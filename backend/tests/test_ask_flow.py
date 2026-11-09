"""
The whole question flow (Claude loop + tools + evidence + validators), with a
scripted fake Claude, so every path is tested exactly, offline and for free.
"""

import json

import pytest

from app.assistant import SpendAssistant
from app.config import Settings
from app.errors import LLMBadOutput, LLMNotConfigured, LLMTimeout
from app.llm.client import create_claude_client
from app.llm.prompt import PROMPT_VERSION
from tests.fakes import FakeClaude, submit, text, thinking, tool_use


def make_assistant(settings, script):
    fake = FakeClaude(script)
    return SpendAssistant(settings, lambda _settings: fake), fake


# ------------------------------------------------------------------- happy paths
def test_data_question_gets_server_built_evidence(settings):
    assistant, fake = make_assistant(settings, [
        [text("Checking spend by vendor."), tool_use("query_spend", {"group_by": "vendor", "limit": 5})],
        [submit(status="answered", answer="The top vendor is **BioReagent Direct**.", data_refs=["q1"], policy_refs=["5.1"])],
    ])
    response = assistant.ask("What are our top 5 vendors by total spend in 2025?", "req-1")

    assert response["status"] == "answered"
    assert response["route"] == ["policy", "data"]
    data = response["evidence"]["data"][0]
    assert data["query_id"] == "q1" and len(data["rows"]) == 5
    assert data["invoice_count"] > 50 and data["invoices_truncated"] is True and len(data["invoices"]) == 50
    assert response["evidence"]["policy"][0]["text"].startswith("The Group reporting currency")
    assert any("2 unmatched credit note(s)" in a and "not subtracted" in a for a in response["assumptions"])
    assert response["warnings"] == []
    assert response["meta"]["llm_calls"] == 2 and response["meta"]["tool_calls"] == 1
    # The tool result Claude received is labelled with its query ID.
    tool_reply = fake.requests[1]["messages"][2]["content"][0]
    assert json.loads(tool_reply["content"])["query_id"] == "q1"


def test_policy_only_question_needs_no_data(settings):
    assistant, fake = make_assistant(settings, [
        [submit(status="answered",
                answer="An invoice of EUR 60,000 falls in the 50,000.01 – 250,000 band, so the **Finance Director** "
                       "must approve it (§3). Self-approval is prohibited (§7.2).",
                policy_refs=["3", "7.2"])],
    ])
    response = assistant.ask("Who is allowed to approve an invoice of EUR 60,000?", "req-2")
    assert response["route"] == ["policy"]
    assert [p["clause_id"] for p in response["evidence"]["policy"]] == ["3", "7.2"]
    assert response["warnings"] == []  # 60,000 comes from the question, 50,000.01 from the policy
    assert len(fake.requests) == 1


def test_decline_when_the_data_cannot_answer(settings):
    assistant, _ = make_assistant(settings, [
        [submit(status="insufficient_data",
                answer="I can't tell: the data has no requester field, so self-approval can't be checked (§7.2).",
                policy_refs=["7.1", "7.2"], missing_information=["The requester of each purchase"])],
    ])
    response = assistant.ask("Were any invoices self-approved?", "req-3")
    assert response["status"] == "insufficient_data"
    assert response["missing_information"] == ["The requester of each purchase"]


# ------------------------------------------------------------------ safety nets
def test_figures_without_data_are_sent_back_once(settings):
    assistant, fake = make_assistant(settings, [
        [submit(status="answered", answer="Spend with Spanish vendors is EUR 2,500,000.00.")],  # made up
        [tool_use("query_spend", {"filters": {"countries": ["Spain"]}})],
        [submit(status="answered", answer="See the total in the evidence.", data_refs=["q1"])],
    ])
    response = assistant.ask("What is our total spend with vendors based in Spain?", "req-4")
    correction = fake.requests[1]["messages"][-1]["content"][0]
    assert correction["is_error"] is True and "no data tool was used" in correction["content"]
    assert response["route"] == ["data"]


def test_unknown_citations_are_removed_and_status_downgraded(settings):
    assistant, _ = make_assistant(settings, [
        [submit(status="answered", answer="Approval is needed (§3).", policy_refs=["3", "§12.4"], data_refs=["q7"])],
    ])
    response = assistant.ask("Who approves invoices?", "req-5")
    assert response["status"] == "partial"
    assert [p["clause_id"] for p in response["evidence"]["policy"]] == ["3"]
    assert any("§12.4" in w for w in response["warnings"]) and any("q7" in w for w in response["warnings"])


