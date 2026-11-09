"""
The conversation loop with Claude for one question (POST /ask, steps 3-5 on the diagram).

In plain English
----------------
1. Send Claude the standing instructions (system prompt), the list of tools and
   the analyst's question.
2. Claude replies by asking for one or more tools, for example
   "query_spend, grouped by vendor, top 5".
3. We run those tools on the invoice table and send the results back, each
   labelled with a query ID ("q1", "q2", ...).
4. Steps 2 and 3 repeat, at most `max_tool_rounds` times. After that, further
   lookups are refused with a message telling Claude to submit its answer.
5. Claude ends by calling `submit_answer`: a status, the answer text, and the
   IDs of the clauses and queries it used.

How the model is called (current Claude models)
-----------------------------------------------
* tool_choice is "auto". Current models (for example claude-sonnet-5-5) reject
  forced tool choice, so the prompt says when to use each tool, and any reply
  that isn't a submit_answer call is sent back for correction.
* submit_answer is a "strict" tool, so its input always matches the schema.
* Current models think before answering (adaptive thinking). Their thinking
  blocks are passed back unchanged with the tool results, as the API requires.
* Sampling parameters (temperature) are only sent if configured, because
  current models reject them.

Safety nets
-----------
* A plain-text reply, an invalid submit_answer, or an answer that quotes figures
  without having looked at any data is sent back (at most MAX_CORRECTIONS times)
  with an explanation, so Claude can fix it. After that the request ends with a
  clear 502 error.
* A reply cut off by the token limit, or a refusal, ends with a clear error.
* There is an overall deadline for the whole question, not just per call.
* Every Claude error (timeout, bad key, unknown model, rate limit) becomes a typed API error.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.config import Settings
from app.data.loader import Dataset
from app.errors import LLMBadOutput, LLMTimeout
from app.llm.client import translate_llm_error
from app.llm.submission import SUBMIT_ANSWER, SUBMIT_ANSWER_TOOL, AnswerSubmission
from app.policy.parser import Policy
from app.tools import data_tool_definitions, run_tool
from app.tools.base import ToolResult
from app.validators import ungrounded_figures

MAX_CORRECTIONS = 2  # how many times a reply that can't be used is sent back for repair
NO_MORE_LOOKUPS = (
    "Not run: the limit of data lookups for this question has been reached. "
    "Call submit_answer now, using only the results you already have."
)


@dataclass
class Usage:
    """Token counts across all Claude calls for one question (for cost tracking)."""

    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def add(self, response: Any) -> None:
        self.llm_calls += 1
        usage = getattr(response, "usage", None)
        for name in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            setattr(self, name, getattr(self, name) + int(getattr(usage, name, 0) or 0))


@dataclass
class OrchestratorResult:
    submission: AnswerSubmission
    tool_results: list[ToolResult]
    usage: Usage
    corrections: list[str] = field(default_factory=list)  # why a reply had to be sent back, if it was


class Orchestrator:
    """Runs one question through Claude and the tools. Create one per request."""

    def __init__(self, client: Any, dataset: Dataset, policy: Policy, system_prompt: str, settings: Settings):
        self.client = client
        self.dataset = dataset
        self.policy = policy
        self.system_prompt = system_prompt
        self.settings = settings
        self.tools = [*data_tool_definitions(), SUBMIT_ANSWER_TOOL]

    # ------------------------------------------------------------------ main loop
    def answer(self, question: str) -> OrchestratorResult:
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        results: list[ToolResult] = []
        usage = Usage()
        corrections: list[str] = []
        data_rounds = 0
        deadline = time.monotonic() + self.settings.ask_deadline_seconds
        # Hard ceiling on Claude calls: data rounds + one refused round + the answer + corrections.
        max_calls = self.settings.max_tool_rounds + 2 + MAX_CORRECTIONS

        def send_back(problem: str) -> None:
            """Record a correction, or give up if the budget is spent."""
            if len(corrections) >= MAX_CORRECTIONS:
                raise LLMBadOutput(f"Claude's answer could not be used: {problem}")
            corrections.append(problem)

        while usage.llm_calls < max_calls:
            response = self._call_claude(messages, deadline)
            usage.add(response)
            self._check_stop_reason(response)

            blocks = [b for b in (_block_to_dict(x) for x in getattr(response, "content", []) or []) if b]
            tool_uses = [b for b in blocks if b["type"] == "tool_use"]

            # --- A reply without any tool call: ask for the structured answer.
            if not tool_uses:
                send_back("Claude replied in plain text instead of calling submit_answer.")
                if blocks:
                    messages.append({"role": "assistant", "content": blocks})
                messages.append({"role": "user", "content": "Please give your final answer by calling the submit_answer tool."})
                continue

            messages.append({"role": "assistant", "content": blocks})
            final = next((b for b in tool_uses if b["name"] == SUBMIT_ANSWER), None)

            # --- The final answer: check it, accept it or send it back.
            if final is not None:
                submission, problem = self._check_submission(final["input"], question, results)
                if problem is None:
                    return OrchestratorResult(submission, results, usage, corrections)
                if submission is not None and len(corrections) >= MAX_CORRECTIONS:
                    # Usable, and out of retries: accept; the validators will flag the issue to the user.
                    corrections.append(f"Accepted with warnings: {problem}")
                    return OrchestratorResult(submission, results, usage, corrections)
                send_back(problem)
                messages.append({"role": "user", "content": [
                    _tool_reply(b["id"], problem if b is final else "Not run: an answer was submitted in the same turn.", True)
                    for b in tool_uses
                ]})
                continue

            # --- Claude asked for data: run the tools (or refuse once the budget is spent).
            replies = []
            if data_rounds >= self.settings.max_tool_rounds:
                replies = [_tool_reply(b["id"], NO_MORE_LOOKUPS, True) for b in tool_uses]
            else:
                data_rounds += 1
                for block in tool_uses:
                    result = run_tool(block["name"], block.get("input") or {}, self.dataset, f"q{len(results) + 1}")
                    results.append(result)
                    replies.append(_tool_reply(block["id"], json.dumps(result.for_model(), default=str), not result.ok))
            messages.append({"role": "user", "content": replies})

        raise LLMBadOutput("Claude did not finish within the allowed number of steps.")

    # ------------------------------------------------------------------ helpers
    def _call_claude(self, messages: list[dict[str, Any]], deadline: float) -> Any:
        """One request to the Claude API. Every SDK error is converted to an API error."""
        remaining = deadline - time.monotonic()
        if remaining < 1:
            raise LLMTimeout("Answering took longer than the allowed time. Please try again or simplify the question.")
        request: dict[str, Any] = {
            "model": self.settings.anthropic_model,
            "max_tokens": self.settings.llm_max_tokens,
            # cache_control: the tools and system prompt are identical on every request, so
            # Anthropic can cache them, which cuts cost and latency on repeat questions.
            "system": [{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
            "tools": self.tools,
            "tool_choice": {"type": "auto"},
            "messages": messages,
            # Never wait longer than the time left for the whole question.
            "timeout": min(self.settings.llm_timeout_seconds, remaining),
        }
        if self.settings.llm_effort:
            request["output_config"] = {"effort": self.settings.llm_effort}
        if self.settings.llm_temperature is not None:
            request["temperature"] = self.settings.llm_temperature
        try:
            return self.client.messages.create(**request)
        except Exception as exc:
            raise translate_llm_error(exc) from exc

    @staticmethod
    def _check_stop_reason(response: Any) -> None:
        reason = getattr(response, "stop_reason", None)
        if reason == "max_tokens":
            raise LLMBadOutput("Claude's reply was cut off by the token limit. Increase LLM_MAX_TOKENS in backend/.env.")
        if reason == "refusal":
            raise LLMBadOutput("Claude declined to answer this question.")

    def _check_submission(
        self, raw: dict[str, Any], question: str, results: list[ToolResult]
    ) -> tuple[AnswerSubmission | None, str | None]:
        """Return (submission, None) if usable, or (submission-or-None, explanation) if not."""
        try:
            submission = AnswerSubmission.model_validate(raw or {})
        except ValidationError as exc:
            fields = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors())
            return None, f"submit_answer was invalid (check: {fields}). Call submit_answer again with all required fields."

        # "No tool, no number": figures with no data behind them are sent back.
        used_data = any(r.ok for r in results)
        if not used_data:
            stray = ungrounded_figures(submission.answer, [question, self.policy.prompt_text()])
            if stray:
                return submission, (
                    f"Your answer states figures ({', '.join(stray)}) but no data tool was used. Every figure "
                    "must come from a tool result: call the relevant data tool, or answer without those figures."
                )
        return submission, None


def _block_to_dict(block: Any) -> dict[str, Any] | None:
    """
    Convert a content block from Claude's reply into the plain dict the API accepts back.
    Thinking blocks are kept exactly as received: the API requires them to be passed back.
    """
    get = (lambda k: block.get(k)) if isinstance(block, dict) else (lambda k: getattr(block, k, None))
    kind = get("type")
    if kind == "text":
        return {"type": "text", "text": get("text")} if (get("text") or "").strip() else None
    if kind == "tool_use":
        return {"type": "tool_use", "id": get("id"), "name": get("name"), "input": get("input") or {}}
    if kind == "thinking":
        return {"type": "thinking", "thinking": get("thinking") or "", "signature": get("signature")}
    if kind == "redacted_thinking":
        return {"type": "redacted_thinking", "data": get("data")}
    return None  # block types this app doesn't use


def _tool_reply(tool_use_id: str, content: str, is_error: bool) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content, "is_error": is_error}
