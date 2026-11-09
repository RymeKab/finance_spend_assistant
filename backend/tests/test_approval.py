"""Approval bands (policy §3): exact edges, and the bands still match the policy text."""

import pytest

from app.policy.approval import APPROVAL_TIERS, PO_REQUIRED_FROM_EUR, required_approval


@pytest.mark.parametrize(
    ("amount_eur", "approver"),
    [
        (0.01, "Cost Center Owner"),
        (5_000.00, "Cost Center Owner"),  # "Up to 5,000" includes 5,000
        (5_000.01, "Department Head"),
        (50_000.00, "Department Head"),
        (50_000.01, "Finance Director"),
        (60_000.00, "Finance Director"),
        (250_000.00, "Finance Director"),
        (250_000.01, "CFO + Procurement Excellence review"),
    ],
)
def test_band_edges(amount_eur, approver):
    assert required_approval(amount_eur).approver == approver


def test_float_noise_does_not_push_an_amount_over_an_edge():
    assert required_approval(5_000.0000001).approver == "Cost Center Owner"


def test_credit_notes_have_no_band():
    assert required_approval(-52_749.39) is None
    assert required_approval(0) is None


def test_bands_match_the_policy_text(policy):
    table = policy.get("3").text
    for tier in APPROVAL_TIERS:
        assert f"| {tier.band} | {tier.approver} |" in table


def test_conversion_moves_invoices_across_a_band(dataset):
    """The two examples from the data review: face value and EUR value fall in different bands."""
    invoices = dataset.invoices.set_index("invoice_number")
    # GBP 47,368.81: under 50k at face value, over EUR 50,000 once converted.
    assert invoices.loc["INV-20065", "amount"] < 50_000 < invoices.loc["INV-20065", "amount_eur"]
    assert invoices.loc["INV-20065", "required_approver"] == "Finance Director"
    # USD 51,057.79: over 50k at face value, under EUR 50,000 once converted.
    assert invoices.loc["INV-20071", "amount"] > 50_000 > invoices.loc["INV-20071", "amount_eur"]
    assert invoices.loc["INV-20071", "required_approver"] == "Department Head"


def test_po_threshold_matches_the_policy_text(policy):
    assert PO_REQUIRED_FROM_EUR == 1_000.00
    assert "**EUR 1,000 or above**" in policy.get("2.1").text
