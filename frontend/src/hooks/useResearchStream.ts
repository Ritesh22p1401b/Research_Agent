import { useResearchStore } from "@/store/research-store";

export type { ProgressEvent, ResearchStreamStatus, StreamOptions } from "@/store/research-store";

/**
 * Live research state (SSE progress -> result). Backed by a global store so the run and its output are kept
 * when the user switches to another page and back; a browser refresh clears it.
 */
export function useResearchStream() {
  const start = useResearchStore((s) => s.start);
  const reset = useResearchStore((s) => s.reset);
  const progress = useResearchStore((s) => s.progress);
  const result = useResearchStore((s) => s.result);
  const status = useResearchStore((s) => s.status);
  const error = useResearchStore((s) => s.error);
  const lastQuery = useResearchStore((s) => s.lastQuery);

  return { start, reset, progress, result, status, error, lastQuery, isPending: status === "running" };
}
