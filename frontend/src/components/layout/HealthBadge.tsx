"use client";

import { useHealth } from "@/hooks/useHealth";
import { cn } from "@/lib/utils";

/** Tiny status pill: green = model online, amber = backend up but model offline, red = backend unreachable. */
export function HealthBadge() {
  const { data, isLoading, isError } = useHealth();

  const state = isLoading
    ? { color: "bg-muted-foreground", text: "Checking..." }
    : isError || !data
      ? { color: "bg-destructive", text: "Backend offline" }
      : data.llm === "connected"
        ? { color: "bg-success", text: "Model online" }
        : { color: "bg-warning", text: "Model offline" };

  return (
    <div
      className="flex items-center gap-2 rounded-full px-3 py-1 text-xs text-muted-foreground"
      title={data ? `LLM: ${data.llm} - Qdrant: ${data.qdrant ?? "?"}` : undefined}
    >
      <span className={cn("size-2 rounded-full", state.color)} />
      {state.text}
    </div>
  );
}
