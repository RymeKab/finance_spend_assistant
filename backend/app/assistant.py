"""
The assistant itself, independent of the web layer.

`SpendAssistant` loads everything once at startup (data, policy, prompt) and
offers the three operations the API exposes: health(), summary() and ask().

Keeping this separate from main.py means the whole question-answering flow can
be tested, or reused from a script, without starting a web server.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from app.audit import AuditLog
from app.config import Settings
from app.data.loader import POLICY_FILE, load_dataset
from app.errors import AppError
from app.evidence import build_evidence
from app.llm.client import create_claude_client
from app.llm.orchestrator import Orchestrator
from app.llm.prompt import PROMPT_VERSION, build_system_prompt
from app.policy.parser import load_policy
from app.summary import build_summary


class SpendAssistant:
    def __init__(self, settings: Settings, client_factory: Callable[[Settings], Any] = create_claude_client):
        self.settings = settings
        self.dataset = load_dataset(settings.data_dir)
        self.policy = load_policy(settings.data_dir / POLICY_FILE)
        self.system_prompt = build_system_prompt(self.dataset, self.policy, settings.max_tool_rounds)
        self.audit = AuditLog(settings.log_dir)
        self._summary = build_summary(self.dataset)  # the data never changes while running
        self._client_factory = client_factory
        self._client: Any = None

    # ------------------------------------------------------------------ GET /health
    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "llm_configured": self.settings.llm_configured,
            "model": self.settings.anthropic_model,
            "data_snapshot": self.dataset.data_snapshot,
        }

    # ----------------------------------------------------------------- GET /summary
    def summary(self) -> dict[str, Any]:
        return self._summary

    # -------------------------------------------------------------------- POST /ask
    def ask(self, question: str, request_id: str) -> dict[str, Any]:
        started = time.perf_counter()
        audit_base = {
            "request_id": request_id,
            "question": question,
            "model": self.settings.anthropic_model,
            "prompt_version": PROMPT_VERSION,
            "data_snapshot": self.dataset.data_snapshot,
        }
        try:
            client = self._get_client()
            result = Orchestrator(client, self.dataset, self.policy, self.system_prompt, self.settings).answer(question)
        except AppError as exc:
            self.audit.write({**audit_base, "outcome": "error", "error_code": exc.code, "error": exc.message,
                              "latency_ms": _elapsed_ms(started)})
            raise

        evidence = build_evidence(question, result, self.dataset, self.policy)
        latency = _elapsed_ms(started)
        response = {
            "request_id": request_id,
            "status": evidence.status,
            "answer": result.submission.answer,
            "route": evidence.route,
            "evidence": {"policy": evidence.policy, "data": evidence.data},
            "assumptions": evidence.assumptions,
            "missing_information": result.submission.missing_information,
            "warnings": evidence.warnings,
            "meta": {
                "model": self.settings.anthropic_model,
                "prompt_version": PROMPT_VERSION,
                "latency_ms": latency,
                "llm_calls": result.usage.llm_calls,
                "tool_calls": len(result.tool_results),
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "cache_read_input_tokens": result.usage.cache_read_input_tokens,
                "data_snapshot": self.dataset.data_snapshot,
            },
        }
        self.audit.write({
            **audit_base,
            "outcome": "answered",
            "status": evidence.status,
            "route": evidence.route,
            "answer": result.submission.answer,
            "policy_refs": [p["clause_id"] for p in evidence.policy],
            "data_refs": [d["query_id"] for d in evidence.data],
            "tool_calls": [{"query_id": r.query_id, "tool": r.tool, "params": r.params, "error": r.error}
                           for r in result.tool_results],
            "corrections": result.corrections,
            "warnings": evidence.warnings,
            "usage": vars(result.usage),
            "latency_ms": latency,
        })
        return response

    def _get_client(self) -> Any:
        """Create the Claude client on first use (raises a clear 503 if key_1 is missing)."""
        if self._client is None:
            self._client = self._client_factory(self.settings)
        return self._client


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
