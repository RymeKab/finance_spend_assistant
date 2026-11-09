// The chat's state: every question asked in this session and what happened to it.
//
// Each message moves through: pending -> done (with the answer), or pending -> error.
// An errored message can be retried, which sends the same question again.
// State lives only in memory: reloading the page starts a fresh session.
import { useCallback, useEffect, useReducer, useRef } from "react";
import { ApiError, askQuestion } from "../lib/api";
import type { AskResponse } from "../lib/types";

export interface ChatMessage {
  id: string; // local ID, used as the React key
  question: string;
  state: "pending" | "done" | "error";
  response?: AskResponse;
  error?: ApiError;
}

type Action =
  | { type: "asked"; id: string; question: string }
  | { type: "retrying"; id: string }
  | { type: "answered"; id: string; response: AskResponse }
  | { type: "failed"; id: string; error: ApiError };

let nextId = 0; // local message IDs: m1, m2, ...

function reducer(messages: ChatMessage[], action: Action): ChatMessage[] {
  switch (action.type) {
    case "asked":
      return [...messages, { id: action.id, question: action.question, state: "pending" }];
    case "retrying":
      return messages.map((m) => (m.id === action.id ? { id: m.id, question: m.question, state: "pending" } : m));
    case "answered":
      return messages.map((m) => (m.id === action.id ? { ...m, state: "done", response: action.response } : m));
    case "failed":
      return messages.map((m) => (m.id === action.id ? { ...m, state: "error", error: action.error } : m));
  }
}

export function useChat() {
  const [messages, dispatch] = useReducer(reducer, []);
  const controllers = useRef(new Map<string, AbortController>());

  // Cancel any request still running when the chat is closed.
  useEffect(() => {
    const running = controllers.current;
    return () => running.forEach((controller) => controller.abort());
  }, []);

  const send = useCallback(async (id: string, question: string) => {
    const controller = new AbortController();
    controllers.current.set(id, controller);
    try {
      const response = await askQuestion(question, controller.signal);
      dispatch({ type: "answered", id, response });
    } catch (error) {
      if (controller.signal.aborted) return;
      const apiError = error instanceof ApiError ? error : new ApiError("unknown", String(error), null, 0);
      dispatch({ type: "failed", id, error: apiError });
    } finally {
      controllers.current.delete(id);
    }
  }, []);

  const ask = useCallback(
    (question: string) => {
      const id = `m${++nextId}`;
      dispatch({ type: "asked", id, question });
      void send(id, question);
    },
    [send],
  );

  const retry = useCallback(
    (id: string) => {
      const message = messages.find((m) => m.id === id);
      if (!message) return;
      dispatch({ type: "retrying", id });
      void send(id, message.question);
    },
    [messages, send],
  );

  const isBusy = messages.some((m) => m.state === "pending");
  return { messages, ask, retry, isBusy };
}
