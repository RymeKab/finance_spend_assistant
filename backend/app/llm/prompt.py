"""
Builds the system prompt (Claude's standing instructions) from the template file.

The template lives in prompts/system_v3.md, so it can be read and reviewed like
any other document. This module only fills in the {{PLACEHOLDERS}}: the full
policy text with clause anchors, the date range, and the values Claude can
filter on.

PROMPT_VERSION goes out with every response and into the audit log. If the
prompt changes, bump the version (system_v4.md, "ask-v4"), so every answer can
be traced back to the exact instructions that produced it.
"""

from __future__ import annotations

from pathlib import Path

from app.data.loader import Dataset
from app.policy.parser import Policy

# v2: credit notes reported separately, not netted (§6.1); PO breach only from EUR 1,000 (§2.1).
# v3: three gaps between the data and the policy are stated, never guessed: no reporting date
#     (the §6.1 90-day rule), vendor status is today's only (§4.1), bands use the invoice amount (§3).
# Older versions are kept in prompts/ so older audit-log entries can still be traced to their exact prompt.
PROMPT_VERSION = "ask-v3"
TEMPLATE_PATH = Path(__file__).parent / "prompts" / "system_v3.md"


def _listing(values) -> str:
    return ", ".join(sorted(str(v) for v in values if v))


def build_system_prompt(dataset: Dataset, policy: Policy, max_rounds: int) -> str:
    invoices = dataset.invoices
    first, last = dataset.period
    replacements = {
        "{{MAX_ROUNDS}}": str(max_rounds),
        "{{INVOICE_COUNT}}": str(len(invoices)),
        "{{VENDOR_COUNT}}": str(invoices["vendor_id"].nunique()),
        "{{PERIOD_START}}": first.isoformat(),
        "{{PERIOD_END}}": last.isoformat(),
        "{{COUNTRIES}}": _listing(dataset.vendors["country"].unique()),
        "{{CURRENCIES}}": _listing(invoices["currency"].unique()),
        "{{COST_CENTERS}}": _listing(invoices["cost_center"].dropna().unique()),
        "{{APPROVERS}}": _listing(invoices["approved_by"].dropna().unique()),
        "{{FX_BASIS}}": dataset.fx.basis_description,
        "{{POLICY}}": policy.prompt_text(),
    }
    prompt = TEMPLATE_PATH.read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    if "{{" in prompt:
        raise ValueError("The system prompt still contains an unfilled {{PLACEHOLDER}}.")
    return prompt
