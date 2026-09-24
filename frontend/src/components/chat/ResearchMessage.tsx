"use client";

import { AlertTriangle, ChevronDown, FileText, Globe, Library, Loader2 } from "lucide-react";
import { useState } from "react";

import { Markdown } from "@/components/chat/Markdown";
import { ProgressLog } from "@/components/research/ProgressLog";
import { ReportOptions } from "@/components/research/ReportOptions";
import type { ReportSections, Source } from "@/lib/api-types";
import { formatMs } from "@/lib/utils";
import type { ResearchRun } from "@/store/chat-store";

function isReport(report: unknown): report is ReportSections {
  return typeof report === "object" && report !== null && "executive_summary" in report;
}

function list(title: string, items: string[]): string {
  return items.length ? `\n\n## ${title}\n\n${items.map((i) => `- ${i}`).join("\n")}` : "";
}

function section(title: string, text: string): string {
  return text ? `\n\n## ${title}\n\n${text}` : "";
}

function reportToMarkdown(r: ReportSections): string {
  let md = "";
  md += section("Executive summary", r.executive_summary);
  md += section("Market overview", r.market_overview);
  md += list("Key findings", r.key_findings);
  md += section("Competitor analysis", r.competitor_analysis);
  md += list("Opportunities", r.opportunities);
  md += list("Risks", r.risks);
  md += list("Evidence", r.evidence);
  const v = r.verification;
  if (v && v.low_confidence_claims.length > 0) {
    md += `\n\n> **Treat with caution** - weakly supported claims:\n${v.low_confidence_claims.map((c) => `> - ${c}`).join("\n")}`;
  }
  if (v && !v.approved && (v.issues.length > 0 || v.missing_evidence.length > 0)) {
    md += `\n\n> **The critic flagged issues:**\n${[...v.issues, ...v.missing_evidence.map((m) => `Missing evidence: ${m}`)]
      .map((i) => `> - ${i}`)
      .join("\n")}`;
  }
  return md.trim();
}

function SourceChips({ sources }: { sources: Source[] }) {
  const [all, setAll] = useState(false);
  if (sources.length === 0) return null;
  const shown = all ? sources : sources.slice(0, 6);
  return (
    <div className="mt-4">
      <div className="mb-2 text-sm font-medium text-muted-foreground">Sources</div>
      <div className="flex flex-wrap gap-2">
        {shown.map((s, i) => {
          const Icon = s.origin === "web" ? Globe : s.origin === "uploaded_document" ? FileText : Library;
          const body = (
            <>
              <span className="text-muted-foreground">{i + 1}</span>
              <Icon className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="max-w-[16rem] truncate">{s.title}</span>
            </>
          );
          const cls =
            "inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 text-xs transition-colors hover:bg-accent";
          return s.url ? (
            <a key={i} href={s.url} target="_blank" rel="noreferrer" className={cls} title={s.url}>
              {body}
            </a>
          ) : (
            <span key={i} className={cls}>
              {body}
            </span>
          );
        })}
        {sources.length > 6 && (
          <button type="button" onClick={() => setAll((v) => !v)} className={`${"rounded-full bg-muted px-3 py-1 text-xs hover:bg-accent"}`}>
            {all ? "Show less" : `+${sources.length - 6} more`}
          </button>
        )}
      </div>
    </div>
  );
}

export function ResearchMessage({ run, query, messageId }: { run: ResearchRun; query: string; messageId: string }) {
  const [open, setOpen] = useState(false);
  const running = run.status === "running";
  const showSteps = open || running;
  const result = run.result;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mb-3 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        {running ? <Loader2 className="size-4 animate-spin" /> : <ChevronDown className={`size-4 transition-transform ${open ? "" : "-rotate-90"}`} />}
        {running
          ? "Researching..."
          : `Researched for ${formatMs(result?.metrics.latency_ms ?? Date.now() - run.startedAt)} · ${run.progress.length} steps`}
      </button>

      {showSteps && (
        <div className="mb-4">
          <ProgressLog events={run.progress} isPending={running} />
        </div>
      )}

      {run.status === "failed" && (
        <p className="flex items-start gap-2 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {run.error ?? "Research failed"}
        </p>
      )}

      {result && isReport(result.report) && <Markdown>{reportToMarkdown(result.report)}</Markdown>}

      {result && <SourceChips sources={result.sources} />}

      {result && result.status === "completed" && (
        <>
          <ReportOptions messageId={messageId} query={query} result={result} jobs={run.jobs} />
          <p className="mt-3 text-xs text-muted-foreground">
            {result.metrics.llm_calls} model calls · {result.metrics.tool_calls} lookups
          </p>
        </>
      )}
    </div>
  );
}
