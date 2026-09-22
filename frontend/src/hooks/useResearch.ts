import { useMutation } from "@tanstack/react-query";

import { postResearch } from "@/lib/api-client";

export function useResearch() {
  return useMutation({
    mutationFn: (query: string) => postResearch({ query }),
  });
}
