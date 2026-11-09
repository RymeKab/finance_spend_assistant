// Small coloured labels: the answer's status, and which sources it used.
import type { AnswerStatus, Route } from "../lib/types";

const STATUS_LABELS: Record<AnswerStatus, string> = {
  answered: "Answered",
  partial: "Partial answer",
  insufficient_data: "Can't answer from the data",
  out_of_scope: "Out of scope",
};

export function StatusBadge({ status }: { status: AnswerStatus }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABELS[status]}</span>;
}

export function RouteChips({ route }: { route: Route[] }) {
  if (route.length === 0) return <span className="chip chip-none">No sources cited</span>;
  return (
    <>
      {route.map((source) => (
        <span key={source} className={`chip chip-${source}`}>
          {source === "policy" ? "Policy" : "Invoice data"}
        </span>
      ))}
    </>
  );
}
