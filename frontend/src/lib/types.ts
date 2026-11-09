// The API contract, mirrored from backend/app/schemas.py.
// If you change one, change the other.

export type AnswerStatus = "answered" | "partial" | "insufficient_data" | "out_of_scope";
export type Route = "policy" | "data";

/** A row in a result table: column name -> value. */
export type Row = Record<string, string | number | boolean | null>;

// ------------------------------------------------------------------------ POST /ask
export interface PolicyEvidence {
  clause_id: string; // e.g. "3.1"
  section_title: string;
  text: string; // verbatim policy text, looked up by the server
}

export interface DataEvidence {
  query_id: string; // e.g. "q1"
  tool: string;
  description: string; // plain-English description of the computation
  params: Record<string, unknown>;
  rows: Row[]; // the result table
  totals: Record<string, string | number | null>;
  notes: string[];
  invoices: Row[]; // contributing invoices (at most 50)
  invoice_count: number; // how many contributed in total
  invoices_truncated: boolean;
}

export interface AnswerMeta {
  model: string;
  prompt_version: string;
  latency_ms: number;
  llm_calls: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens: number;
  data_snapshot: string;
}

export interface AskResponse {
  request_id: string;
  status: AnswerStatus;
  answer: string;
  route: Route[];
  evidence: { policy: PolicyEvidence[]; data: DataEvidence[] };
  assumptions: string[];
  missing_information: string[];
  warnings: string[];
  meta: AnswerMeta;
}

// --------------------------------------------------------------------- GET /summary
export interface SummaryResponse {
  invoice_count: number;
  vendor_count: number;
  period: { first_invoice: string; last_invoice: string };
  // gross = invoices only (the headline). Credit notes can't be matched to their
  // original invoice (policy §6.1), so they are reported separately; net is for reference.
  spend_eur: { gross: number; credit_notes: number; credit_note_count: number; net: number };
  by_currency: { currency: string; invoice_count: number; amount_original: number; amount_eur: number }[];
  by_vendor_status: { status: string; vendor_count: number; invoice_count: number; amount_eur: number }[];
  control_flags: { flag: string; label: string; policy_clause: string; invoice_count: number; amount_eur: number }[];
  fx_basis: string;
  data_snapshot: string;
  source_files: { name: string; sha256: string; rows: number | null }[];
}

// ------------------------------------------------------------------------- errors
export interface ErrorResponse {
  error: { code: string; message: string; request_id: string };
}
