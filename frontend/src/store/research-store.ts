import { toast } from "sonner";
import { create } from "zustand";

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

export type ResearchStreamStatus = "idle" | "running" | "completed" | "failed";

/**
 * Research page state lives here (plain in-memory Zustand, NOT persisted) so it survives switching between
 * the Chat / Research / Evaluation pages - the SSE stream keeps running while another page is open - but is
 * cleared by a browser refresh. The EventSource is module-level for the same reason.
 */
interface ResearchState {
  // form
  query: string;
  mode: ResearchMode;
  reportDepth: ReportDepth;
  attached: { id: string; filename: string }[];
  // run
  lastQuery: string;
  progress: ProgressEvent[];
  result: ResearchResponse | null;
  status: ResearchStreamStatus;
  error: string | null;

  setForm: (patch: Partial<Pick<ResearchState, "query" | "mode" | "reportDepth">>) => void;
  setAttached: (updater: (prev: { id: string; filename: string }[]) => { id: string; filename: string }[]) => void;
  start: (query: string, options?: StreamOptions) => void;
  reset: () => void;
}

let source: EventSource | null = null;

export const useResearchStore = create<ResearchState>()((set, get) => ({
  query: "",
  mode: "fast",
  reportDepth: "standard",
  attached: [],
  lastQuery: "",
  progress: [],
  result: null,
  status: "idle",
  error: null,

  setForm: (patch) => set(patch),
  setAttached: (updater) => set((s) => ({ attached: updater(s.attached) })),

  start: (query, options = {}) => {
    source?.close();
    set({ lastQuery: query, progress: [], result: null, error: null, status: "running" });

    const params = new URLSearchParams({ query });
    if (options.documentIds && options.documentIds.length > 0) {
      params.set("document_ids", options.documentIds.join(","));
    }
    if (options.mode) params.set("mode", options.mode);
    if (options.reportDepth) params.set("report_depth", options.reportDepth);
    const es = new EventSource(`${API_BASE_URL}/api/research/stream?${params.toString()}`);
    source = es;
    const finish = (patch: Partial<ResearchState>) => {
      es.close();
      if (source === es) source = null;
      set(patch);
    };

    es.addEventListener("node_complete", (e: MessageEvent) => {
      try {
        const event = JSON.parse(e.data) as ProgressEvent;
        set((s) => ({ progress: [...s.progress, event] }));
      } catch {
        // ignore malformed progress chunk - the final "done" event is what matters
      }
    });

    es.addEventListener("done", (e: MessageEvent) => {
      try {
        const parsed = researchResponseSchema.parse(JSON.parse(e.data));
        const ok = parsed.status === "completed";
        finish({ result: parsed, status: ok ? "completed" : "failed", error: ok ? null : (parsed.error ?? null) });
        if (ok) toast.success("Research finished");
        else toast.error(parsed.error ?? "Research failed");
      } catch {
        finish({ status: "failed", error: "Received a malformed response from the server" });
        toast.error("Received a malformed response from the server");
      }
    });

    es.addEventListener("error", (e: MessageEvent) => {
      let message = "Research workflow failed";
      try {
        message = (JSON.parse(e.data) as { message?: string }).message ?? message;
      } catch {
        // server-sent "error" event may not carry a JSON body on hard disconnects
      }
      finish({ status: "failed", error: message });
      toast.error(message);
    });

    es.onerror = () => {
      if (get().status === "running") {
        finish({ status: "failed", error: "Connection to the research stream was lost" });
        toast.error("Connection to the research stream was lost");
      } else {
        es.close();
      }
    };
  },

  reset: () => {
    source?.close();
    source = null;
    set({ progress: [], result: null, status: "idle", error: null });
  },
}));
