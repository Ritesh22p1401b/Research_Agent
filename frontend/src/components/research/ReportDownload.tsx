"use client";

import { AlertTriangle, Download, FileText, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useReportJob } from "@/hooks/useReportJob";
import { reportDownloadUrl } from "@/lib/api-client";

export function ReportDownload({ jobId }: { jobId: string }) {
  const { data: job, error } = useReportJob(jobId);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <FileText className="size-4" /> Business report (Word document)
        </CardTitle>
        {job?.status === "completed" && (
          <Button asChild size="sm">
            <a href={reportDownloadUrl(job.job_id)} download>
              <Download /> Download .docx
              {job.pages_estimate ? ` (~${job.pages_estimate} pages)` : ""}
            </a>
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {error && !job && (
          <p className="flex items-center gap-2 text-sm text-destructive">
            <AlertTriangle className="size-4" /> Could not read the report status.
          </p>
        )}
        {job && job.status !== "completed" && job.status !== "failed" && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              <span>
                {job.message || "Generating"}
                {job.sections_total > 0 && job.stage === "writing"
                  ? ` (${job.sections_done}/${job.sections_total} sections)`
                  : ""}
              </span>
              <span className="ml-auto tabular-nums">{job.percent}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all duration-500"
                style={{ width: `${job.percent}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Runs in the background - you can keep using the app. Long, chart-rich reports take several minutes.
            </p>
          </div>
        )}
        {job?.status === "completed" && (
          <p className="text-sm text-muted-foreground">
            Cover page, contents, executive summary, chapters with tables and charts, risk assessment,
            recommendations, methodology and a full source register.
          </p>
        )}
        {job?.status === "failed" && (
          <p className="flex items-center gap-2 text-sm text-destructive">
            <AlertTriangle className="size-4" /> Report generation failed: {job.error ?? "unknown error"}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
