"""
Tool: query_spend. Totals, rankings and breakdowns of spend in EUR.

Answers questions like:
  "Top 5 vendors by spend"           group_by="vendor", limit=5
  "Total spend with Spanish vendors" filters.countries=["Spain"], group_by="none"
  "Spend by currency"                group_by="currency"

Every amount is the EUR amount computed at load time (policy §5.1).

Credit notes are NOT subtracted by default
------------------------------------------
Policy §6.1 says credit notes must be matched to their original invoice. Nothing
in the data links a credit note to an invoice, so none can be matched. Subtracting
them anyway would lower a vendor's spend on the strength of a match nobody has
confirmed. So, by default:
  * spend counts invoices only,
  * unmatched credit notes are reported separately: in the totals, and per row
    in a `unmatched_credit_notes_eur` column whenever a group has any.
`net_credit_notes=true` gives a net figure when the user explicitly asks for one.
The filter `is_credit_note=true` shows the credit notes on their own.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from app.data.loader import Dataset
from app.tools.base import ToolResult
from app.tools.filters import InvoiceFilters

GroupBy = Literal["vendor", "country", "currency", "vendor_status", "cost_center", "month", "approver", "description", "none"]
SortOrder = Literal["amount_desc", "amount_asc", "count_desc", "group_asc"]

# Which invoice columns identify a group, and what each column is called in the result rows.
GROUP_COLUMNS: dict[str, dict[str, str]] = {
    "vendor": {"vendor_id": "vendor_id", "vendor_name": "vendor", "country": "country", "vendor_status": "vendor_status"},
    "country": {"country": "country"},
    "currency": {"currency": "currency"},
    "vendor_status": {"vendor_status": "vendor_status"},
    "cost_center": {"cost_center": "cost_center"},
    "month": {"month": "month"},
    "approver": {"approved_by": "approver"},
    "description": {"description": "description"},
}
MISSING_LABEL = "(none recorded)"


class QuerySpendInput(BaseModel):
    """Parameters Claude sends to query_spend."""

    model_config = ConfigDict(extra="forbid")

    filters: InvoiceFilters = Field(default_factory=InvoiceFilters, description="Which invoices to include.")
    group_by: GroupBy = Field("none", description="How to break the total down. 'none' = one overall total.")
    sort: SortOrder = Field("amount_desc", description="Order of the groups. Use 'group_asc' for months.")
    limit: int = Field(50, ge=1, le=50, description="Maximum number of groups to return, e.g. 5 for a top 5.")
    net_credit_notes: bool = Field(
        False,
        description="Subtract credit notes from spend. Leave false unless the user explicitly asks for a net figure: "
        "policy §6.1 requires credit notes to be matched to their original invoice, and none can be matched here.",
    )


def _eur(value: float) -> float:
    return round(float(value), 2)


def run_query_spend(params: QuerySpendInput, dataset: Dataset, query_id: str) -> ToolResult:
    matched = params.filters.apply(dataset.invoices)
    credit_notes = matched[matched["is_credit_note"]]

    # What counts as spend: invoices only, unless credit notes are asked for on their own or netted on request.
    only_credit_notes = params.filters.is_credit_note is True
    include_credit_notes = only_credit_notes or params.net_credit_notes
    spend = matched if include_credit_notes else matched[~matched["is_credit_note"]]
    report_separately = not include_credit_notes and not credit_notes.empty

    totals = {"spend_eur": _eur(spend["amount_eur"].sum()), "invoice_count": int(len(spend))}
    if report_separately:
        totals["unmatched_credit_note_count"] = int(len(credit_notes))
        totals["unmatched_credit_notes_eur"] = _eur(credit_notes["amount_eur"].sum())
    if params.net_credit_notes and not only_credit_notes:
        totals["credit_notes_netted_eur"] = _eur(credit_notes["amount_eur"].sum())

    if params.group_by == "none":
        rows = [{"group": "All matching invoices", "amount_eur": totals["spend_eur"], "invoice_count": totals["invoice_count"]}]
        if report_separately:
            rows[0]["unmatched_credit_notes_eur"] = totals["unmatched_credit_notes_eur"]
        contributing = list(spend["invoice_number"])
        group_phrase, limit_phrase = "as one overall total", ""
    else:
        rows, contributing, group_count = _grouped(spend, credit_notes if report_separately else None, params)
        totals["groups"] = group_count
        group_phrase = f"grouped by {params.group_by.replace('_', ' ')}"
        limit_phrase = f", showing {len(rows)} of {group_count} groups" if len(rows) < group_count else ""

    sort_phrase = {
        "amount_desc": "highest EUR amount first",
        "amount_asc": "lowest EUR amount first",
        "count_desc": "most invoices first",
        "group_asc": "in alphabetical / date order",
    }[params.sort]
    if only_credit_notes:
        basis = "Sum of credit notes in EUR"
    elif params.net_credit_notes:
        basis = f"Sum of EUR amounts, net of {len(credit_notes)} credit note(s) as requested (matching unconfirmed, §6.1)"
    elif report_separately:
        basis = (f"Sum of EUR invoice amounts, excluding {len(credit_notes)} unmatched credit note(s) "
                 f"(EUR {totals['unmatched_credit_notes_eur']:,.2f}, shown separately, §6.1)")
    else:
        basis = "Sum of EUR invoice amounts (no credit notes in this selection)"
    description = (
        f"{basis}, {group_phrase}"
        f"{'' if params.group_by == 'none' else ', ' + sort_phrase}{limit_phrase}. "
        f"Filters: {params.filters.describe()}."
    )

    return ToolResult(
        query_id=query_id,
        tool="query_spend",
        params=params.model_dump(mode="json", exclude_none=True),
        description=description,
        rows=rows,
        totals=totals,
        invoice_numbers=contributing,
    )


def _grouped(
    spend: pd.DataFrame, credit_notes: pd.DataFrame | None, params: QuerySpendInput
) -> tuple[list[dict], list[str], int]:
    """
    Group, sort and trim. Returns (rows, contributing invoice numbers, total number of groups).
    When `credit_notes` is given, each row also shows its unmatched credit notes, without subtracting them.
    """
    columns = GROUP_COLUMNS[params.group_by]
    frame = spend.copy()
    for column in columns:
        frame[column] = frame[column].fillna(MISSING_LABEL).astype(str)

    aggregations = {"amount_eur": ("amount_eur", "sum"), "invoice_count": ("invoice_number", "count")}
    if params.group_by == "currency":
        aggregations["amount_original"] = ("amount", "sum")  # same currency within a group, so summing is valid
    grouped = frame.groupby(list(columns), dropna=False).agg(**aggregations).reset_index()

    sort_by = {
        "amount_desc": (["amount_eur"], [False]),
        "amount_asc": (["amount_eur"], [True]),
        "count_desc": (["invoice_count", "amount_eur"], [False, False]),
        "group_asc": (list(columns), [True] * len(columns)),
    }[params.sort]
    grouped = grouped.sort_values(sort_by[0], ascending=sort_by[1], kind="stable")
    top = grouped.head(params.limit)

    # Unmatched credit notes per group, shown next to the spend but never subtracted from it.
    credits_by_group: dict[tuple, float] = {}
    if credit_notes is not None:
        cn = credit_notes.copy()
        for column in columns:
            cn[column] = cn[column].fillna(MISSING_LABEL).astype(str)
        credits_by_group = cn.groupby(list(columns))["amount_eur"].sum().to_dict()
        if len(columns) == 1:  # pandas uses plain keys, not tuples, for a single column
            credits_by_group = {(k,): v for k, v in credits_by_group.items()}

    rows = []
    for record in top.to_dict("records"):
        row = {label: record[column] for column, label in columns.items()}
        row["amount_eur"] = _eur(record["amount_eur"])
        if "amount_original" in record:
            row["amount_original"] = _eur(record["amount_original"])
        row["invoice_count"] = int(record["invoice_count"])
        if credit_notes is not None:
            row["unmatched_credit_notes_eur"] = _eur(credits_by_group.get(tuple(record[c] for c in columns), 0.0))
        rows.append(row)

    # The invoices behind the groups that are actually shown, listed group by group
    # (in the same order as the rows) and largest amount first within each group.
    rank = {key: position for position, key in enumerate(top[list(columns)].apply(tuple, axis=1))}
    frame["_group_rank"] = frame[list(columns)].apply(tuple, axis=1).map(rank)
    shown = frame[frame["_group_rank"].notna()].sort_values(["_group_rank", "amount_eur"], ascending=[True, False])
    return rows, list(shown["invoice_number"]), int(len(grouped))
