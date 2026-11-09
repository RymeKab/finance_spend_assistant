"""
The filters shared by the invoice tools ("only Spanish vendors", "only invoices without a PO", ...).

Claude fills these in as JSON. Pydantic checks them before anything runs, so an
invalid value (say, a currency that doesn't exist) comes back to Claude as a clear
error instead of silently returning wrong numbers.

Every filter can also describe itself in plain English. That description goes into
the evidence panel, so an analyst can check that the right question was asked of
the data.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

Currency = Literal["EUR", "GBP", "USD"]
VendorStatus = Literal["ACTIVE", "INACTIVE", "ON_HOLD"]


class InvoiceFilters(BaseModel):
    """Optional conditions. An invoice is kept only if it meets every condition that is set."""

    model_config = ConfigDict(extra="forbid")

    invoice_numbers: list[str] | None = Field(None, description="Exact invoice numbers, e.g. ['INV-20071'].")
    vendor_ids: list[str] | None = Field(None, description="Exact vendor IDs, e.g. ['V-1002'].")
    vendor_name_contains: str | None = Field(None, description="Case-insensitive part of a vendor name, e.g. 'labtech'.")
    countries: list[str] | None = Field(None, description="Vendor countries as in the vendor master, e.g. ['Spain'].")
    vendor_statuses: list[VendorStatus] | None = Field(
        None, description="Vendor status as in the vendor master today (the data has no status history)."
    )
    currencies: list[Currency] | None = Field(None, description="Original invoice currency.")
    cost_centers: list[str] | None = Field(None, description="Cost centre codes, e.g. ['CC-IT-550'].")
    approvers: list[str] | None = Field(None, description="Values of approved_by, e.g. ['j.smith'].")
    description_contains: str | None = Field(None, description="Case-insensitive part of the invoice description.")
    date_from: date | None = Field(None, description="First invoice date to include (YYYY-MM-DD).")
    date_to: date | None = Field(None, description="Last invoice date to include (YYYY-MM-DD).")
    min_amount_eur: float | None = Field(None, description="Smallest EUR amount to include.")
    max_amount_eur: float | None = Field(None, description="Largest EUR amount to include.")
    has_po_ref: bool | None = Field(None, description="true = only invoices WITH a PO number; false = only WITHOUT (any amount).")
    missing_required_po: bool | None = Field(
        None, description="true = only invoices of EUR 1,000+ with no PO reference: the actual §2.1 breach."
    )
    has_approver: bool | None = Field(None, description="true = only invoices WITH an approver; false = only WITHOUT.")
    vendor_not_active: bool | None = Field(
        None, description="true = only vendors that are INACTIVE or ON_HOLD today (the data has no status history)."
    )
    is_credit_note: bool | None = Field(None, description="true = only credit notes (negative amounts); false = exclude them.")

    def apply(self, invoices: pd.DataFrame) -> pd.DataFrame:
        """Return only the invoices that meet every condition that is set."""
        keep = pd.Series(True, index=invoices.index)

        def is_in(column: str, values: list[str] | None, upper: bool = False) -> None:
            nonlocal keep
            if values:
                wanted = {v.upper() if upper else v.lower() for v in values}
                column_values = invoices[column].fillna("").astype(str)
                column_values = column_values.str.upper() if upper else column_values.str.lower()
                keep &= column_values.isin(wanted)

        def contains(column: str, text: str | None) -> None:
            nonlocal keep
            if text:
                keep &= invoices[column].fillna("").astype(str).str.contains(text, case=False, regex=False)

        def flag(column: str, wanted: bool | None) -> None:
            nonlocal keep
            if wanted is not None:
                keep &= invoices[column] == wanted

        is_in("invoice_number", self.invoice_numbers, upper=True)
        is_in("vendor_id", self.vendor_ids, upper=True)
        contains("vendor_name", self.vendor_name_contains)
        is_in("country", self.countries)
        is_in("vendor_status", self.vendor_statuses, upper=True)
        is_in("currency", self.currencies, upper=True)
        is_in("cost_center", self.cost_centers, upper=True)
        is_in("approved_by", self.approvers)
        contains("description", self.description_contains)
        if self.date_from:
            keep &= invoices["invoice_date"] >= self.date_from
        if self.date_to:
            keep &= invoices["invoice_date"] <= self.date_to
        if self.min_amount_eur is not None:
            keep &= invoices["amount_eur"] >= self.min_amount_eur
        if self.max_amount_eur is not None:
            keep &= invoices["amount_eur"] <= self.max_amount_eur
        # "has X" is the opposite of "missing X".
        flag("missing_po_ref", None if self.has_po_ref is None else not self.has_po_ref)
        flag("missing_required_po", self.missing_required_po)
        flag("missing_approver", None if self.has_approver is None else not self.has_approver)
        flag("vendor_not_active", self.vendor_not_active)
        flag("is_credit_note", self.is_credit_note)
        return invoices[keep]

    def describe(self) -> str:
        """Plain-English summary of the filters, e.g. 'country is Spain; no PO reference'."""
        parts: list[str] = []

        def one_of(label: str, values: list[str] | None) -> None:
            if values:
                parts.append(f"{label} is {' or '.join(values)}")

        one_of("invoice", self.invoice_numbers)
        one_of("vendor ID", self.vendor_ids)
        if self.vendor_name_contains:
            parts.append(f"vendor name contains '{self.vendor_name_contains}'")
        one_of("vendor country", self.countries)
        one_of("vendor status", self.vendor_statuses)
        one_of("currency", self.currencies)
        one_of("cost centre", self.cost_centers)
        one_of("approver", self.approvers)
        if self.description_contains:
            parts.append(f"description contains '{self.description_contains}'")
        if self.date_from or self.date_to:
            parts.append(f"invoice date {self.date_from or 'start'} to {self.date_to or 'end'}")
        if self.min_amount_eur is not None:
            parts.append(f"EUR amount at least {self.min_amount_eur:,.2f}")
        if self.max_amount_eur is not None:
            parts.append(f"EUR amount at most {self.max_amount_eur:,.2f}")
        for value, yes, no in (
            (self.has_po_ref, "has a PO reference", "no PO reference"),
            (self.missing_required_po, "no PO reference although EUR 1,000+ (§2.1)", "PO requirement met"),
            (self.has_approver, "has an approver", "no approver recorded"),
            (self.vendor_not_active, "vendor currently INACTIVE or ON_HOLD", "vendor currently ACTIVE"),
            (self.is_credit_note, "credit notes only", "credit notes excluded"),
        ):
            if value is not None:
                parts.append(yes if value else no)
        return "; ".join(parts) if parts else "all 2025 invoices"
