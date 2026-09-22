import type { ResearchMetrics } from "@/lib/api-types";
import { formatMs, formatNumber } from "@/lib/utils";

const items: { key: keyof ResearchMetrics; label: string; format: (n: number) => string }[] = [
  { key: "latency_ms", label: "Latency", format: formatMs },
  { key: "llm_calls", label: "LLM calls", format: formatNumber },
  { key: "tool_calls", label: "Tool calls", format: formatNumber },
  { key: "retries", label: "Retries", format: formatNumber },
  { key: "total_tokens", label: "Tokens", format: formatNumber },
];

export function MetricsRow({ metrics }: { metrics: ResearchMetrics }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {items.map(({ key, label, format }) => (
        <div key={key} className="rounded-lg border border-border bg-card p-3">
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className="text-lg font-semibold">{format(metrics[key])}</div>
        </div>
      ))}
    </div>
  );
}
