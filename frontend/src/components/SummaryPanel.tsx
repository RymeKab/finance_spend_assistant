// The overview on the left. Loaded from GET /summary when the page opens,
// so there is something useful on screen before the first question.
// No AI is involved, so it also works when the AI service is down.
//
// Display rule: amounts in the tables are rounded (1.38m, 416.1k) so the panel is easy
// to scan. The exact figure, to the cent, is always one step away: the headline shows
// it underneath, and every rounded amount shows it in a small tooltip on hover, on
// keyboard focus or on tap (phones), and reads it out to screen readers.
// These are the same figures the answers quote, so the two can be compared directly.
import { useSummary } from "../hooks/useSummary";
import { errorTitle } from "../lib/api";
import { formatCompact, formatCount, formatEurShort, formatMoney } from "../lib/format";

/**
 * A rounded amount that reveals its exact value, e.g. "1.38m" -> "EUR 1,377,108.82".
 * The tooltip is our own (styles.css: .amount-tip) rather than the browser's `title`
 * tooltip, which is slow, needs a perfectly still mouse and never appears on phones.
 */
function Amount({ value, currency }: { value: number; currency: string }) {
  const exact = `${currency} ${formatMoney(value)}`;
  return (
    // tabIndex makes it reachable by keyboard and tappable on phones (focus shows the tooltip).
    <span className="amount" tabIndex={0}>
      <span aria-hidden="true">{formatCompact(value)}</span>
       <span className="amount-tip" aria-hidden="true">{exact}</span>
      <span className="visually-hidden">{exact}</span>
    </span>
  );
}

export function SummaryPanel() {
  const { state, reload } = useSummary();

  if (state.status === "loading") {
    return (
      <aside className="panel summary-panel" aria-busy="true" aria-label="Invoice summary">
        <h2>2025 overview</h2>
        <div className="skeleton skeleton-big" />
        <div className="skeleton" />
        <div className="skeleton" />
        <div className="skeleton" />
      </aside>
    );
  }

  if (state.status === "error") {
    return (
      <aside className="panel summary-panel" aria-label="Invoice summary">
        <h2>2025 overview</h2>
        <div className="callout callout-error" role="alert">
          <strong>{errorTitle(state.error)}</strong>
          <p>{state.error.message}</p>
          <button type="button" className="button-secondary" onClick={reload}>Retry</button>
        </div>
      </aside>
    );
  }

  const s = state.data;
  // Credit notes can't be matched to their original invoice (§6.1), so they are
  // counted and shown on their own instead of being subtracted from spend.
  const creditNoteCount = s.spend_eur.credit_note_count;
  const invoiceCount = s.invoice_count - creditNoteCount;
  return (
    <aside className="panel summary-panel" aria-label="Invoice summary">
      <h2>2025 overview</h2>

      <div className="headline">
        <span className="headline-label">Spend (EUR), invoices only</span>
        <span className="headline-value">{formatEurShort(s.spend_eur.gross)}</span>
        <span className="headline-exact">EUR {formatMoney(s.spend_eur.gross)}</span>
        <span className="muted small">
          {formatCount(invoiceCount)} invoices + {creditNoteCount} credit notes · {s.vendor_count} vendors ·{" "}
          {s.period.first_invoice} to {s.period.last_invoice}
        </span>
        {creditNoteCount > 0 && (
          <span className="muted small">
            {creditNoteCount} unmatched credit notes (EUR {formatMoney(s.spend_eur.credit_notes)}), shown separately and
            not subtracted (§6.1)
          </span>
        )}
      </div>

      <h3>By currency</h3>
      <table className="summary-table">
        <thead>
          <tr><th>Currency</th><th className="num">Invoices</th><th className="num">Original</th><th className="num">EUR</th></tr>
        </thead>
        <tbody>
          {s.by_currency.map((c) => (
            <tr key={c.currency}>
              <td>{c.currency}</td>
              <td className="num">{c.invoice_count}</td>
              <td className="num"><Amount value={c.amount_original} currency={c.currency} /></td>
              <td className="num"><Amount value={c.amount_eur} currency="EUR" /></td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>By vendor status</h3>
      <table className="summary-table">
        <thead>
          <tr><th>Status</th><th className="num">Vendors</th><th className="num">Invoices</th><th className="num">EUR</th></tr>
        </thead>
        <tbody>
          {s.by_vendor_status.map((v) => (
            <tr key={v.status}>
              <td><span className={`status-dot status-${v.status}`} />{v.status}</td>
              <td className="num">{v.vendor_count}</td>
              <td className="num">{v.invoice_count}</td>
              <td className="num"><Amount value={v.amount_eur} currency="EUR" /></td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Control checks</h3>
      <ul className="flags">
        {s.control_flags.map((f) => (
          <li key={f.flag}>
            <span className="flag-count">{f.invoice_count}</span>
            <span>
              {f.label} <span className="muted">(§{f.policy_clause})</span>
            </span>
          </li>
        ))}
      </ul>

      <footer className="summary-footer">
        <p className="muted small">Table amounts are rounded; hover over one (or tap it) to see it to the cent.</p>
        <p className="muted small">FX: {s.fx_basis}.</p>
        <p className="muted small">Data snapshot {s.data_snapshot}</p>
      </footer>
    </aside>
  );
}
