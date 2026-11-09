"""Currency conversion: the right rate is picked for each date (policy §5.1)."""

from datetime import date

import pandas as pd
import pytest

from app.data.fx import FxTable


@pytest.fixture
def daily_rates() -> FxTable:
    # A tiny made-up table: Friday 31 Jan and Monday 3 Feb 2025, no weekend rows (like the ECB).
    return FxTable(pd.DataFrame({
        "date": [date(2025, 1, 31), date(2025, 2, 3), date(2025, 1, 31)],
        "currency": ["USD", "USD", "GBP"],
        "rate_per_eur": [1.04, 1.02, 0.84],
        "basis": ["ecb_daily_reference"] * 3,
    }))


def test_eur_needs_no_conversion(daily_rates):
    amount, rate = daily_rates.to_eur(100.0, "EUR", date(2025, 6, 1))
    assert amount == 100.0 and rate.rate_per_eur == 1.0


def test_rate_on_a_business_day_is_used_as_is(daily_rates):
    rate = daily_rates.rate_for("USD", date(2025, 2, 3))
    assert rate.rate_per_eur == 1.02 and rate.rate_date == date(2025, 2, 3)


def test_weekend_uses_previous_business_day(daily_rates):
    rate = daily_rates.rate_for("USD", date(2025, 2, 1))  # Saturday
    assert rate.rate_date == date(2025, 1, 31) and rate.rate_per_eur == 1.04


def test_conversion_divides_by_the_ecb_quote(daily_rates):
    amount, _ = daily_rates.to_eur(104.0, "USD", date(2025, 1, 31))
    assert amount == 100.0  # 1 EUR = 1.04 USD


def test_missing_rate_is_an_error_not_a_guess(daily_rates):
    with pytest.raises(KeyError):
        daily_rates.rate_for("USD", date(2025, 1, 1))  # before the first rate
    with pytest.raises(KeyError):
        daily_rates.rate_for("CHF", date(2025, 6, 1))  # unknown currency


def test_every_invoice_amount_matches_its_recorded_rate(dataset):
    invoices = dataset.invoices
    recomputed = (invoices["amount"] / invoices["fx_rate_per_eur"]).round(2)
    assert (recomputed - invoices["amount_eur"]).abs().max() < 0.006
    assert (invoices.loc[invoices["currency"] == "EUR", "fx_rate_per_eur"] == 1.0).all()


def test_rate_date_is_never_after_the_invoice_date(dataset):
    invoices = dataset.invoices
    assert (invoices["fx_rate_date"] <= invoices["invoice_date"]).all()


def test_rates_are_labelled_as_ecb(dataset):
    assert dataset.fx.basis == "ecb_daily_reference"
    assert dataset.fx.basis_description.startswith("ECB euro reference rate")


# ----------------------------------------------------- the ECB file, read as downloaded
def test_invoice_uses_the_ecb_rate_of_its_own_date(dataset):
    """INV-20096 (USD credit note, Monday 20 Oct 2025) uses that day's ECB rate, 1.1655."""
    row = dataset.invoices.set_index("invoice_number").loc["INV-20096"]
    assert row["fx_rate_per_eur"] == 1.1655 and row["fx_rate_date"] == date(2025, 10, 20)
    assert row["amount_eur"] == round(row["amount"] / 1.1655, 2)


@pytest.mark.parametrize(
    ("invoice", "rate_date", "rate"),
    [
        ("INV-20071", date(2025, 1, 31), 1.0393),  # Saturday 1 Feb -> Friday 31 Jan
        ("INV-20133", date(2025, 4, 17), 1.1360),  # Good Friday (no ECB rate) -> Thursday 17 Apr
    ],
)
def test_weekends_and_holidays_use_the_previous_business_day(dataset, invoice, rate_date, rate):
    row = dataset.invoices.set_index("invoice_number").loc[invoice]
    assert row["fx_rate_date"] == rate_date and row["fx_rate_per_eur"] == rate


def test_ecb_file_is_read_as_downloaded(tmp_path):
    from app.config import REPO_ROOT

    fx = FxTable.from_ecb_csv(REPO_ROOT / "data" / "ecb_eur_rates_2025.csv")
    assert fx.currencies == ["EUR", "GBP", "USD"]
    # The file writes the 15 January USD rate as "01.03"; it must still be read as 1.03.
    assert fx.rate_for("USD", date(2025, 1, 15)).rate_per_eur == 1.03

    duplicated = tmp_path / "rates.csv"
    duplicated.write_text("Date,USD,GBP\n2025-01-02,1.0321,0.83118\n2025-01-02,1.0321,0.83118\n")
    with pytest.raises(ValueError, match="more than once"):
        FxTable.from_ecb_csv(duplicated)
