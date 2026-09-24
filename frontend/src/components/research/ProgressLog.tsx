import { BarChart3, CheckCircle2, FileText, ListTree, Loader2, Search, ShieldCheck } from "lucide-react";
import type { ComponentType } from "react";

import type { ProgressEvent } from "@/lib/research-stream";

const STAGE_META: Record<string, { label: string; icon: ComponentType<{ className?: string }> }> = {
  planner: { label: "Planning sub-questions", icon: ListTree },
  research: { label: "Researching", icon: Search },
  analysis: { label: "Analyzing evidence", icon: BarChart3 },
  critic: { label: "Verifying findings", icon: ShieldCheck },
  report: { label: "Writing report", icon: FileText },
};

function describeStage(event: ProgressEvent): string {
  switch (event.stage) {
    case "planner": {
      const subQuestions = (event.sub_questions as string[] | undefined) ?? [];
      return subQuestions.length > 1
        ? `Split into ${subQuestions.length} sub-questions`
        : "Narrow enough to research directly";
    }
    case "research":
      return `Gathered ${event.evidence_count ?? 0} evidence item(s) so far${
        Number(event.uploaded_docs_count ?? 0) > 0
          ? ` (${event.uploaded_docs_count} from your uploaded documents)`
          : ""
      }`;
    case "analysis":
      return `${event.key_findings_count ?? 0} key finding(s), ${event.competitors_count ?? 0} competitor(s) identified`;
    case "critic":
      return event.approved
        ? "Findings verified"
        : `Requested another look (${(event.issues as string[] | undefined)?.length ?? 0} issue(s) flagged)`;
    case "report":
      return "Final report ready";
    default:
      return "";
  }
}

export function ProgressLog({ events, isPending }: { events: ProgressEvent[]; isPending: boolean }) {
  if (events.length === 0 && !isPending) return null;

  return (
    <div className="flex flex-col gap-3 border-l-2 border-border pl-4">
      {events.map((event, i) => {
        const meta = STAGE_META[event.stage] ?? { label: event.stage, icon: CheckCircle2 };
        const Icon = meta.icon;
        return (
          <div key={i} className="flex items-start gap-2 text-sm">
            <Icon className="mt-0.5 size-4 shrink-0 text-success" />
            <div>
              <div className="font-medium">{meta.label}</div>
              <div className="text-xs text-muted-foreground">{describeStage(event)}</div>
            </div>
          </div>
        );
      })}
      {isPending && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Working...
        </div>
      )}
    </div>
  );
}
