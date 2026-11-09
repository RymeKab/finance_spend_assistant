"""
Tool: approval_requirement. Who must approve a given invoice or amount (policy §3).

Answers questions like:
  "Who must approve INV-20071?"             invoice_number="INV-20071"
  "Who approves a USD 60,000 invoice?"      amount=60000, currency="USD"

It converts to EUR first (at the rate for the invoice date, policy §5.1), then
picks the band. That's why it's a tool: the conversion can change the band.

For a real invoice it also reports who actually approved it. The data has no
approver roles or limits, though, so it can't confirm that person had the
authority. The tool says so explicitly, and Claude must pass that on.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.data.loader import Dataset
from app.policy.approval import required_approval
from app.tools.base import ToolResult
from app.tools.filters import Currency

SELF_APPROVAL_NOTE = "Self-approval is prohibited at all thresholds (§7.2)."
NO_ROLES_NOTE = (
    "The data records who approved the invoice but has no approver roles or limits, "
    "so it cannot confirm that this person holds the required authority."
)


class ApprovalRequirementInput(BaseModel):
    """Give either an invoice number, or an amount with its currency (and ideally a date)."""

    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None = Field(None, description="An existing invoice, e.g. 'INV-20071'.")
    amount: float | None = Field(None, description="An amount to classify, in `currency`.")
    currency: Currency = Field("EUR", description="Currency of `amount`.")
    date: dt.date | None = Field(None, description="Date for the exchange rate (YYYY-MM-DD). Needed for GBP/USD.")

    @model_validator(mode="after")
    def _need_invoice_or_amount(self) -> "ApprovalRequirementInput":
        if not self.invoice_number and self.amount is None:
            raise ValueError("Provide either invoice_number or amount.")
        return self


def run_approval_requirement(params: ApprovalRequirementInput, dataset: Dataset, query_id: str) -> ToolResult:
    notes: list[str] = [SELF_APPROVAL_NOTE]
    invoice_numbers: list[str] = []
    recorded_approver = None

    if params.invoice_number:
        match = dataset.invoices[dataset.invoices["invoice_number"].str.upper() == params.invoice_number.upper()]
        if match.empty:
            return ToolResult(query_id, "approval_requirement", params.model_dump(mode="json", exclude_none=True),
                              error=f"Invoice {params.invoice_number} does not exist in the 2025 data.")
        invoice = match.iloc[0]
        amount, currency, on = float(invoice["amount"]), invoice["currency"], invoice["invoice_date"]
        recorded_approver = invoice["approved_by"]
        invoice_numbers = [invoice["invoice_number"]]
        notes.append(NO_ROLES_NOTE if recorded_approver else
                     "No approver is recorded for this invoice, so it must be held and may not be paid (§3.1).")
    else:
        amount, currency, on = float(params.amount), params.currency, params.date
        if currency != "EUR" and on is None:
            on = dataset.fx.latest_rate(currency).rate_date
            notes.append(f"No date was given, so the latest available {currency} rate ({on.isoformat()}) was used.")
        on = on or dt.date.today()

    amount_eur, rate = dataset.fx.to_eur(amount, currency, on)
    tier = required_approval(amount_eur)
    if tier is None:
        notes.append("This is a credit note (negative amount): approval thresholds don't apply; "
                     "it must be matched to the original invoice (§6.1).")

    row = {
        "invoice_number": invoice_numbers[0] if invoice_numbers else None,
        "amount": round(amount, 2),
        "currency": currency,
        "fx_rate_per_eur": rate.rate_per_eur,
        "fx_rate_date": rate.rate_date.isoformat() if currency != "EUR" else None,
        "amount_eur": amount_eur,
        "policy_band_eur": tier.band if tier else None,
        "required_approver": tier.approver if tier else None,
        "recorded_approver": recorded_approver,
        "policy_clause": "3",
    }
    subject = params.invoice_number or f"{currency} {amount:,.2f}"
    conversion = "" if currency == "EUR" else f" converted at {rate.rate_per_eur} {currency} per EUR ({rate.rate_date.isoformat()})"
    return ToolResult(
        query_id=query_id,
        tool="approval_requirement",
        params=params.model_dump(mode="json", exclude_none=True),
        description=f"Approval band under policy §3 for {subject}: amount{conversion} = EUR {amount_eur:,.2f}.",
        rows=[{k: v for k, v in row.items() if v is not None}],
        invoice_numbers=invoice_numbers,
        notes=notes,
    )
