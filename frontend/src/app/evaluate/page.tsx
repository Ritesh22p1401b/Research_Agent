import { EvaluationRunner } from "@/components/evaluate/EvaluationRunner";

export default function EvaluatePage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Evaluation</h1>
      <EvaluationRunner />
    </div>
  );
}
