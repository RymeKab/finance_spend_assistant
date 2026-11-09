// The chat: example questions, the conversation so far, and the question box.
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";
import { useChat } from "../hooks/useChat";
import { AnswerCard } from "./AnswerCard";

const EXAMPLE_QUESTIONS = [
  "What are our top 5 vendors by total spend in 2025?",
  "What is our total spend with vendors based in Spain?",
  "Who is allowed to approve an invoice of EUR 60,000?",
  "Who needs to approve INV-20071?",
  "Were any invoices self-approved?",
];
const MAX_LENGTH = 1000;

export function ChatPanel() {
  const { messages, ask, retry, isBusy } = useChat();
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  // Keep the newest exchange in view.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  const question = draft.trim();
  const canSend = question.length > 0 && question.length <= MAX_LENGTH && !isBusy;

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!canSend) return;
    ask(question);
    setDraft("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter adds a new line.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  const latestDoneId = [...messages].reverse().find((m) => m.state === "done")?.id;

  return (
    <section className="panel chat-panel" aria-label="Ask a question">
      <div className="chat-scroll">
        {messages.length === 0 ? (
          <div className="empty-chat">
            <h2>Ask about 2025 invoices and the procurement policy</h2>
            <p className="muted">
              Every answer shows what it is based on: the policy clauses, quoted word for word, and the invoice data
              behind each figure.
            </p>
            <div className="examples">
              {EXAMPLE_QUESTIONS.map((example) => (
                <button key={example} type="button" className="example" onClick={() => ask(example)} disabled={isBusy}>
                  {example}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <AnswerCard key={message.id} message={message} isLatest={message.id === latestDoneId} onRetry={retry} />
          ))
        )}
        <div ref={endRef} />
      </div>

      <form className="composer" onSubmit={submit}>
        <textarea
          value={draft}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask a question, e.g. Which invoices have no approver?"
          rows={2}
          maxLength={MAX_LENGTH}
          aria-label="Your question"
        />
        <button type="submit" disabled={!canSend}>
          {isBusy ? "Working…" : "Ask"}
        </button>
      </form>
    </section>
  );
}
