"""
The tool registry: the four calculators Claude can call, and how to run them.

Claude never does arithmetic. When a question needs data, Claude asks for one of
these tools by name and fills in its parameters. The server then:

  1. checks the parameters against the tool's Pydantic model,
  2. runs the tool on the in-memory invoice table,
  3. returns a ToolResult with a query ID ("q1", "q2", ...) that Claude can cite.

Adding a tool means writing its module and adding one line to DATA_TOOLS below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from app.data.loader import Dataset
from app.tools.approval_requirement import ApprovalRequirementInput, run_approval_requirement
from app.tools.base import ToolResult
from app.tools.find_invoices import FindInvoicesInput, run_find_invoices
from app.tools.lookup_vendors import LookupVendorsInput, run_lookup_vendors
from app.tools.query_spend import QuerySpendInput, run_query_spend


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str  # what Claude reads to decide when to use the tool
    input_model: type[BaseModel]
    run: Callable[[Any, Dataset, str], ToolResult]


DATA_TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec(
            "query_spend",
            "Totals, rankings and breakdowns of spend in EUR. Counts invoices only: unmatched credit notes are "
            "reported separately (set net_credit_notes=true only if the user explicitly asks for a net figure). "
            "Use for: total spend, top-N vendors, spend by country / currency / vendor status / cost centre / month / approver.",
            QuerySpendInput,
            run_query_spend,
        ),
        ToolSpec(
            "find_invoices",
            "List individual invoices that match filters, with their control flags "
            "(no PO reference on an invoice of EUR 1,000+, missing approver, vendor not active, credit note) and approval band. "
            "Use for 'which invoices...' questions and to look up specific invoices.",
            FindInvoicesInput,
            run_find_invoices,
        ),
        ToolSpec(
            "lookup_vendors",
            "Look up vendors in the vendor master (country, category, status) with their 2025 invoice counts.",
            LookupVendorsInput,
            run_lookup_vendors,
        ),
        ToolSpec(
            "approval_requirement",
            "Required approver under policy §3 for an invoice number or for an amount in EUR/GBP/USD. "
            "Converts to EUR at the invoice-date rate first. Always use this instead of reading the §3 table "
            "yourself when an invoice or a non-EUR amount is involved.",
            ApprovalRequirementInput,
            run_approval_requirement,
        ),
    )
}


def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """
    Turn a Pydantic model into the JSON schema Claude reads, with nested models
    written out in place (no $ref links) and without noisy 'title' keys.
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def inline(node: Any, is_properties: bool = False) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                target = definitions[node["$ref"].split("/")[-1]]
                merged = {**inline(target), **{k: v for k, v in node.items() if k != "$ref"}}
                return inline(merged)
            # Drop the schema keyword "title", but keep a *field* that happens to be called "title".
            return {
                k: inline(v, is_properties=(k == "properties" and not is_properties))
                for k, v in node.items()
                if is_properties or k != "title"
            }
        if isinstance(node, list):
            return [inline(item) for item in node]
        return node

    return inline(schema)


def data_tool_definitions() -> list[dict[str, Any]]:
    """The tool list in the format the Claude API expects."""
    return [
        {"name": spec.name, "description": spec.description, "input_schema": json_schema_for(spec.input_model)}
        for spec in DATA_TOOLS.values()
    ]


def run_tool(name: str, raw_input: dict[str, Any], dataset: Dataset, query_id: str) -> ToolResult:
    """Validate the parameters and run one tool. Never raises: problems become ToolResult.error."""
    spec = DATA_TOOLS.get(name)
    if spec is None:
        return ToolResult(query_id, name, raw_input or {}, error=f"Unknown tool '{name}'.")
    try:
        params = spec.input_model.model_validate(raw_input or {})
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}" for e in exc.errors())
        return ToolResult(query_id, name, raw_input or {}, error=f"Invalid parameters: {problems}")
    try:
        return spec.run(params, dataset, query_id)
    except Exception as exc:  # a bug in a tool must not crash the request; it is reported instead
        return ToolResult(query_id, name, params.model_dump(mode="json", exclude_none=True), error=f"Tool failed: {exc}")


__all__ = ["DATA_TOOLS", "ToolResult", "data_tool_definitions", "json_schema_for", "run_tool"]
