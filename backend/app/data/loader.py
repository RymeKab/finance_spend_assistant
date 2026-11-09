"""
Loads the invoice and vendor files once at startup and prepares them for questions.

What happens here, step by step
-------------------------------
1. Read invoices_2025_clean.csv, vendor_master.csv and ecb_eur_rates_2025.csv
   (official ECB daily rates, read exactly as downloaded).
2. Attach each invoice's vendor country, category and status (from the vendor master).
3. Convert every amount to EUR (policy §5.1) and keep the rate that was used.
4. Add yes/no "control flags" that the policy cares about:
     missing_po_ref       no PO number on the invoice (a plain fact, any amount)
     po_required          EUR amount is 1,000 or above, so a PO is required (§2.1)
     missing_required_po  both of the above: the actual policy breach (§2.1-2.2)
     missing_approver     no approver recorded; must be held (§3.1)
     vendor_not_active    vendor is INACTIVE or ON_HOLD; must be escalated (§4.1)
     is_credit_note       negative amount; must be matched to the original (§6.1)
5. Work out the approval band each invoice falls in (§3), after conversion.
6. Fingerprint each source file (SHA-256), so every answer can say exactly which
   version of the data it came from (lineage, policy §8.2).

The resulting table is never modified afterwards. All tools only read it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from app.data.fx import FxTable
from app.policy.approval import PO_REQUIRED_FROM_EUR, required_approval

INVOICES_FILE = "invoices_2025_clean.csv"
VENDORS_FILE = "vendor_master.csv"
FX_FILE = "ecb_eur_rates_2025.csv"  # official ECB daily rates; not part of the data pack (see data/SOURCES.md)
POLICY_FILE = "procurement_policy.md"

NOT_ACTIVE_STATUSES = ("INACTIVE", "ON_HOLD")


@dataclass(frozen=True)
class SourceFile:
    """A source file and its fingerprint, reported in /summary and in every answer."""

    name: str
    sha256: str
    rows: int | None  # None for non-tabular files (the policy)


@dataclass
class Dataset:
    """Everything the tools need: the enriched invoice table, vendors, rates and lineage."""

    invoices: pd.DataFrame
    vendors: pd.DataFrame
    fx: FxTable
    source_files: list[SourceFile]

    @property
    def data_snapshot(self) -> str:
        """One short fingerprint for the whole data set (changes if any file changes)."""
        combined = hashlib.sha256("".join(f.sha256 for f in self.source_files).encode()).hexdigest()
        return f"sha256:{combined[:16]}"

    @property
    def period(self) -> tuple[date, date]:
        return self.invoices["invoice_date"].min(), self.invoices["invoice_date"].max()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _blank_to_none(value: object) -> str | None:
    """Turn empty cells into None, so 'missing' means one thing everywhere."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def load_dataset(data_dir: Path) -> Dataset:
    """Read and enrich the source files. Called once when the app starts."""
    invoices = pd.read_csv(data_dir / INVOICES_FILE, dtype=str)
    vendors = pd.read_csv(data_dir / VENDORS_FILE, dtype=str)
    fx = FxTable.from_ecb_csv(data_dir / FX_FILE)

    # --- Clean types --------------------------------------------------------------
    invoices["amount"] = invoices["amount"].astype(float)
    invoices["invoice_date"] = pd.to_datetime(invoices["invoice_date"]).dt.date
    invoices["currency"] = invoices["currency"].str.upper().str.strip()
    for column in ("po_number", "approved_by", "description", "cost_center"):
        invoices[column] = invoices[column].map(_blank_to_none).astype(object)

    # --- Step 2: attach vendor details (joined on vendor_id, never on name) --------
    vendor_details = vendors.rename(columns={"category": "vendor_category", "status": "vendor_status"})[
        ["vendor_id", "country", "vendor_category", "vendor_status"]
    ]
    invoices = invoices.merge(vendor_details, on="vendor_id", how="left", validate="many_to_one")
    if invoices["vendor_status"].isna().any():
        unknown = sorted(invoices.loc[invoices["vendor_status"].isna(), "vendor_id"].unique())
        raise ValueError(f"Invoices reference vendors missing from the vendor master: {unknown}")

    # --- Step 3: convert to EUR -----------------------------------------------------
    conversions = [fx.to_eur(a, c, d) for a, c, d in zip(invoices["amount"], invoices["currency"], invoices["invoice_date"])]
    invoices["amount_eur"] = [eur for eur, _ in conversions]
    invoices["fx_rate_per_eur"] = [rate.rate_per_eur for _, rate in conversions]
    invoices["fx_rate_date"] = [rate.rate_date for _, rate in conversions]

    # --- Step 4: control flags ------------------------------------------------------
    invoices["is_credit_note"] = invoices["amount"] < 0
    invoices["missing_po_ref"] = invoices["po_number"].isna()
    # A missing PO only breaches the policy at EUR 1,000 or more (§2.1), measured in EUR after conversion.
    invoices["po_required"] = invoices["amount_eur"] >= PO_REQUIRED_FROM_EUR
    invoices["missing_required_po"] = invoices["missing_po_ref"] & invoices["po_required"]
    invoices["missing_approver"] = invoices["approved_by"].isna()
    invoices["vendor_not_active"] = invoices["vendor_status"].isin(NOT_ACTIVE_STATUSES)

    # --- Step 5: approval band (§3), computed on the EUR amount ---------------------
    tiers = [required_approval(eur) for eur in invoices["amount_eur"]]
    invoices["approval_band"] = [t.band if t else None for t in tiers]
    invoices["required_approver"] = [t.approver if t else None for t in tiers]

    invoices["month"] = [d.strftime("%Y-%m") for d in invoices["invoice_date"]]
    invoices = invoices.sort_values("invoice_number").reset_index(drop=True)

    # --- Step 6: lineage ------------------------------------------------------------
    source_files = [
        SourceFile(INVOICES_FILE, _sha256(data_dir / INVOICES_FILE), len(invoices)),
        SourceFile(VENDORS_FILE, _sha256(data_dir / VENDORS_FILE), len(vendors)),
        SourceFile(FX_FILE, _sha256(data_dir / FX_FILE), len(pd.read_csv(data_dir / FX_FILE))),
        SourceFile(POLICY_FILE, _sha256(data_dir / POLICY_FILE), None),
    ]

    return Dataset(invoices=invoices, vendors=vendors, fx=fx, source_files=source_files)
