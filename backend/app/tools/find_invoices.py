"""
Tool: find_invoices. Lists the individual invoices that match some conditions.

Answers questions like:
  "Which invoices have no approver?"        filters.has_approver=false
  "Invoices from vendors that aren't active" filters.vendor_not_active=true
  "Show me INV-20071"                        filters.invoice_numbers=["INV-20071"]

Returns at most `limit` rows (50 at most) to keep answers readable. It always
reports how many invoices matched in total, so nothing is silently cut off.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.data.loader import Dataset
from app.tools.base import ToolResult
from app.tools.filters import InvoiceFilters

# The columns shown for each invoice, in display order.
INVOICE_COLUMNS = [
    "invoice_number", "invoice_date", "vendor_id", "vendor_name", "country", "vendor_status",
    "description", "amount", "currency", "fx_rate_per_eur", "amount_eur", "cost_center",
    "po_number", "approved_by", "approval_band", "required_approver",
    "missing_po_ref", "missing_required_po", "missing_approver", "vendor_not_active", "is_credit_note",
]


class FindInvoicesInput(BaseModel):
    """Parameters Claude sends to find_invoices."""

    model_config = ConfigDict(extra="forbid")

    filters: InvoiceFilters = Field(default_factory=InvoiceFilters, description="Which invoices to list.")
    sort: Literal["date_asc", "date_desc", "amount_desc", "amount_asc"] = Field("date_asc", description="Row order.")
    limit: int = Field(25, ge=1, le=50, description="Maximum number of rows to return.")


def invoice_rows(frame, columns: list[str] = INVOICE_COLUMNS) -> list[dict]:
    """Convert invoice rows to plain JSON-friendly dictionaries (dates as text, no NaN)."""
    rows = []
    for record in frame[columns].to_dict("records"):
        clean = {}
        for key, value in record.items():
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            elif isinstance(value, float) and value != value:  # NaN
                value = None
            elif hasattr(value, "item"):  # numpy scalar -> Python scalar
                value = value.item()
            clean[key] = value
        rows.append(clean)
    return rows


def run_find_invoices(params: FindInvoicesInput, dataset: Dataset, query_id: str) -> ToolResult:
    matched = params.filters.apply(dataset.invoices)
    order = {
        "date_asc": (["invoice_date", "invoice_number"], [True, True]),
        "date_desc": (["invoice_date", "invoice_number"], [False, True]),
        "amount_desc": (["amount_eur"], [False]),
        "amount_asc": (["amount_eur"], [True]),
    }[params.sort]
    matched = matched.sort_values(order[0], ascending=order[1], kind="stable")
    shown = matched.head(params.limit)

    total = int(len(matched))
    shown_phrase = f"showing {len(shown)} of {total}" if len(shown) < total else f"{total} found"
    sort_phrase = {
        "date_asc": "oldest first", "date_desc": "newest first",
        "amount_desc": "highest EUR amount first", "amount_asc": "lowest EUR amount first",
    }[params.sort]
    return ToolResult(
        query_id=query_id,
        tool="find_invoices",
        params=params.model_dump(mode="json", exclude_none=True),
        description=f"List of invoices ({shown_phrase}), {sort_phrase}. Filters: {params.filters.describe()}.",
        rows=invoice_rows(shown),
        totals={
            "matching_invoices": total,
            "rows_returned": int(len(shown)),
            "invoices_eur": round(float(matched.loc[~matched["is_credit_note"], "amount_eur"].sum()), 2),
            "credit_notes_eur": round(float(matched.loc[matched["is_credit_note"], "amount_eur"].sum()), 2),
        },
        invoice_numbers=list(matched["invoice_number"]),
    )
