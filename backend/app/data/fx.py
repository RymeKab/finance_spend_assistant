"""
Currency conversion to EUR.

Why this exists
---------------
Invoices are in EUR, GBP and USD. Policy §5.1 says everything is reported in EUR,
converted "at the ECB reference rate on the invoice date". Adding up raw amounts
in different currencies would give wrong totals, so every amount is converted
exactly once, when the data is loaded.

Where the rates come from
-------------------------
data/ecb_eur_rates_2025.csv: the official ECB euro reference rates for every
business day of 2025, downloaded from the ECB and read exactly as downloaded
(a Date column, then one column per currency). See data/SOURCES.md.

How a rate is chosen
--------------------
For each invoice we use the latest rate dated on or before the invoice date.
The ECB publishes no rate on weekends and TARGET holidays, so an invoice dated
on one of those days uses the previous business day's rate.

Rates are "units of foreign currency per 1 EUR", as the ECB quotes them:
    amount_eur = amount / rate_per_eur
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

BASE_CURRENCY = "EUR"

ECB_BASIS = "ecb_daily_reference"

# Human-readable description of each rate source, shown in /summary and in every answer's assumptions.
BASIS_DESCRIPTIONS = {
    ECB_BASIS: "ECB euro reference rate on the invoice date (previous business day on weekends and holidays)",
}


@dataclass(frozen=True)
class FxRate:
    """One exchange rate as applied to one amount."""

    currency: str
    rate_per_eur: float  # 1 EUR = rate_per_eur units of `currency`
    rate_date: date  # the date of the rate actually used
    basis: str  # where the rate comes from (see BASIS_DESCRIPTIONS)


class FxTable:
    """All known exchange rates, with a lookup by currency and date."""

    def __init__(self, rates: pd.DataFrame):
        # For each currency keep two parallel, date-sorted lists so we can binary-search.
        self._dates: dict[str, list[date]] = {}
        self._rates: dict[str, list[tuple[float, str]]] = {}
        for currency, group in rates.sort_values("date").groupby("currency"):
            self._dates[currency] = list(group["date"])
            self._rates[currency] = list(zip(group["rate_per_eur"].astype(float), group["basis"]))
        self.bases = sorted(set(rates["basis"]))

    @classmethod
    def from_ecb_csv(cls, path: Path) -> "FxTable":
        """Read the ECB rates file exactly as downloaded.

        Layout: a `Date` column (YYYY-MM-DD), then one column per currency, e.g.
            Date,USD,GBP
            2025-10-20,1.1655,0.8691
        Each cell is the ECB reference rate: units of that currency per 1 EUR.
        """
        wide = pd.read_csv(path)
        if "Date" not in wide.columns or len(wide.columns) < 2:
            raise ValueError(f"{path.name}: expected a 'Date' column followed by one column per currency")
        wide["Date"] = pd.to_datetime(wide["Date"], format="%Y-%m-%d").dt.date
        if not wide["Date"].is_unique:
            raise ValueError(f"{path.name}: a date appears more than once")

        # One row per (date, currency): the shape the lookup below works with.
        rates = wide.melt(id_vars="Date", var_name="currency", value_name="rate_per_eur").rename(columns={"Date": "date"})
        rates["currency"] = rates["currency"].str.upper().str.strip()
        rates["rate_per_eur"] = pd.to_numeric(rates["rate_per_eur"], errors="raise")
        # An empty or N/A cell means the ECB published no rate that day; the previous day's rate applies.
        rates = rates.dropna(subset=["rate_per_eur"])
        if (rates["rate_per_eur"] <= 0).any():
            raise ValueError(f"{path.name}: every exchange rate must be a positive number")
        rates["basis"] = ECB_BASIS
        return cls(rates)

    @property
    def currencies(self) -> list[str]:
        return [BASE_CURRENCY, *sorted(self._dates)]

    @property
    def basis(self) -> str:
        """Short code for where the rates come from ("mixed" if the file combines sources)."""
        return self.bases[0] if len(self.bases) == 1 else "mixed"

    @property
    def basis_description(self) -> str:
        return BASIS_DESCRIPTIONS.get(self.basis, self.basis)

    def rate_for(self, currency: str, on: date) -> FxRate:
        """Return the rate to use for `currency` on day `on`."""
        currency = currency.upper()
        if currency == BASE_CURRENCY:
            return FxRate(BASE_CURRENCY, 1.0, on, "not_needed")
        if currency not in self._dates:
            raise KeyError(f"No exchange rates for currency {currency!r}")
        dates = self._dates[currency]
        # Index of the last rate dated on or before `on`.
        position = bisect.bisect_right(dates, on) - 1
        if position < 0:
            raise KeyError(f"No {currency} rate on or before {on.isoformat()}")
        rate, basis = self._rates[currency][position]
        return FxRate(currency, rate, dates[position], basis)

    def latest_rate(self, currency: str) -> FxRate:
        """The most recent rate in the file (used when a question gives no date)."""
        currency = currency.upper()
        if currency == BASE_CURRENCY:
            return FxRate(BASE_CURRENCY, 1.0, date.today(), "not_needed")
        return self.rate_for(currency, self._dates[currency][-1])

    def to_eur(self, amount: float, currency: str, on: date) -> tuple[float, FxRate]:
        """Convert `amount` to EUR, returning the EUR amount (to the cent) and the rate used."""
        rate = self.rate_for(currency, on)
        return round(amount / rate.rate_per_eur, 2), rate
