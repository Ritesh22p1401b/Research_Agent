import { toast } from "sonner";
import { create } from "zustand";

import { postEvaluate } from "@/lib/api-client";
import type { EvaluateResponse } from "@/lib/api-types";

/** Evaluation run state, in memory only: kept across page switches (the request keeps running), cleared on refresh. */
interface EvaluateState {
  isPending: boolean;
  data: EvaluateResponse | null;
  run: (limit?: number) => void;
}

export const useEvaluateStore = create<EvaluateState>()((set, get) => ({
  isPending: false,
  data: null,
  run: (limit) => {
    if (get().isPending) return;
    set({ isPending: true });
    postEvaluate(limit)
      .then((data) => {
        set({ data, isPending: false });
        if (data.status === "failed") toast.error(data.error ?? "Evaluation run failed");
        else toast.success(`Evaluated ${data.total_questions} questions`);
      })
      .catch((error: unknown) => {
        set({ isPending: false });
        toast.error(error instanceof Error ? error.message : "Evaluation run failed");
      });
  },
}));
