// One question and what happened to it: still thinking, answered (with evidence), or failed (with Retry).
import type { ChatMessage } from "../hooks/useChat";
import { errorTitle } from "../lib/api";
import { EvidencePanel } from "./EvidencePanel";
import { RichText } from "./RichText";
import { StatusBadge } from "./StatusBadge";

interface Props {
  message: ChatMessage;
  isLatest: boolean; // the latest answer opens its evidence by default
  onRetry: (id: string) => void;
}

export function AnswerCard({ message, isLatest, onRetry }: Props) {
  return (
    <article className="exchange">
      <div className="question-bubble">{message.question}</div>

      {message.state === "pending" && (
        <div className="answer answer-pending" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          Checking the policy and the invoice data…
        </div>
      )}

      {message.state === "error" && message.error && (
        <div className="answer answer-error" role="alert">
          <strong>{errorTitle(message.error)}</strong>
          <p>{message.error.message}</p>
          {message.error.requestId && <p className="muted small">Request ID: {message.error.requestId}</p>}
          <button type="button" className="button-secondary" onClick={() => onRetry(message.id)}>
            Retry
          </button>
        </div>
      )}

      {message.state === "done" && message.response && (
        <div className={`answer answer-${message.response.status}`}>
          <StatusBadge status={message.response.status} />
          <RichText text={message.response.answer} />
          <EvidencePanel response={message.response} defaultOpen={isLatest} />
        </div>
      )}
    </article>
  );
}
