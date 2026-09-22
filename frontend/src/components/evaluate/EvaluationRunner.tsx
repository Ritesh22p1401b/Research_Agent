"use client";

import { Loader2, PlayCircle } from "lucide-react";
import { toast } from "sonner";

import { ResultsTable } from "@/components/evaluate/ResultsTable";
import { SummaryCards } from "@/components/evaluate/SummaryCards";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useEvaluate } from "@/hooks/useEvaluate";

export function EvaluationRunner() {
  const evaluate = useEvaluate();

  const handleRun = () => {
    evaluate.mutate(undefined, {
      onError: (error) => {
        toast.error(error instanceof Error ? error.message : "Evaluation run failed");
      },
      onSuccess: (data) => {
        if (data.status === "failed") {
          toast.error(data.error ?? "Evaluation run failed");
        } else {
          toast.success(`Evaluated ${data.total_questions} questions`);
        }
      },
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Runs every question in the golden dataset through the research pipeline and scores retrieval,
          citation accuracy and latency.
        </p>
        <Button onClick={handleRun} disabled={evaluate.isPending}>
          {evaluate.isPending ? <Loader2 className="animate-spin" /> : <PlayCircle />}
          Run evaluation
        </Button>
      </div>

      {evaluate.isPending && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      )}

      {evaluate.data && (
        <Tabs defaultValue="summary">
          <TabsList>
            <TabsTrigger value="summary">Summary</TabsTrigger>
            <TabsTrigger value="results">Per-question results</TabsTrigger>
          </TabsList>
          <TabsContent value="summary">
            <SummaryCards summary={evaluate.data.summary} />
          </TabsContent>
          <TabsContent value="results">
            <ResultsTable results={evaluate.data.results} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
