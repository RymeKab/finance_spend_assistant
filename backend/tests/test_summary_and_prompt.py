"""GET /summary content, and the system prompt that Claude receives."""

from app.llm.prompt import build_system_prompt
from app.summary import build_summary


def test_summary_totals_are_consistent(dataset):
    summary = build_summary(dataset)
    spend = summary["spend_eur"]
    assert round(spend["gross"] + spend["credit_notes"], 2) == spend["net"]
    assert spend["credit_notes"] < 0 and spend["credit_note_count"] == 2
    # Breakdowns count invoices only; the 2 credit notes are reported separately.
    assert sum(c["invoice_count"] for c in summary["by_currency"]) == 138
    assert round(sum(c["amount_eur"] for c in summary["by_currency"]), 2) == spend["gross"]
    assert {s["status"] for s in summary["by_vendor_status"]} == {"ACTIVE", "INACTIVE", "ON_HOLD"}


def test_summary_control_flags(dataset):
    flags = {f["flag"]: f["invoice_count"] for f in build_summary(dataset)["control_flags"]}
    assert flags == {"missing_required_po": 21, "missing_approver": 25, "vendor_not_active": 29, "is_credit_note": 2}


def test_summary_reports_fx_basis_and_lineage(dataset):
    summary = build_summary(dataset)
    assert summary["fx_basis"].startswith("ECB euro reference rate")
    assert len(summary["source_files"]) == 4


def test_system_prompt_is_complete(dataset, policy):
    prompt = build_system_prompt(dataset, policy, max_rounds=4)
    assert "{{" not in prompt
    assert "[§3.1] Approval is evidenced" in prompt
    assert "2025-01-03 to 2025-12-26" in prompt
    assert "Spain" in prompt and "CC-IT-550" in prompt and "j.smith" in prompt
    assert "What the data does NOT contain" in prompt
    assert "Credit notes are NOT subtracted" in prompt and "missing_required_po" in prompt
