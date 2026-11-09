"""
An independent re-implementation of the core numbers, used to check the tools.

It deliberately does NOT import anything from `app`. It reads the raw CSV files
and computes EUR amounts its own way (pandas merge_asof instead of the app's
lookup table). If a tool has a bug, the two disagree and a test fails, instead
of the bug being copied into the expected answer.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def reference_invoices() -> pd.DataFrame:
    invoices = pd.read_csv(DATA_DIR / "invoices_2025_clean.csv")
    vendors = pd.read_csv(DATA_DIR / "vendor_master.csv")
    # The ECB file is wide (Date, USD, GBP): reshape it to one row per date and currency.
    wide = pd.read_csv(DATA_DIR / "ecb_eur_rates_2025.csv")
    rates = wide.melt(id_vars="Date", var_name="currency", value_name="rate_per_eur").dropna()
    rates["date"] = pd.to_datetime(rates["Date"])

    invoices["invoice_date"] = pd.to_datetime(invoices["invoice_date"])
    eur_rates = pd.DataFrame({"date": [pd.Timestamp("2000-01-01")], "currency": ["EUR"], "rate_per_eur": [1.0]})
    rates = pd.concat([rates[["date", "currency", "rate_per_eur"]], eur_rates]).sort_values("date")

    # For each invoice: the latest rate for its currency dated on or before the invoice date.
    invoices = pd.merge_asof(
        invoices.sort_values("invoice_date"), rates, left_on="invoice_date", right_on="date", by="currency",
        direction="backward",
    )
    invoices["amount_eur"] = (invoices["amount"] / invoices["rate_per_eur"]).round(2)
    return invoices.merge(vendors[["vendor_id", "country", "status"]], on="vendor_id", how="left")
