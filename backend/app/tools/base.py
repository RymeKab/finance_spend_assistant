"""
What every tool returns: a `ToolResult`.

A ToolResult is the unit of evidence for data. It records:
  * which tool ran and with which parameters (for the audit log),
  * a plain-English description of the computation (shown to the analyst),
  * the result rows (what Claude reads and what the UI shows),
  * the invoice numbers that contributed (so the UI can list the actual invoices).

Each result gets a short ID such as "q1". Claude cites these IDs, and the server
uses them to attach the real rows to the answer. Claude never copies rows itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# How many invoice numbers Claude sees per result. The full list is kept for the evidence.
MODEL_INVOICE_SAMPLE = 20


@dataclass
class ToolResult:
    query_id: str  # "q1", "q2", ... in the order the tools ran
    tool: str  # tool name, e.g. "query_spend"
    params: dict[str, Any]  # the validated parameters (as JSON)
    description: str = ""  # plain-English description of the computation
    rows: list[dict[str, Any]] = field(default_factory=list)  # the result table
    totals: dict[str, Any] = field(default_factory=dict)  # headline numbers, e.g. total EUR
    invoice_numbers: list[str] = field(default_factory=list)  # every contributing invoice
    notes: list[str] = field(default_factory=list)  # facts Claude must pass on (e.g. "no approver roles in the data")
    error: str | None = None  # set when the parameters were invalid or the tool failed

    @property
    def ok(self) -> bool:
        return self.error is None

    def for_model(self) -> dict[str, Any]:
        """The compact version Claude reads (keeps the prompt small and cheap)."""
        if self.error:
            return {"query_id": self.query_id, "error": self.error}
        payload: dict[str, Any] = {
            "query_id": self.query_id,
            "description": self.description,
            "rows": self.rows,
        }
        if self.totals:
            payload["totals"] = self.totals
        if self.invoice_numbers:
            payload["contributing_invoice_count"] = len(self.invoice_numbers)
            payload["contributing_invoices_sample"] = self.invoice_numbers[:MODEL_INVOICE_SAMPLE]
        if self.notes:
            payload["notes"] = self.notes
        return payload
