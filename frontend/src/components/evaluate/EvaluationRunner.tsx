"use client";

import { Loader2, PlayCircle, Zap } from "lucide-react";

import { ResultsTable } from "@/components/evaluate/ResultsTable";
import { SummaryCards } from "@/components/evaluate/SummaryCards";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useEvaluate } from "@/hooks/useEvaluate";

export function EvaluationRunner() {
  const evaluate = useEvaluate();
  const { run } = evaluate;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Runs every question in the golden dataset through the research pipeline and scores retrieval,
          citation accuracy and latency.
        </p>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" onClick={() => run(4)} disabled={evaluate.isPending} title="4 questions spread across all categories - about a third of the time">
            {evaluate.isPending ? <Loader2 className="animate-spin" /> : <Zap />}
            Quick run (4)
          </Button>
          <Button onClick={() => run()} disabled={evaluate.isPending}>
            {evaluate.isPending ? <Loader2 className="animate-spin" /> : <PlayCircle />}
            Full run
          </Button>
        </div>
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
