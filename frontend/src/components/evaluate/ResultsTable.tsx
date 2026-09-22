import { Badge } from "@/components/ui/badge";
import { formatMs } from "@/lib/utils";

export function ResultsTable({ results }: { results: Record<string, unknown>[] }) {
  if (results.length === 0) {
    return <p className="text-sm text-muted-foreground">No per-question results available.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-left text-sm">
        <thead className="bg-muted text-muted-foreground">
          <tr>
            <th className="p-2 font-medium">Question</th>
            <th className="p-2 font-medium">Status</th>
            <th className="p-2 font-medium">Recall</th>
            <th className="p-2 font-medium">Precision</th>
            <th className="p-2 font-medium">Citation acc.</th>
            <th className="p-2 font-medium">Latency</th>
          </tr>
        </thead>
        <tbody>
          {results.map((row, i) => (
            <tr key={i} className="border-t border-border">
              <td className="max-w-xs truncate p-2" title={String(row.question ?? "")}>
                {String(row.question ?? "")}
              </td>
              <td className="p-2">
                <Badge variant={row.status === "completed" ? "success" : "destructive"}>
                  {String(row.status ?? "unknown")}
                </Badge>
              </td>
              <td className="p-2">{Number(row.retrieval_recall ?? 0).toFixed(2)}</td>
              <td className="p-2">{Number(row.retrieval_precision ?? 0).toFixed(2)}</td>
              <td className="p-2">{Number(row.citation_accuracy ?? 0).toFixed(2)}</td>
              <td className="p-2">{formatMs(Number(row.latency_ms ?? 0))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
