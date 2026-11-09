"""The policy is split into citable clauses, quoted verbatim."""

from app.policy.parser import normalise_reference


def test_all_clauses_found(policy):
    assert list(policy.clauses) == [
        "1", "2", "2.1", "2.2", "2.3", "3", "3.1", "4", "4.1", "4.2", "4.3",
        "5", "5.1", "5.2", "6", "6.1", "7", "7.1", "7.2", "8", "8.1", "8.2", "9", "9.1",
    ]


def test_clause_text_is_verbatim(policy):
    assert policy.get("7.2").text == "Self-approval is prohibited at all thresholds."
    assert policy.get("7.2").section_title == "Segregation of Duties"
    assert policy.get("3").text.startswith("| Invoice / PO Value (EUR) | Required Approver |")


def test_section_without_intro_holds_the_whole_section(policy):
    assert policy.get("2").text.startswith("2.1 All purchases")
    assert "2.3 Recurring services" in policy.get("2").text


def test_loose_references_are_understood(policy):
    for reference in ("3.1", "§3.1", "§ 3.1", "Section 3.1", "3.1."):
        assert normalise_reference(reference) == "3.1"
        assert policy.get(reference) is not None
    assert policy.get("§99") is None


def test_prompt_text_has_anchors_and_no_duplicates(policy):
    text = policy.prompt_text()
    assert "[§2.1] All purchases" in text
    assert "[§3] | Invoice / PO Value" in text
    assert text.count("Self-approval is prohibited") == 1  # §7 copy is not repeated
