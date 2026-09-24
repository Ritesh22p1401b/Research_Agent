import { useEvaluateStore } from "@/store/evaluate-store";

export function useEvaluate() {
  const run = useEvaluateStore((s) => s.run);
  const isPending = useEvaluateStore((s) => s.isPending);
  const data = useEvaluateStore((s) => s.data);
  return { run, isPending, data };
}
