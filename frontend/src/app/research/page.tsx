"use client";

import { ExportDocxButton } from "@/components/research/ExportDocxButton";
import { MetricsRow } from "@/components/research/MetricsRow";
import { ProgressLog } from "@/components/research/ProgressLog";
import { ReportDownload } from "@/components/research/ReportDownload";
import { ReportView } from "@/components/research/ReportView";
import { ResearchForm } from "@/components/research/ResearchForm";
import { SourceList } from "@/components/research/SourceList";
import { useResearchStream } from "@/hooks/useResearchStream";

export default function ResearchPage() {
  const { start, progress, result, lastQuery, isPending } = useResearchStream();

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="mb-1 text-xl font-semibold">Research</h1>
        <p className="text-sm text-muted-foreground">
          Runs the full Planner {"→"} Research {"→"} Analysis {"→"} Critic {"→"} Report agent pipeline
          against the knowledge base, the web and any documents you attach, with live progress - then
          writes a full business report as a Word document.
        </p>
      </div>

      <ResearchForm
        onSubmit={(query, options) => start(query, options)}
        isPending={isPending}
      />

      <ProgressLog events={progress} isPending={isPending} />

      {result && (
        <>
          <MetricsRow metrics={result.metrics} />
          <div>
            <ExportDocxButton query={lastQuery} result={result} />
          </div>
          {result.docx_job_id && <ReportDownload jobId={result.docx_job_id} />}
          <ReportView report={result.report} />
          <div>
            <h2 className="mb-2 text-sm font-semibold text-muted-foreground">Sources</h2>
            <SourceList sources={result.sources} />
          </div>
        </>
      )}
    </div>
  );
}
