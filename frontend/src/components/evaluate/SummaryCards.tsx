import { formatMs, formatNumber } from "@/lib/utils";

function formatValue(key: string, value: unknown): string {
  if (typeof value !== "number") return String(value);
  if (key.includes("latency")) return formatMs(value);
  if (
    key.includes("rate") ||
    key.includes("recall") ||
    key.includes("precision") ||
    key.includes("coverage") ||
    key.includes("accuracy") ||
    key.includes("faithfulness") ||
    key.includes("completeness")
  ) {
    return `${(value * 100).toFixed(1)}%`;
  }
  return formatNumber(value);
}

function labelize(key: string): string {
  return key.replace(/^avg_/, "").replace(/_/g, " ");
}

export function SummaryCards({ summary }: { summary: Record<string, unknown> }) {
  const entries = Object.entries(summary);
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No summary available yet.</p>;
  }

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {entries.map(([key, value]) => (
        <div key={key} className="rounded-lg border border-border bg-card p-3">
          <div className="text-xs capitalize text-muted-foreground">{labelize(key)}</div>
          <div className="text-lg font-semibold">{formatValue(key, value)}</div>
        </div>
      ))}
    </div>
  );
}
