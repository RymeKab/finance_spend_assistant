"""Numeric grounding: figures are recognised, identifiers are ignored, rounding is allowed."""

import pytest

from app.validators import extract_figures, ungrounded_figures


def values(text):
    return [f.value for f in extract_figures(text)]


def test_figures_are_parsed_with_separators_and_units():
    assert values("EUR 1,131,810.23 and 6.9 million and 12k") == [1131810.23, 6_900_000.0, 12_000.0]


def test_written_dates_are_not_figures():
    assert values("Invoiced on 31 January 2025, paid March 14th.") == []


def test_identifiers_dates_clauses_years_and_small_counts_are_ignored():
    text = "INV-20071 dated 2025-02-01 under §3.1 and sections 2.1–2.3 (PO-78935, CC-IT-550, V-1001) in 2025: top 5, q1"
    assert values(text) == []


def test_a_copied_figure_is_grounded():
    assert ungrounded_figures("Spend was EUR 2,631,350.72.", [{"spend_eur": 2631350.72}]) == []


def test_rounded_figures_are_accepted_within_their_precision():
    assert ungrounded_figures("About EUR 2.6 million.", [2631350.72]) == []
    assert ungrounded_figures("About EUR 2.6 million.", [2_900_000]) == ["2.6 million"]


def test_an_invented_figure_is_flagged():
    assert ungrounded_figures("Total EUR 3,000,000.00 across 49 invoices.", [{"spend_eur": 2631350.72, "count": 49}]) == [
        "3,000,000.00"
    ]


def test_credit_notes_match_regardless_of_sign():
    assert ungrounded_figures("A credit note of EUR 52,749.39.", [-52749.39]) == []


def test_figures_from_the_question_and_policy_count_as_sources():
    question = "Who can approve an invoice of EUR 60,000?"
    policy = "| 50,000.01 – 250,000 | Finance Director |"
    answer = "EUR 60,000 falls in the 50,000.01 – 250,000 band."
    assert ungrounded_figures(answer, [question, policy]) == []

# Invoice numbers are IDs, not amounts, however Claude writes them.
@pytest.mark.parametrize(
    "answer",
    [
        "INV-20073 has no approver.",
        "INV\u201120073 has no approver.",  # non-breaking hyphen (looks identical)
        "INV\u201320073 has no approver.",  # en dash
        "INV 20073 has no approver.",
        "**INV**-20073 has no approver.",
        "Invoices INV-20038, 20073 have no approver.",  # prefix written once
    ],
)
def test_invoice_numbers_are_never_mistaken_for_figures(answer):
    sources = [{"rows": [{"invoice_number": "INV-20073"}, {"invoice_number": "INV-20038"}]}]
    assert ungrounded_figures(answer, sources) == []


def test_a_bare_number_counts_as_an_id_only_if_that_id_is_in_the_results():
    sources = [{"rows": [{"invoice_number": "INV-20073"}]}]
    assert ungrounded_figures("Invoice 20074 has no approver.", sources) == ["20074"]
    assert ungrounded_figures("It cost EUR 20,073.00.", sources) == ["20,073.00"]  # amounts are still checked