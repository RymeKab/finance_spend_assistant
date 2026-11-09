"""
Numeric grounding: checks that every number in an answer can be traced to a source.

Why this exists
---------------
The tools compute every figure, but Claude still writes the sentence that
contains it. This check catches the cases where a number in that sentence came
from somewhere else: a typo, a figure Claude worked out itself (a sum, a
percentage), or one it made up.

How it works
------------
1. Pull every number out of the answer text ("EUR 1,131,810.23", "1.2 million", "25").
2. Collect every number in the trusted sources: the tool results, the policy text
   and the question itself (if the analyst says "EUR 60,000", repeating it is fine).
3. A number in the answer that matches none of them, allowing for rounding,
   becomes an "unverified figure" warning, shown in amber in the UI.

Things that look like numbers but aren't figures are ignored first: invoice and
PO numbers (INV-20071), dates (2025-03-09, 31 January), clause references (§3.1), years
(2025) and small whole numbers up to 12 (for example "top 5" or "3 currencies").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

# Patterns removed before looking for figures (identifiers, dates, references).
_NOISE = [
    re.compile(r"\b[A-Za-z]{1,4}(?:-[A-Za-z]{1,4})*-\d+\b"),  # INV-20071, PO-78935, CC-IT-550, V-1001, FIN-POL-014
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),  # 2025-03-09
    re.compile(r"(?i)\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"),  # 31 January
    re.compile(r"(?i)\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?\b"),  # January 31
    re.compile(r"§\s*\d+(?:\.\d+)*(?:\s*(?:[–-]|to|and|,)\s*\d+(?:\.\d+)*)*"),  # §3.1, §2.1–2.3
    re.compile(r"(?i)\b(?:sections?|clauses?)\s+\d+(?:\.\d+)*(?:\s*(?:[–-]|to|and|,)\s*\d+(?:\.\d+)*)*"),
    re.compile(r"\bQ[1-4]\b"),  # quarters
    re.compile(r"\bq\d+\b"),  # query IDs
    re.compile(r"(?i)\bv\d+(?:\.\d+)*\b"),  # versions
]

_NUMBER = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?"
    r"(?:\s*(%|k\b|K\b|m\b|M\b|mn\b|million\b|thousand\b|bn\b|billion\b))?"
)
_MULTIPLIERS = {"k": 1e3, "K": 1e3, "thousand": 1e3, "m": 1e6, "M": 1e6, "mn": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9}

# Claude sometimes writes "INV‑20073" with a look-alike dash (non-breaking hyphen, en dash...)
# or a non-breaking space. Turn them into the plain characters before looking for IDs.
_LOOKALIKES = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
                             "\u2212": "-", "\u00a0": " "})
# An ID's number, e.g. "20073" in "INV-20073", used to recognise IDs written without their prefix.
_ID_NUMBER = re.compile(r"\b[A-Za-z]{1,4}(?:-[A-Za-z]{1,4})*-(\d+)\b")


SMALL_INTEGER_LIMIT = 12  # whole numbers up to this are treated as counts/ranks, not figures
RELATIVE_TOLERANCE = 0.005  # 0.5%


@dataclass(frozen=True)
class Figure:
    raw: str  # as written, e.g. "1.2 million"
    value: float  # e.g. 1200000.0
    precision: float  # half of the last written digit, e.g. 50000 for "1.2 million"


def _strip_noise(text: str) -> str:
    # Look-alike dashes become "-", and bold/code markers go ("**INV**-20073" -> "INV-20073").
    text = text.translate(_LOOKALIKES).replace("*", "").replace("`", "")
    text = re.sub(r"\b(INV|PO)\s+(\d+)\b", r"\1-\2", text)  # "INV 20073" -> "INV-20073"
    for pattern in _NOISE:
        text = pattern.sub(" ", text)
    return text


def _all_strings(node: Any) -> Iterable[str]:
    """Every piece of text inside nested dicts and lists."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for item in node.values():
            yield from _all_strings(item)
    elif isinstance(node, (list, tuple, set)):
        for item in node:
            yield from _all_strings(item)


def extract_figures(text: str, *, skip_trivial: bool = True) -> list[Figure]:
    """Find the numbers in a piece of text."""
    figures: list[Figure] = []
    for match in _NUMBER.finditer(_strip_noise(text)):
        whole, decimals, unit = match.group(1), match.group(2) or "", match.group(3) or ""
        value = float(whole.replace(",", "") + ("." + decimals if decimals else ""))
        multiplier = _MULTIPLIERS.get(unit, 1.0)
        is_plain_integer = not decimals and "," not in whole and not unit
        if skip_trivial and is_plain_integer and (value <= SMALL_INTEGER_LIMIT or 1900 <= value <= 2100):
            continue
        precision = 0.5 * 10 ** (-len(decimals)) * multiplier
        figures.append(Figure(match.group(0).strip(), value * multiplier, precision))
    return figures


def known_values(sources: Iterable[Any]) -> list[float]:
    """Every number found in the trusted sources (nested dicts/lists/strings), as absolute values."""
    values: list[float] = []

    def walk(node: Any) -> None:
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, (int, float)):
            values.append(abs(float(node)))
        elif isinstance(node, str):
            values.extend(abs(f.value) for f in extract_figures(node, skip_trivial=False))
        elif isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, (list, tuple, set)):
            for item in node:
                walk(item)

    for source in sources:
        walk(source)
    return values


def ungrounded_figures(answer: str, sources: Iterable[Any]) -> list[str]:
    """Figures in `answer` that match nothing in `sources`. An empty list means fully grounded."""
    sources = list(sources)
    trusted = known_values(sources)
    # Numbers of the IDs in the results (INV-20073 -> "20073"): a bare "20073" in the answer is that ID, not an amount.
    id_numbers = {m.group(1) for text in _all_strings(sources) for m in _ID_NUMBER.finditer(text.translate(_LOOKALIKES))}
    missing: list[str] = []
    for figure in extract_figures(answer):
        if figure.raw.isdigit() and figure.raw in id_numbers:
            continue
        target = abs(figure.value)
        grounded = any(abs(target - v) <= max(figure.precision, RELATIVE_TOLERANCE * v) for v in trusted)
        if not grounded and figure.raw not in missing:
            missing.append(figure.raw)
    return missing
