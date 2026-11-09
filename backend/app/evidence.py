"""
Builds "What this answer is based on": the evidence shown under every answer
(POST /ask, steps 6-7 on the diagram).

This is the ONLY place where evidence is created. Claude supplies clause IDs and
query IDs; this module turns them into:

  * policy evidence: the exact clause text from the policy file,
  * data evidence: the computation in plain English, the result table, and the
    actual invoices behind it,
  * assumptions: standard ones added by the server (FX basis, how credit notes
    were treated) plus any Claude stated,
  * warnings: citations that didn't check out, and figures that match no source.

An answer with a removed citation or an unverified figure can't be marked
"answered": it is downgraded to "partial". In finance, a number nobody can trace
shouldn't look like a complete answer.

The route ("policy", "data" or both) is worked out from the evidence that was
actually used. It is never the model's own claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.data.loader import Dataset
from app.llm.orchestrator import OrchestratorResult
from app.policy.parser import Policy, normalise_reference
from app.tools.base import ToolResult
from app.tools.find_invoices import invoice_rows
from app.validators import ungrounded_figures

MAX_EVIDENCE_INVOICES = 50
EVIDENCE_INVOICE_COLUMNS = [
    "invoice_number", "invoice_date", "vendor_name", "vendor_status", "description",
    "amount", "currency", "fx_rate_per_eur", "amount_eur", "po_number", "approved_by",
    "approval_band", "missing_po_ref", "missing_required_po", "missing_approver", "vendor_not_active", "is_credit_note",
]
SPEND_TOOLS = {"query_spend", "find_invoices", "approval_requirement"}


@dataclass
class Evidence:
    status: str
    route: list[str]
    policy: list[dict[str, Any]] = field(default_factory=list)
    data: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_evidence(question: str, result: OrchestratorResult, dataset: Dataset, policy: Policy) -> Evidence:
    submission = result.submission
    warnings: list[str] = []

    # --- 1. Policy citations -> verbatim clauses ------------------------------------
    policy_evidence, seen = [], set()
    for reference in submission.policy_refs:
        clause = policy.get(reference)
        if clause is None:
            warnings.append(f"Removed citation §{normalise_reference(reference)}: there is no such clause in the policy.")
        elif clause.clause_id not in seen:
            seen.add(clause.clause_id)
            policy_evidence.append({"clause_id": clause.clause_id, "section_title": clause.section_title, "text": clause.text})

    # --- 2. Data citations -> real rows -----------------------------------------------
    successful = {r.query_id: r for r in result.tool_results if r.ok}
    cited: list[ToolResult] = []
    for reference in submission.data_refs:
        query = successful.get(reference.strip())
        if query is None:
            warnings.append(f"Removed citation {reference}: no successful query with that ID ran for this answer.")
        elif query not in cited:
            cited.append(query)
    if not cited and successful:
        # Be transparent rather than hide work: show every query that ran.
        cited = list(successful.values())
        warnings.append("The answer did not cite its data queries, so every query that ran is shown.")
    data_evidence = [_data_entry(query, dataset) for query in cited]

    # --- 3. Assumptions: the server's standard ones first, then Claude's ------------------
    assumptions = _standard_assumptions(cited, dataset) + list(submission.assumptions)
    assumptions = list(dict.fromkeys(a.strip() for a in assumptions if a and a.strip()))  # de-duplicate

    # --- 4. Numeric grounding: every figure must match a source ------------------------
    sources: list[Any] = [question, policy.prompt_text()]
    sources += [r.for_model() | {"params": r.params} for r in result.tool_results if r.ok]
    sources += [entry["invoices"] for entry in data_evidence]
    unverified = ungrounded_figures(submission.answer, sources)
    for figure in unverified:
        warnings.append(f"Unverified figure: {figure} does not match any query result or the policy.")

    # --- 5. Status and route -------------------------------------------------------------
    # Anything that didn't check out (a removed citation, an untraceable number) means the
    # answer can't be shown as complete.
    status = submission.status
    cited_something_invalid = any(w.startswith("Removed citation") for w in warnings)
    if status == "answered" and (cited_something_invalid or unverified):
        status = "partial"
    if status == "answered" and not policy_evidence and not data_evidence:
        warnings.append("This answer cites no policy clause and no data query.")

    route = (["policy"] if policy_evidence else []) + (["data"] if data_evidence else [])
    return Evidence(status, route, policy_evidence, data_evidence, assumptions, warnings)


def _data_entry(query: ToolResult, dataset: Dataset) -> dict[str, Any]:
    """One data query as shown in the evidence panel, with the real invoices behind it."""
    shown = query.invoice_numbers[:MAX_EVIDENCE_INVOICES]
    # Look the invoices up by number, keeping the order the tool returned them in.
    invoices = dataset.invoices.set_index("invoice_number").loc[shown].reset_index() if shown else dataset.invoices.head(0)
    return {
        "query_id": query.query_id,
        "tool": query.tool,
        "description": query.description,
        "params": query.params,
        "rows": query.rows,
        "totals": query.totals,
        "notes": query.notes,
        "invoices": invoice_rows(invoices, EVIDENCE_INVOICE_COLUMNS),
        "invoice_count": len(query.invoice_numbers),
        "invoices_truncated": len(query.invoice_numbers) > MAX_EVIDENCE_INVOICES,
    }


# Gaps between the data and the policy, stated whenever an answer relies on them.
VENDOR_STATUS_ASSUMPTION = (
    "Vendor status is the vendor master's current status. The data has no status history, so it can't show "
    "whether a vendor was ACTIVE when an invoice was processed (§4.1)."
)
APPROVAL_BAND_ASSUMPTION = (
    "Approval bands use the invoice's EUR amount. The §3 table refers to \"Invoice / PO Value\", but PO values "
    "aren't in the data, so a band based on the PO can't be checked."
)


def _uses_vendor_status(query: ToolResult) -> bool:
    filters = query.params.get("filters", {}) or {}
    return (query.tool == "lookup_vendors" or "vendor_statuses" in filters or "vendor_not_active" in filters
            or query.params.get("group_by") == "vendor_status")


def _standard_assumptions(queries: list[ToolResult], dataset: Dataset) -> list[str]:
    """Assumptions the server adds whenever they apply, so they're never forgotten."""
    assumptions: list[str] = []
    if any(q.tool in SPEND_TOOLS for q in queries):
        assumptions.append(f"Non-EUR amounts are converted to EUR (policy §5.1) using {dataset.fx.basis_description}.")
    if any(_uses_vendor_status(q) for q in queries):
        assumptions.append(VENDOR_STATUS_ASSUMPTION)
    if any(q.tool == "approval_requirement" and any("required_approver" in r for r in q.rows) for q in queries):
        assumptions.append(APPROVAL_BAND_ASSUMPTION)
    for query in queries:
        if query.tool == "find_invoices" and query.params.get("as_of"):
            assumptions.append(
                f"Ages are counted to {query.params['as_of']}, the date given in the question. "
                "The data has no reporting date of its own."
            )
    for query in queries:
        if query.tool != "query_spend":
            continue
        filters = query.params.get("filters", {})
        count = query.totals.get("unmatched_credit_note_count")
        if count:
            assumptions.append(
                f"Spend counts invoices only. {count} unmatched credit note(s) "
                f"(EUR {query.totals['unmatched_credit_notes_eur']:,.2f}) are shown separately, not subtracted: "
                "policy §6.1 requires credit notes to be matched to their original invoice first."
            )
        if "credit_notes_netted_eur" in query.totals:
            assumptions.append(
                "Spend is net of credit notes, as requested. The data can't confirm the credit notes are matched "
                "to their original invoices (§6.1)."
            )
        if "vendor_statuses" not in filters and "vendor_not_active" not in filters:
            assumptions.append("All vendor statuses are included (ACTIVE, INACTIVE and ON_HOLD).")
    return assumptions
