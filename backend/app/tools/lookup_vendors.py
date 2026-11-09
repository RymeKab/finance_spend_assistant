"""
Tool: lookup_vendors. Reads the vendor master: name, country, category, status.

Answers questions like:
  "Which vendors are based in Spain?"   countries=["Spain"]
  "Is Crown Travel Partners active?"    name_contains="crown"

It also counts each vendor's 2025 invoices, so Claude can tell a vendor with no
invoices apart from one that doesn't exist.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.data.loader import Dataset
from app.tools.base import ToolResult
from app.tools.filters import VendorStatus


class LookupVendorsInput(BaseModel):
    """Parameters Claude sends to lookup_vendors. Leave everything empty to list all vendors."""

    model_config = ConfigDict(extra="forbid")

    name_contains: str | None = Field(None, description="Case-insensitive part of the vendor name.")
    vendor_ids: list[str] | None = Field(None, description="Exact vendor IDs, e.g. ['V-1006'].")
    countries: list[str] | None = Field(None, description="Countries, e.g. ['Spain'].")
    statuses: list[VendorStatus] | None = Field(None, description="Vendor statuses.")
    categories: list[str] | None = Field(None, description="Vendor categories, e.g. ['Logistics'].")


def run_lookup_vendors(params: LookupVendorsInput, dataset: Dataset, query_id: str) -> ToolResult:
    vendors = dataset.vendors.copy()
    if params.name_contains:
        vendors = vendors[vendors["vendor_name"].str.contains(params.name_contains, case=False, regex=False)]
    for column, values in (("vendor_id", params.vendor_ids), ("country", params.countries),
                           ("status", params.statuses), ("category", params.categories)):
        if values:
            vendors = vendors[vendors[column].str.lower().isin({v.lower() for v in values})]

    invoice_counts = dataset.invoices.groupby("vendor_id")["invoice_number"].count()
    rows = [
        {
            "vendor_id": v["vendor_id"],
            "vendor": v["vendor_name"],
            "country": v["country"],
            "category": v["category"],
            "status": v["status"],
            "invoices_2025": int(invoice_counts.get(v["vendor_id"], 0)),
        }
        for v in vendors.sort_values("vendor_id").to_dict("records")
    ]

    conditions = [
        f"name contains '{params.name_contains}'" if params.name_contains else "",
        f"ID is {' or '.join(params.vendor_ids)}" if params.vendor_ids else "",
        f"country is {' or '.join(params.countries)}" if params.countries else "",
        f"status is {' or '.join(params.statuses)}" if params.statuses else "",
        f"category is {' or '.join(params.categories)}" if params.categories else "",
    ]
    described = "; ".join(c for c in conditions if c) or "all vendors"
    return ToolResult(
        query_id=query_id,
        tool="lookup_vendors",
        params=params.model_dump(mode="json", exclude_none=True),
        description=f"Vendor master lookup ({len(rows)} found). Conditions: {described}.",
        rows=rows,
        totals={"vendors_found": len(rows)},
    )