# Override 6: an unverified figure means the answer can't be shown as complete.
def test_invented_figure_is_flagged_and_downgrades_the_answer(settings):
    assistant, _ = make_assistant(settings, [
        [tool_use("query_spend", {"filters": {"countries": ["Spain"]}})],
        [submit(status="answered", answer="Spain spend is EUR 9,999,999.00.", data_refs=["q1"])],
    ])
    response = assistant.ask("Spend with Spanish vendors?", "req-6")
    assert any("Unverified figure: 9,999,999.00" in w for w in response["warnings"])
    assert response["status"] == "partial"


def test_a_grounded_answer_keeps_its_status(settings):
    # The figure is read from the tool, so the test holds whatever the exchange rates are.
    from app.data.loader import load_dataset
    from app.tools import run_tool

    spain = run_tool("query_spend", {"filters": {"countries": ["Spain"]}}, load_dataset(settings.data_dir), "q0")
    assistant, _ = make_assistant(settings, [
        [tool_use("query_spend", {"filters": {"countries": ["Spain"]}})],
        [submit(status="answered", answer=f"Spain spend is EUR {spain.totals['spend_eur']:,.2f} across 49 invoices.",
                data_refs=["q1"])],
    ])
    response = assistant.ask("Spend with Spanish vendors?", "req-6b")
    assert response["warnings"] == [] and response["status"] == "answered"


# Domain gaps: stated whenever an answer relies on them, never left for the model to guess.
def test_vendor_status_and_approval_band_gaps_are_stated(settings):
    assistant, _ = make_assistant(settings, [
        [tool_use("find_invoices", {"filters": {"vendor_not_active": True}}),
         tool_use("approval_requirement", {"invoice_number": "INV-20071"})],
        [submit(status="answered", answer="The details are in the evidence.", data_refs=["q1", "q2"])],
    ])
    response = assistant.ask("Which invoices come from inactive vendors, and who approves INV-20071?", "req-6c")
    assert any("no status history" in a for a in response["assumptions"])  # §4.1: today's status only
    assert any("Invoice / PO Value" in a for a in response["assumptions"])  # §3: no PO values


def test_ages_from_the_tool_are_grounded_when_a_date_is_given(settings):
    assistant, _ = make_assistant(settings, [
        [tool_use("find_invoices", {"filters": {"is_credit_note": True}, "as_of": "2025-12-31"})],
        [submit(status="answered",
                answer="As of 31 December 2025, INV-20096 is 72 days old and INV-20029 is 48 days old, "
                       "so neither is over 90 days (§6.1).",
                data_refs=["q1"], policy_refs=["6.1"])],
    ])
    response = assistant.ask("Were any unmatched credit notes older than 90 days on 31 December 2025?", "req-6d")
    assert response["warnings"] == [] and response["status"] == "answered"  # 72 and 48 come from the tool
    assert any("counted to 2025-12-31" in a for a in response["assumptions"])


def test_tool_errors_go_back_to_claude(settings):
    assistant, fake = make_assistant(settings, [
        [tool_use("query_spend", {"group_by": "planet"})],
        [tool_use("query_spend", {"group_by": "country"})],
        [submit(status="answered", answer="Spend by country is in the evidence.", data_refs=["q2"])],
    ])
    response = assistant.ask("Spend by country?", "req-7")
    first_reply = fake.requests[1]["messages"][-1]["content"][0]
    assert first_reply["is_error"] is True and "group_by" in first_reply["content"]
    assert [d["query_id"] for d in response["evidence"]["data"]] == ["q2"]


def test_lookups_beyond_the_limit_are_refused(settings):
    rounds = settings.max_tool_rounds
    script = [[tool_use("lookup_vendors", {})] for _ in range(rounds + 1)]  # one round too many
    script.append([submit(status="answered", answer="Done.", data_refs=["q1"])])
    assistant, fake = make_assistant(settings, script)
    response = assistant.ask("List vendors", "req-8")
    refused = fake.requests[-1]["messages"][-1]["content"][0]
    assert refused["is_error"] is True and "limit of data lookups" in refused["content"]
    assert response["meta"]["tool_calls"] == rounds  # the extra request was not run


