import { useMutation, useQueryClient } from "@tanstack/react-query";

import { postEvaluate } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

export function useEvaluate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: postEvaluate,
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.evaluate, data);
    },
  });
}
