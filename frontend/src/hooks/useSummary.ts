// Loads GET /summary once when the page opens, with loading, error and retry states.
import { useCallback, useEffect, useState } from "react";
import { ApiError, getSummary } from "../lib/api";
import type { SummaryResponse } from "../lib/types";

export type SummaryState =
  | { status: "loading" }
  | { status: "loaded"; data: SummaryResponse }
  | { status: "error"; error: ApiError };

export function useSummary(): { state: SummaryState; reload: () => void } {
  const [state, setState] = useState<SummaryState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0); // bumping this re-runs the effect (Retry)

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    getSummary(controller.signal)
      .then((data) => setState({ status: "loaded", data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: "error", error: error instanceof ApiError ? error : new ApiError("unknown", String(error), null, 0) });
      });
    return () => controller.abort(); // cancel if the component goes away
  }, [attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { state, reload };
}
