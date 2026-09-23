import { useCallback, useRef, useState } from "react";

import {
  type ReportDepth,
  type ResearchMode,
  type ResearchResponse,
  researchResponseSchema,
} from "@/lib/api-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";

export type ProgressEvent = {
  stage: "planner" | "research" | "analysis" | "critic" | "report" | string;
  [key: string]: unknown;
};

export type StreamOptions = {
  documentIds?: string[];
  mode?: ResearchMode;
  reportDepth?: ReportDepth;
};

export type ResearchStreamStatus = "idle" | "running" | "completed" | "failed";

/**
 * Drives GET /api/research/stream over SSE so the UI can show live progress
 * (planning -> researching -> analysis -> critic -> report) instead of
 * waiting on one long POST /api/research request with no feedback.
 */
export function useResearchStream() {
  const [progress, setProgress] = useState<ProgressEvent[]>([]);
  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [status, setStatus] = useState<ResearchStreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  const start = useCallback((query: string, options: StreamOptions = {}) => {
    sourceRef.current?.close();
    setProgress([]);
    setResult(null);
    setError(null);
    setStatus("running");

    const params = new URLSearchParams({ query });
    if (options.documentIds && options.documentIds.length > 0) {
      params.set("document_ids", options.documentIds.join(","));
    }
    if (options.mode) params.set("mode", options.mode);
    if (options.reportDepth) params.set("report_depth", options.reportDepth);
    const url = `${API_BASE_URL}/api/research/stream?${params.toString()}`;
    const source = new EventSource(url);
    sourceRef.current = source;

    source.addEventListener("node_complete", (e: MessageEvent) => {
      try {
        setProgress((prev) => [...prev, JSON.parse(e.data) as ProgressEvent]);
      } catch {
        // ignore malformed progress chunk - the final "done" event is what matters
      }
    });

    source.addEventListener("done", (e: MessageEvent) => {
      source.close();
      try {
        const parsed = researchResponseSchema.parse(JSON.parse(e.data));
        setResult(parsed);
        setStatus(parsed.status === "completed" ? "completed" : "failed");
        if (parsed.status !== "completed" && parsed.error) {
          setError(parsed.error);
        }
      } catch {
        setStatus("failed");
        setError("Received a malformed response from the server");
      }
    });

    source.addEventListener("error", (e: MessageEvent) => {
      let message = "Research workflow failed";
      try {
        message = (JSON.parse(e.data) as { message?: string }).message ?? message;
      } catch {
        // server-sent "error" event may not carry a JSON body on hard disconnects
      }
      setStatus("failed");
      setError(message);
      source.close();
    });

    source.onerror = () => {
      setStatus((prev) => {
        if (prev === "running") {
          setError((prevError) => prevError ?? "Connection to the research stream was lost");
          return "failed";
        }
        return prev;
      });
      source.close();
    };
  }, []);

  const reset = useCallback(() => {
    sourceRef.current?.close();
    setProgress([]);
    setResult(null);
    setStatus("idle");
    setError(null);
  }, []);

  return { start, reset, progress, result, status, error, isPending: status === "running" };
}
