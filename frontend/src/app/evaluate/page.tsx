import { EvaluationRunner } from "@/components/evaluate/EvaluationRunner";

export default function EvaluatePage() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-10">
        <div>
          <h1 className="text-2xl font-semibold">Evaluation</h1>
          <p className="mt-1 text-sm text-muted-foreground">Measure retrieval quality, citation accuracy and answer quality.</p>
        </div>
        <EvaluationRunner />
      </div>
    </div>
  );
}
