"""
The shape of Claude's final answer: the `submit_answer` tool.

Claude must finish every question by "calling" submit_answer. This gives a
structured reply that the server can check, instead of free text it would have
to guess its way through. The tool is marked `strict`, so the API guarantees the
reply matches the schema below.

Note what is NOT in it: no quotes from the policy and no data rows. Claude only
gives clause IDs ("3.1") and query IDs ("q1"). The server turns those IDs into
the real text and rows (see evidence.py), so the model has no way to invent evidence.
"""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

SUBMIT_ANSWER = "submit_answer"

AnswerStatus = Literal["answered", "partial", "insufficient_data", "out_of_scope"]


class AnswerSubmission(BaseModel):
    """Claude's final answer. Validated again on our side before anything is shown."""

    model_config = ConfigDict(extra="ignore")

    status: AnswerStatus
    answer: str = Field(min_length=1, max_length=3000)
    policy_refs: list[str] = Field(default_factory=list)
    data_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


def _string_list(description: str) -> dict:
    return {"type": "array", "items": {"type": "string"}, "description": description}


# Written by hand rather than generated: strict tools accept only a subset of JSON
# Schema (no length limits or defaults), and making every field required keeps the
# schema simple. Claude sends empty lists when a field doesn't apply.
SUBMIT_ANSWER_TOOL = {
    "name": SUBMIT_ANSWER,
    "description": (
        "Submit the final answer. Call this exactly once, at the end. Cite policy clause IDs and query IDs; "
        "do not paste policy text or data rows."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": list(get_args(AnswerStatus)),
                "description": "answered = fully answered; partial = part of it; insufficient_data = the data "
                "can't answer it; out_of_scope = not about these invoices or this policy.",
            },
            "answer": {"type": "string", "description": "The answer for the analyst, 1-5 short sentences."},
            "policy_refs": _string_list("Policy clause IDs relied on, e.g. ['3', '7.2']."),
            "data_refs": _string_list("query_id of every tool result used, e.g. ['q1']."),
            "assumptions": _string_list("Definitions or interpretations applied."),
            "missing_information": _string_list("For partial / insufficient_data: what data would be needed."),
        },
        "required": ["status", "answer", "policy_refs", "data_refs", "assumptions", "missing_information"],
        "additionalProperties": False,
    },
}