def test_request_shape_suits_current_models(settings):
    assistant, fake = make_assistant(settings, [
        [submit(status="out_of_scope", answer="I can only help with invoices and the policy.")],
    ])
    assistant.ask("Write a poem", "req-8b")
    request = fake.requests[0]
    assert request["tool_choice"] == {"type": "auto"}  # current models reject forced tool choice
    assert "temperature" not in request  # current models reject sampling parameters
    assert request["output_config"] == {"effort": "medium"}
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
    final_tool = next(t for t in request["tools"] if t["name"] == "submit_answer")
    assert final_tool["strict"] is True
    assert 0 < request["timeout"] <= settings.llm_timeout_seconds


def test_thinking_blocks_are_passed_back_unchanged(settings):
    assistant, fake = make_assistant(settings, [
        [thinking(), tool_use("lookup_vendors", {"countries": ["Spain"]})],
        [submit(status="answered", answer="Three vendors are based in Spain.", data_refs=["q1"])],
    ])
    assistant.ask("Which vendors are in Spain?", "req-8c")
    assistant_turn = fake.requests[1]["messages"][1]
    assert assistant_turn["role"] == "assistant"
    assert assistant_turn["content"][0] == {"type": "thinking", "thinking": "Let me work out which tool fits.",
                                            "signature": "sig-abc123"}


def test_a_reply_cut_off_by_the_token_limit_is_a_clear_error(settings):
    assistant, _ = make_assistant(settings, [
        {"blocks": [tool_use("submit_answer", {"status": "answ"})], "stop_reason": "max_tokens"},
    ])
    with pytest.raises(LLMBadOutput, match="LLM_MAX_TOKENS"):
        assistant.ask("Anything", "req-8d")


def test_overall_deadline(settings):
    from dataclasses import replace

    assistant, _ = make_assistant(replace(settings, ask_deadline_seconds=0), [])
    with pytest.raises(LLMTimeout):
        assistant.ask("Anything", "req-8e")


def test_plain_text_reply_is_corrected(settings):
    assistant, _ = make_assistant(settings, [
        [text("The answer is the Finance Director.")],
        [submit(status="answered", answer="The **Finance Director** (§3).", policy_refs=["3"])],
    ])
    assert assistant.ask("Who approves EUR 60,000?", "req-9")["status"] == "answered"


def test_repeated_invalid_answers_end_with_a_clear_error(settings):
    assistant, _ = make_assistant(settings, [
        [submit(answer="missing status")],
        [submit(status="maybe", answer="still invalid")],
        [text("I'll just say it in words.")],
    ])
    with pytest.raises(LLMBadOutput):
        assistant.ask("Anything", "req-10")


def test_uncited_queries_are_still_shown(settings):
    assistant, _ = make_assistant(settings, [
        [tool_use("lookup_vendors", {"countries": ["Spain"]})],
        [submit(status="answered", answer="Three vendors are based in Spain.")],
    ])
    response = assistant.ask("Which vendors are in Spain?", "req-11")
    assert [d["query_id"] for d in response["evidence"]["data"]] == ["q1"]
    assert any("did not cite its data queries" in w for w in response["warnings"])


# ------------------------------------------------------------ configuration, audit
def test_missing_key_gives_a_clear_error(tmp_path):
    settings = Settings(key_1=None, log_dir=tmp_path)
    assistant = SpendAssistant(settings, create_claude_client)
    with pytest.raises(LLMNotConfigured, match="key_1"):
        assistant.ask("Anything", "req-12")
    assert assistant.summary()["invoice_count"] == 140  # the summary still works


def test_every_question_is_written_to_the_audit_log(settings):
    assistant, _ = make_assistant(settings, [
        [tool_use("query_spend", {"group_by": "currency"})],
        [submit(status="answered", answer="Breakdown in the evidence.", data_refs=["q1"])],
    ])
    assistant.ask("Spend by currency?", "req-13")
    entry = json.loads((settings.log_dir / "audit.jsonl").read_text().strip().splitlines()[-1])
    assert entry["request_id"] == "req-13" and entry["prompt_version"] == PROMPT_VERSION
    assert entry["tool_calls"] == [{"query_id": "q1", "tool": "query_spend",
                                    "params": {"filters": {}, "group_by": "currency", "sort": "amount_desc", "limit": 50,
                                               "net_credit_notes": False},
                                    "error": None}]
    assert entry["data_snapshot"].startswith("sha256:")
    assert "test-key" not in json.dumps(entry)  # the API key is never logged
