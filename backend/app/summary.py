"""
The overview behind GET /summary. Plain pandas, no AI involved.

Because it doesn't call Claude, it is fast, always gives the same answer for the
same data, and keeps working when the AI service is down. That's why the
frontend can show it the moment the page opens.
"""

from __future__ import annotations

from typing import Any

from app.data.loader import Dataset

# Control flags shown in the summary, with the policy clause each one relates to.
CONTROL_FLAGS = (
    ("missing_required_po", "No PO reference on an invoice of EUR 1,000+", "2.1–2.3"),
    ("missing_approver", "No approver recorded (must be held)", "3.1"),
    ("vendor_not_active", "Vendor INACTIVE or ON_HOLD (escalate)", "4.1"),
    ("is_credit_note", "Unmatched credit notes (not subtracted)", "6.1"),
)


def _eur(value: float) -> float:
    return round(float(value), 2)


def build_summary(dataset: Dataset) -> dict[str, Any]:
    everything = dataset.invoices
    first, last = dataset.period
    credit_notes = everything[everything["is_credit_note"]]
    # Spend = invoices only. Credit notes can't be matched to their originals (§6.1),
    # so they are reported separately and never subtracted from the breakdowns.
    invoices = everything[~everything["is_credit_note"]]

    by_currency = (
        invoices.groupby("currency")
        .agg(invoice_count=("invoice_number", "count"), amount_original=("amount", "sum"), amount_eur=("amount_eur", "sum"))
        .reset_index()
        .sort_values("amount_eur", ascending=False)
    )
    by_status = (
        invoices.groupby("vendor_status")
        .agg(vendor_count=("vendor_id", "nunique"), invoice_count=("invoice_number", "count"), amount_eur=("amount_eur", "sum"))
        .reset_index()
        .sort_values("amount_eur", ascending=False)
    )

    return {
        "invoice_count": int(len(everything)),  # all documents, credit notes included
        "vendor_count": int(everything["vendor_id"].nunique()),
        "period": {"first_invoice": first.isoformat(), "last_invoice": last.isoformat()},
        "spend_eur": {
            "gross": _eur(invoices["amount_eur"].sum()),  # the headline: invoices only
            "credit_notes": _eur(credit_notes["amount_eur"].sum()),  # unmatched, shown separately
            "credit_note_count": int(len(credit_notes)),
            "net": _eur(everything["amount_eur"].sum()),  # for reference only
        },
        "by_currency": [
            {
                "currency": r["currency"],
                "invoice_count": int(r["invoice_count"]),
                "amount_original": _eur(r["amount_original"]),
                "amount_eur": _eur(r["amount_eur"]),
            }
            for r in by_currency.to_dict("records")
        ],
        "by_vendor_status": [
            {
                "status": r["vendor_status"],
                "vendor_count": int(r["vendor_count"]),
                "invoice_count": int(r["invoice_count"]),
                "amount_eur": _eur(r["amount_eur"]),
            }
            for r in by_status.to_dict("records")
        ],
        "control_flags": [
            {
                "flag": column,
                "label": label,
                "policy_clause": clause,
                "invoice_count": int(everything[column].sum()),
                "amount_eur": _eur(everything.loc[everything[column], "amount_eur"].sum()),
            }
            for column, label, clause in CONTROL_FLAGS
        ],
        "fx_basis": dataset.fx.basis_description,
        "data_snapshot": dataset.data_snapshot,
        "source_files": [
            {"name": f.name, "sha256": f.sha256, "rows": f.rows} for f in dataset.source_files
        ],
    }
