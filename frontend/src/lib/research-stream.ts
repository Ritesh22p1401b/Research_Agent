import { API_BASE_URL } from "@/lib/api-client";
import {
  type ReportDepth,
  type ResearchMode,
  type ResearchResponse,
  researchResponseSchema,
} from "@/lib/api-types";

export type ProgressEvent = {
  stage: "planner" | "research" | "analysis" | "critic" | "report" | string;
  [key: string]: unknown;
};

export type StreamOptions = {
  documentIds?: string[];
  mode?: ResearchMode;
  reportDepth?: ReportDepth;
};

export type StreamHandlers = {
  onProgress: (event: ProgressEvent) => void;
  onDone: (result: ResearchResponse) => void;
  onError: (message: string) => void;
};

/**
 * Opens GET /api/research/stream (SSE) and reports live progress + the final result through callbacks.
 * Returns a function that closes the stream (used by the Stop button).
 */
export function startResearchStream(query: string, options: StreamOptions, handlers: StreamHandlers): () => void {
  const params = new URLSearchParams({ query });
  if (options.documentIds && options.documentIds.length > 0) {
    params.set("document_ids", options.documentIds.join(","));
  }
  if (options.mode) params.set("mode", options.mode);
  if (options.reportDepth) params.set("report_depth", options.reportDepth);

  const source = new EventSource(`${API_BASE_URL}/api/research/stream?${params.toString()}`);
  let finished = false;
  const finish = (fn: () => void) => {
    if (finished) return;
    finished = true;
    source.close();
    fn();
  };

  source.addEventListener("node_complete", (e: MessageEvent) => {
    try {
      handlers.onProgress(JSON.parse(e.data) as ProgressEvent);
    } catch {
      // ignore a malformed progress chunk - the final "done" event is what matters
    }
  });

  source.addEventListener("done", (e: MessageEvent) => {
    finish(() => {
      try {
        handlers.onDone(researchResponseSchema.parse(JSON.parse(e.data)));
      } catch {
        handlers.onError("Received a malformed response from the server");
      }
    });
  });

  source.addEventListener("error", (e: MessageEvent) => {
    let message = "Research workflow failed";
    try {
      message = (JSON.parse(e.data) as { message?: string }).message ?? message;
    } catch {
      // a hard disconnect carries no body
    }
    finish(() => handlers.onError(message));
  });

  source.onerror = () => finish(() => handlers.onError("Connection to the research stream was lost"));

  return () => {
    finished = true;
    source.close();
  };
}
