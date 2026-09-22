"use client";

import { toast } from "sonner";

import { MetricsRow } from "@/components/research/MetricsRow";
import { ReportView } from "@/components/research/ReportView";
import { ResearchForm } from "@/components/research/ResearchForm";
import { SourceList } from "@/components/research/SourceList";
import { Skeleton } from "@/components/ui/skeleton";
import { useResearch } from "@/hooks/useResearch";

export default function ResearchPage() {
  const research = useResearch();

  const handleSubmit = (query: string) => {
    research.mutate(query, {
      onError: (error) => {
        toast.error(error instanceof Error ? error.message : "Research request failed");
      },
      onSuccess: (data) => {
        if (data.status === "failed") {
          toast.error(data.error ?? "Research workflow failed");
        }
      },
    });
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="mb-1 text-xl font-semibold">Research</h1>
        <p className="text-sm text-muted-foreground">
          Runs the full Research {"→"} Analysis {"→"} Critic {"→"} Report agent pipeline
          against the knowledge base and the web.
        </p>
      </div>

      <ResearchForm onSubmit={handleSubmit} isPending={research.isPending} />

      {research.isPending && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {research.data && (
        <>
          <MetricsRow metrics={research.data.metrics} />
          <ReportView report={research.data.report} />
          <div>
            <h2 className="mb-2 text-sm font-semibold text-muted-foreground">Sources</h2>
            <SourceList sources={research.data.sources} />
          </div>
        </>
      )}
    </div>
  );
}
