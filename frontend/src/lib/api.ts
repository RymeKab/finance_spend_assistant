// Talks to the backend. Every failure becomes an ApiError with a code and a
// plain-language message, so components never deal with raw HTTP problems.
import type { AskResponse, ErrorResponse, SummaryResponse } from "./types";

const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public code: string, // e.g. "llm_timeout", "network_error"
    message: string,
    public requestId: string | null, // matches the backend audit log
    public httpStatus: number, // 0 when the server couldn't be reached
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, signal });
  } catch (error) {
    if (signal?.aborted) throw error; // the user navigated away; not an error to show
    throw new ApiError("network_error", `Can't reach the backend at ${API_URL}. Is it running?`, null, 0);
  }

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (body as ErrorResponse | null)?.error;
    throw new ApiError(
      detail?.code ?? `http_${response.status}`,
      detail?.message ?? `The server answered with an error (${response.status}).`,
      detail?.request_id ?? response.headers.get("X-Request-ID"),
      response.status,
    );
  }
  return body as T;
}

export function getSummary(signal?: AbortSignal): Promise<SummaryResponse> {
  return request<SummaryResponse>("/summary", { method: "GET" }, signal);
}

export function askQuestion(question: string, signal?: AbortSignal): Promise<AskResponse> {
  return request<AskResponse>(
    "/ask",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) },
    signal,
  );
}

/** Short, user-facing explanation for each error code. The server's message is shown underneath. */
export function errorTitle(error: ApiError): string {
  switch (error.code) {
    case "network_error":
      return "The backend can't be reached";
    case "llm_not_configured":
      return "The AI isn't set up yet";
    case "llm_unavailable":
      return "The AI service is unavailable";
    case "llm_timeout":
      return "The AI took too long to answer";
    case "llm_bad_output":
      return "The AI's answer couldn't be used";
    case "invalid_question":
      return "That question can't be sent";
    default:
      return "Something went wrong";
  }
}
