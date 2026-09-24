"use client";

import { AlertTriangle, ChevronDown, Download, FileText, Loader2, Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { useReportJob } from "@/hooks/useReportJob";
import { exportResearchDocx, generateReport, reportDownloadUrl } from "@/lib/api-client";
import type { ReportSize, ResearchResponse } from "@/lib/api-types";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat-store";

const SIZES: { id: ReportSize; title: string; pages: string; hint: string }[] = [
  { id: "overview", title: "Overview", pages: "5-6 pages", hint: "Short executive briefing" },
  { id: "standard", title: "Detailed report", pages: "15-20 pages", hint: "Full chapters, tables and charts" },
  { id: "comprehensive", title: "Comprehensive report", pages: "50-100 pages", hint: "In-depth business report" },
];

function JobRow({ jobId, label, onRetry }: { jobId: string; label: string; onRetry: () => void }) {
  const { data: job, error } = useReportJob(jobId);
  const running = !job || job.status === "queued" || job.status === "running";

  return (
    <div className="rounded-2xl border border-border p-3 text-sm">
      <div className="flex items-center gap-3">
        <FileText className="size-4 shrink-0 text-muted-foreground" />
        <span className="font-medium">{label}</span>
        <span className="ml-auto flex items-center gap-2">
          {job?.status === "completed" && (
            <a
              href={reportDownloadUrl(job.job_id)}
              download
              className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3.5 py-1 text-xs font-medium text-primary-foreground hover:opacity-90"
            >
              <Download className="size-3.5" /> Download .docx{job.pages_estimate ? ` (~${job.pages_estimate} pages)` : ""}
            </a>
          )}
          {job?.status === "failed" && (
            <button type="button" onClick={onRetry} className="rounded-full border border-border px-3 py-1 text-xs hover:bg-accent">
              Retry
            </button>
          )}
          {running && <span className="tabular-nums text-xs text-muted-foreground">{job?.percent ?? 0}%</span>}
        </span>
      </div>
      {running && (
        <div className="mt-2.5">
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${job?.percent ?? 0}%` }} />
          </div>
          <p className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" />
            {job?.message || "Starting"}
            {job && job.sections_total > 0 && job.stage === "writing" ? ` (${job.sections_done}/${job.sections_total} sections)` : ""}
          </p>
        </div>
      )}
      {job?.status === "failed" && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-destructive">
          <AlertTriangle className="size-3.5" /> {job.error ?? "Report generation failed"}
        </p>
      )}
      {error && !job && <p className="mt-2 text-xs text-destructive">Could not read the report status.</p>}
    </div>
  );
}

/** "Download report" menu shown under a finished research answer: three Word report sizes + an instant summary. */
export function ReportOptions({
  messageId,
  query,
  result,
  jobs,
}: {
  messageId: string;
  query: string;
  result: ResearchResponse;
  jobs: Record<string, string>;
}) {
  const setReportJob = useChatStore((s) => s.setReportJob);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const start = async (size: ReportSize) => {
    setOpen(false);
    if (!result.run_id) return;
    setBusy(size);
    try {
      const job = await generateReport(result.run_id, size);
      setReportJob(messageId, size, job.job_id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not start the report");
    } finally {
      setBusy(null);
    }
  };

  const quick = async () => {
    setOpen(false);
    setBusy("quick");
    try {
      await exportResearchDocx(query, result);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Download failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mt-5 flex flex-col gap-3">
      <div ref={ref} className="relative w-fit">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={cn(
            "inline-flex items-center gap-2 rounded-full border border-border px-4 py-1.5 text-sm transition-colors hover:bg-accent",
            open && "bg-accent",
          )}
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
          Download report
          <ChevronDown className="size-4" />
        </button>

        {open && (
          <div className="absolute bottom-full left-0 z-30 mb-2 w-80 rounded-2xl border border-border bg-card p-1.5 shadow-xl">
            {result.run_id &&
              SIZES.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => start(s.id)}
                  className="flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-accent"
                >
                  <FileText className="mt-0.5 size-5 shrink-0" />
                  <span className="flex-1">
                    <span className="flex items-center justify-between text-sm">
                      {s.title}
                      <span className="text-xs text-muted-foreground">{s.pages}</span>
                    </span>
                    <span className="block text-xs text-muted-foreground">{s.hint}</span>
                  </span>
                </button>
              ))}
            {result.run_id && <div className="my-1 h-px bg-border" />}
            <button
              type="button"
              onClick={quick}
              className="flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-accent"
            >
              <Zap className="mt-0.5 size-5 shrink-0" />
              <span className="flex-1">
                <span className="block text-sm">Quick summary</span>
                <span className="block text-xs text-muted-foreground">Instant, no waiting (2-3 pages)</span>
              </span>
            </button>
          </div>
        )}
      </div>

      {SIZES.filter((s) => jobs[s.id]).map((s) => (
        <JobRow key={s.id} jobId={jobs[s.id]!} label={`${s.title} · ${s.pages}`} onRetry={() => start(s.id)} />
      ))}
    </div>
  );
}
