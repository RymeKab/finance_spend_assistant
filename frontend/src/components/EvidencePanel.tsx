// "What this answer is based on": the evidence under every answer.
//
// Everything shown here was assembled by the server, not written by the AI:
// policy clauses are quoted from the policy file, and data tables come straight
// from the calculations (tools) that ran. Warnings flag anything that didn't check out.
import type { AskResponse, DataEvidence, Row } from "../lib/types";
import { formatCount, formatMoney } from "../lib/format";
import { DataTable } from "./DataTable";
import { RichText } from "./RichText";
import { RouteChips } from "./StatusBadge";

const INVOICE_COLUMNS = [
  "invoice_number", "invoice_date", "vendor_name", "description", "amount", "currency",
  "amount_eur", "po_number", "approved_by", "flags",
];

/** Turn the yes/no control flags into one readable column. */
function withFlags(invoices: Row[]): Row[] {
  return invoices.map((invoice) => {
    const flags = [
      // A missing PO is only a breach from EUR 1,000 (§2.1); below that it is allowed.
      invoice.missing_required_po && "No PO, EUR 1,000+ (§2.1)",
      invoice.missing_po_ref && !invoice.missing_required_po && !invoice.is_credit_note && "No PO, under EUR 1,000 (allowed)",
      invoice.missing_approver && "No approver (§3.1)",
      invoice.vendor_not_active && `Vendor ${invoice.vendor_status} (§4.1)`,
      invoice.is_credit_note && "Credit note (§6.1)",
    ].filter(Boolean);
    return { ...invoice, flags: flags.join(" · ") || null };
  });
}

/** One line under the table with the query's totals, in the same words the server uses. */
function totalsLine(totals: DataEvidence["totals"]): string | null {
  const num = (key: string) => (typeof totals[key] === "number" ? (totals[key] as number) : null);
  const parts: string[] = [];

  // query_spend: spend counts invoices only, unless the user asked for a net figure.
  const spend = num("spend_eur");
  const netted = num("credit_notes_netted_eur");
  if (spend !== null) parts.push(`${netted !== null ? "Net spend" : "Spend"} EUR ${formatMoney(spend)}`);
  const invoiceCount = num("invoice_count");
  if (invoiceCount !== null) parts.push(`${formatCount(invoiceCount)} invoices`);
  const unmatchedCount = num("unmatched_credit_note_count");
  const unmatchedEur = num("unmatched_credit_notes_eur");
  if (unmatchedCount && unmatchedEur !== null) {
    parts.push(`${unmatchedCount} unmatched credit note(s) EUR ${formatMoney(unmatchedEur)}, not subtracted (§6.1)`);
  }
  if (netted !== null) parts.push(`credit notes netted EUR ${formatMoney(netted)}, matching unconfirmed (§6.1)`);

  // find_invoices
  const matching = num("matching_invoices");
  if (matching !== null) parts.push(`${formatCount(matching)} matching invoices`);
  const invoicesEur = num("invoices_eur");
  if (invoicesEur !== null) parts.push(`invoices EUR ${formatMoney(invoicesEur)}`);
  const creditNotes = num("credit_notes_eur");
  if (creditNotes) parts.push(`credit notes EUR ${formatMoney(creditNotes)}, shown separately (§6.1)`);

  return parts.length ? parts.join(" · ") : null;
}

function DataQuery({ query }: { query: DataEvidence }) {
  const totals = totalsLine(query.totals);
  return (
    <div className="evidence-item">
      <div className="evidence-item-head">
        <span className="query-id">{query.query_id}</span>
        <span className="tool-name">{query.tool}</span>
      </div>
      <p className="computation">{query.description}</p>
      <DataTable rows={query.rows} />
      {totals && <p className="muted small">{totals}</p>}
      {query.notes.length > 0 && (
        <ul className="notes">
          {query.notes.map((note) => <li key={note}>{note}</li>)}
        </ul>
      )}
      {query.invoice_count > 0 && (
        <details className="invoices">
          <summary>
            Contributing invoices ({formatCount(query.invoice_count)}
            {query.invoices_truncated ? `, first ${query.invoices.length} shown` : ""})
          </summary>
          <DataTable rows={withFlags(query.invoices)} columns={INVOICE_COLUMNS} />
        </details>
      )}
    </div>
  );
}

export function EvidencePanel({ response, defaultOpen }: { response: AskResponse; defaultOpen: boolean }) {
  const { evidence, assumptions, missing_information: missing, warnings, meta } = response;
  return (
    <details className="evidence" open={defaultOpen}>
      <summary>
        <span className="evidence-title">What this answer is based on</span>
        <RouteChips route={response.route} />
      </summary>

      {warnings.length > 0 && (
        <div className="callout callout-warning" role="alert">
          <strong>Check before relying on this answer</strong>
          <ul>{warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}

      {evidence.policy.length > 0 && (
        <section className="evidence-section">
          <h4>Policy clauses, quoted from FIN-POL-014</h4>
          {evidence.policy.map((clause) => (
            <div className="evidence-item policy-quote" key={clause.clause_id}>
              <div className="evidence-item-head">
                <span className="clause-id">§{clause.clause_id}</span>
                <span>{clause.section_title}</span>
              </div>
              <blockquote><RichText text={clause.text} /></blockquote>
            </div>
          ))}
        </section>
      )}

      {evidence.data.length > 0 && (
        <section className="evidence-section">
          <h4>Invoice data: the calculations that ran</h4>
          {evidence.data.map((query) => <DataQuery key={query.query_id} query={query} />)}
        </section>
      )}

      {assumptions.length > 0 && (
        <section className="evidence-section">
          <h4>Assumptions</h4>
          <ul>{assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
        </section>
      )}

      {missing.length > 0 && (
        <section className="evidence-section">
          <h4>Data that would be needed</h4>
          <ul>{missing.map((m) => <li key={m}>{m}</li>)}</ul>
        </section>
      )}

      <footer className="meta">
        {meta.model} · prompt {meta.prompt_version} · {(meta.latency_ms / 1000).toFixed(1)} s · {meta.llm_calls} AI calls ·{" "}
        {meta.tool_calls} tool calls · {formatCount(meta.input_tokens + meta.output_tokens)} tokens · data {meta.data_snapshot} ·
        request {response.request_id}
      </footer>
    </details>
  );
}
