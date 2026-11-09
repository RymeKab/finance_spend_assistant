"""
A stand-in for the Claude API, used by the tests.

`FakeClaude` replays a script of replies, so the whole question flow (tool
calls, corrections, evidence, validation) can be tested exactly, offline and for
free. Each reply is a list of content blocks, written with the helpers below:

    FakeClaude([
        [tool_use("query_spend", {"group_by": "vendor", "limit": 5})],
        [submit(status="answered", answer="...", data_refs=["q1"])],
    ])

It also records every request it received (`.requests`), so tests can check
what the app sent to Claude, for example the tool_choice.
"""

from __future__ import annotations

import copy
import itertools
from types import SimpleNamespace
from typing import Any

_ids = itertools.count(1)


def tool_use(name: str, tool_input: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"toolu_{next(_ids)}", "name": name, "input": tool_input or {}}


def submit(**fields: Any) -> dict[str, Any]:
    return tool_use("submit_answer", fields)


def text(content: str) -> dict[str, Any]:
    return {"type": "text", "text": content}


def thinking(content: str = "Let me work out which tool fits.") -> dict[str, Any]:
    """A thinking block, as current Claude models send before answering."""
    return {"type": "thinking", "thinking": content, "signature": "sig-abc123"}


class FakeClaude:
    """Mimics `anthropic.Anthropic().messages.create(...)`."""

    def __init__(self, script: list[Any]):
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []
        self.messages = self  # so that client.messages.create(...) works

    def create(self, **request: Any) -> SimpleNamespace:
        # Copy: the app keeps appending to the same message list after this call.
        self.requests.append(copy.deepcopy(request))
        if not self.script:
            raise AssertionError("FakeClaude ran out of scripted replies")
        step = self.script.pop(0)
        # A step is a list of blocks, or {"blocks": [...], "stop_reason": "..."} to test edge cases.
        blocks, stop_reason = (step["blocks"], step["stop_reason"]) if isinstance(step, dict) else (step, None)
        if stop_reason is None:
            stop_reason = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn"
        return SimpleNamespace(
            content=[SimpleNamespace(**block) for block in blocks],
            stop_reason=stop_reason,
            usage=SimpleNamespace(input_tokens=1000, output_tokens=50, cache_read_input_tokens=800,
                                  cache_creation_input_tokens=0),
        )


class FailingClaude:
    """A client whose every call raises the given exception."""

    def __init__(self, exc: Exception):
        self.exc = exc
        self.messages = self

    def create(self, **request: Any):
        raise self.exc
