"""The four tools, checked against the independent reference in reference.py."""

import pytest

from app.tools import data_tool_definitions, run_tool
from tests.reference import reference_invoices


@pytest.fixture(scope="module")
def ref():
    return reference_invoices()


# ---------------------------------------------------------------------- query_spend
def test_top_5_vendors_match_reference(dataset, ref):
    result = run_tool("query_spend", {"group_by": "vendor", "limit": 5}, dataset, "q1")
    invoices_only = ref[ref["amount"] > 0]
    expected = invoices_only.groupby("vendor_name")["amount_eur"].sum().sort_values(ascending=False).head(5)
    assert [r["vendor"] for r in result.rows] == list(expected.index)
    for row, value in zip(result.rows, expected.values):
        assert row["amount_eur"] == pytest.approx(value, abs=0.05)
    assert result.totals["groups"] == 10
    assert "showing 5 of 10 groups" in result.description


def test_spend_with_spanish_vendors_matches_reference(dataset, ref):
    result = run_tool("query_spend", {"filters": {"countries": ["Spain"]}}, dataset, "q1")
    spain = ref[ref["country"] == "Spain"]
    assert result.totals["spend_eur"] == pytest.approx(spain["amount_eur"].sum(), abs=0.05)
    assert result.totals["invoice_count"] == len(spain) == len(result.invoice_numbers)


# Override 1: unmatched credit notes are reported separately, never subtracted by default (§6.1).
def test_credit_notes_are_not_subtracted_by_default(dataset, ref):
    totals = run_tool("query_spend", {}, dataset, "q1").totals
    assert totals["spend_eur"] == pytest.approx(ref.loc[ref["amount"] > 0, "amount_eur"].sum(), abs=0.05)
    assert totals["invoice_count"] == 138
    assert totals["unmatched_credit_note_count"] == 2
    assert totals["unmatched_credit_notes_eur"] == pytest.approx(ref.loc[ref["amount"] < 0, "amount_eur"].sum(), abs=0.05)
    assert "net_eur" not in totals


def test_credit_notes_are_shown_next_to_their_vendor(dataset):
    rows = run_tool("query_spend", {"group_by": "vendor", "limit": 10}, dataset, "q1").rows
    helix = next(r for r in rows if r["vendor"] == "Helix Consulting AG")
    assert helix["unmatched_credit_notes_eur"] < 0  # both credit notes belong to Helix
    assert all(r["unmatched_credit_notes_eur"] == 0 for r in rows if r is not helix)


def test_net_figure_only_on_request(dataset, ref):
    result = run_tool("query_spend", {"net_credit_notes": True}, dataset, "q1")
    assert result.totals["spend_eur"] == pytest.approx(ref["amount_eur"].sum(), abs=0.05)
    assert result.totals["credit_notes_netted_eur"] < 0
    assert "matching unconfirmed" in result.description


def test_spend_by_currency_keeps_original_amounts(dataset, ref):
    result = run_tool("query_spend", {"group_by": "currency"}, dataset, "q1")
    by_currency = {r["currency"]: r for r in result.rows}
    for currency, group in ref[ref["amount"] > 0].groupby("currency"):
        assert by_currency[currency]["amount_original"] == pytest.approx(group["amount"].sum(), abs=0.05)
        assert by_currency[currency]["invoice_count"] == len(group)


def test_contributing_invoices_follow_the_rows(dataset):
    result = run_tool("query_spend", {"group_by": "vendor", "limit": 1}, dataset, "q1")
    top_vendor_invoices = dataset.invoices[dataset.invoices["vendor_name"] == result.rows[0]["vendor"]]
    assert set(result.invoice_numbers) == set(top_vendor_invoices["invoice_number"])


# --------------------------------------------------------------------- find_invoices
def test_find_invoices_without_approver(dataset, ref):
    result = run_tool("find_invoices", {"filters": {"has_approver": False}, "limit": 50}, dataset, "q1")
    assert result.totals["matching_invoices"] == ref["approved_by"].isna().sum() == 25
    assert all(row["approved_by"] is None for row in result.rows)


def test_find_invoices_reports_the_full_count_when_limited(dataset):
    result = run_tool("find_invoices", {"filters": {"vendor_not_active": True}, "limit": 5}, dataset, "q1")
    assert len(result.rows) == 5
    assert result.totals["matching_invoices"] == len(result.invoice_numbers) == 29
    assert "showing 5 of 29" in result.description


# -------------------------------------------------------------------- lookup_vendors
def test_lookup_vendors_by_country(dataset):
    result = run_tool("lookup_vendors", {"countries": ["Spain"]}, dataset, "q1")
    assert {r["vendor"] for r in result.rows} == {"ClinSupply Iberia S.L.", "PharmaPrint Studios", "Stellar Facilities Mgmt"}
    assert sum(r["invoices_2025"] for r in result.rows) == 49


# -------------------------------------------------------------- approval_requirement
def test_approval_for_a_eur_amount(dataset):
    row = run_tool("approval_requirement", {"amount": 60000}, dataset, "q1").rows[0]
    assert row["required_approver"] == "Finance Director"
    assert row["policy_band_eur"] == "50,000.01 – 250,000"


def test_approval_for_an_invoice_converts_first_and_warns_about_roles(dataset):
    result = run_tool("approval_requirement", {"invoice_number": "INV-20071"}, dataset, "q1")
    row = result.rows[0]
    assert row["currency"] == "USD" and row["amount_eur"] < 50_000
    assert row["required_approver"] == "Department Head"
    assert row["recorded_approver"] == "r.okafor"
    assert any("no approver roles" in note for note in result.notes)
    assert result.invoice_numbers == ["INV-20071"]


def test_approval_for_a_credit_note(dataset):
    result = run_tool("approval_requirement", {"invoice_number": "INV-20029"}, dataset, "q1")
    assert "required_approver" not in result.rows[0]
    assert any("§6.1" in note for note in result.notes)


# --------------------------------------------------------------------- error handling
@pytest.mark.parametrize(
    ("name", "params", "message"),
    [
        ("query_spend", {"group_by": "planet"}, "group_by"),
        ("query_spend", {"filters": {"currencies": ["JPY"]}}, "currencies"),
        ("query_spend", {"surprise": True}, "surprise"),
        ("approval_requirement", {}, "invoice_number or amount"),
        ("approval_requirement", {"invoice_number": "INV-99999"}, "does not exist"),
        ("delete_everything", {}, "Unknown tool"),
    ],
)
def test_bad_requests_become_errors_not_crashes(dataset, name, params, message):
    result = run_tool(name, params, dataset, "q1")
    assert not result.ok and message in result.error
    assert result.for_model() == {"query_id": "q1", "error": result.error}


def test_tool_schemas_are_self_contained():
    import json

    definitions = data_tool_definitions()
    assert [d["name"] for d in definitions] == ["query_spend", "find_invoices", "lookup_vendors", "approval_requirement"]
    assert "$ref" not in json.dumps(definitions)
