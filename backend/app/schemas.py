"""
The API contract: the exact shape of every request and response.

These models do two jobs. They validate what goes in and out of the API, and
FastAPI turns them into the interactive documentation at http://localhost:8000/docs.

The frontend mirrors them in frontend/src/lib/types.ts. Change both together.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

AnswerStatus = Literal["answered", "partial", "insufficient_data", "out_of_scope"]


# ----------------------------------------------------------------------------- /ask
class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000, description="The analyst's question in plain English.")

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("The question is empty.")
        return value


class PolicyEvidence(BaseModel):
    clause_id: str = Field(description="Clause number, e.g. '3.1'.")
    section_title: str
    text: str = Field(description="Verbatim policy text, looked up by the server.")


class DataEvidence(BaseModel):
    query_id: str = Field(description="ID of the tool call, e.g. 'q1'.")
    tool: str
    description: str = Field(description="Plain-English description of the computation.")
    params: dict[str, Any]
    rows: list[dict[str, Any]] = Field(description="The result table.")
    totals: dict[str, Any] = {}
    notes: list[str] = []
    invoices: list[dict[str, Any]] = Field(description="The contributing invoices (at most 50).")
    invoice_count: int = Field(description="How many invoices contributed in total.")
    invoices_truncated: bool


class Evidence(BaseModel):
    policy: list[PolicyEvidence]
    data: list[DataEvidence]


class AnswerMeta(BaseModel):
    model: str
    prompt_version: str
    latency_ms: int
    llm_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    data_snapshot: str


class AskResponse(BaseModel):
    request_id: str
    status: AnswerStatus
    answer: str
    route: list[Literal["policy", "data"]] = Field(description="What the answer actually used.")
    evidence: Evidence
    assumptions: list[str]
    missing_information: list[str]
    warnings: list[str]
    meta: AnswerMeta


# ------------------------------------------------------------------------- /summary
class Period(BaseModel):
    first_invoice: str
    last_invoice: str


class SpendTotals(BaseModel):
    gross: float = Field(description="Invoices only: the headline spend.")
    credit_notes: float = Field(description="Unmatched credit notes, reported separately (policy §6.1).")
    credit_note_count: int
    net: float = Field(description="Invoices minus credit notes, for reference only.")


class CurrencyBreakdown(BaseModel):
    currency: str
    invoice_count: int
    amount_original: float
    amount_eur: float


class StatusBreakdown(BaseModel):
    status: str
    vendor_count: int
    invoice_count: int
    amount_eur: float


class ControlFlag(BaseModel):
    flag: str
    label: str
    policy_clause: str
    invoice_count: int
    amount_eur: float


class SourceFileInfo(BaseModel):
    name: str
    sha256: str
    rows: int | None


class SummaryResponse(BaseModel):
    invoice_count: int
    vendor_count: int
    period: Period
    spend_eur: SpendTotals
    by_currency: list[CurrencyBreakdown]
    by_vendor_status: list[StatusBreakdown]
    control_flags: list[ControlFlag]
    fx_basis: str
    data_snapshot: str
    source_files: list[SourceFileInfo]


# --------------------------------------------------------------------- /health, errors
class HealthResponse(BaseModel):
    status: Literal["ok"]
    llm_configured: bool
    model: str
    data_snapshot: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody
