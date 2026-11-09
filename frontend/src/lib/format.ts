// Display helpers: money, numbers, column names and cell values.

const money = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const whole = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

/** 1234567.8 -> "1,234,567.80" */
export function formatMoney(value: number): string {
  return money.format(value);
}

/** 1234567.8 -> "1.23m", 45678 -> "45.7k": compact form for summary tables. */
export function formatCompact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}m`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return formatMoney(value);
}

/** 1234567.8 -> "EUR 1.23m" */
export function formatEurShort(value: number): string {
  return `EUR ${formatCompact(value)}`;
}

export function formatCount(value: number): string {
  return whole.format(value);
}

// Friendly column titles for the evidence tables. Unknown keys fall back to "Title case".
const LABELS: Record<string, string> = {
  amount_eur: "EUR",
  amount_original: "Original amount",
  amount: "Amount",
  invoice_count: "Invoices",
  invoices_2025: "Invoices (2025)",
  invoice_number: "Invoice",
  invoice_date: "Date",
  vendor_name: "Vendor",
  vendor_id: "Vendor ID",
  vendor_status: "Vendor status",
  fx_rate_per_eur: "FX rate (per EUR)",
  fx_rate_date: "FX rate date",
  po_number: "PO",
  approved_by: "Approver",
  approval_band: "Approval band (EUR)",
  policy_band_eur: "Approval band (EUR)",
  required_approver: "Required approver",
  recorded_approver: "Recorded approver",
  cost_center: "Cost centre",
  policy_clause: "Policy clause",
  unmatched_credit_notes_eur: "Unmatched credit notes (EUR)",
  missing_required_po: "No PO, EUR 1,000+",
  missing_po_ref: "No PO ref",
};

export function columnLabel(key: string): string {
  return LABELS[key] ?? key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Format any cell: money columns get two decimals, empty cells a dash. */
export function formatCell(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (key.includes("rate")) return String(value);
    if (key.includes("amount") || key.endsWith("_eur")) return formatMoney(value);
    return formatCount(value);
  }
  return String(value);
}

export function isNumericColumn(key: string, rows: Record<string, unknown>[]): boolean {
  return rows.some((row) => typeof row[key] === "number");
}
