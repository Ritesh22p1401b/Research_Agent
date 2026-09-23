"use client";

import { useEffect } from "react";
import { toast } from "sonner";

import { MetricsRow } from "@/components/research/MetricsRow";
import { ProgressLog } from "@/components/research/ProgressLog";
import { ReportView } from "@/components/research/ReportView";
import { ResearchForm } from "@/components/research/ResearchForm";
import { SourceList } from "@/components/research/SourceList";
import { useResearchStream } from "@/hooks/useResearchStream";

export default function ResearchPage() {
  const { start, progress, result, status, error, isPending } = useResearchStream();

  useEffect(() => {
    if (status === "failed" && error) {
      toast.error(error);
    }
  }, [status, error]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="mb-1 text-xl font-semibold">Research</h1>
        <p className="text-sm text-muted-foreground">
          Runs the full Planner {"→"} Research {"→"} Analysis {"→"} Critic {"→"} Report agent pipeline
          against the knowledge base and the web, with live progress.
        </p>
      </div>

      <ResearchForm onSubmit={start} isPending={isPending} />

      <ProgressLog events={progress} isPending={isPending} />

      {result && (
        <>
          <MetricsRow metrics={result.metrics} />
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
