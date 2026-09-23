import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getDocuments, uploadDocuments } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

export function useDocuments(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.documents,
    queryFn: getDocuments,
    enabled,
    // Poll while the dialog is open so documents flip from "processing" to
    // "completed" (with their classified category) as background ingestion
    // finishes, without the user needing to reopen the dialog.
    refetchInterval: (query) => {
      if (!enabled) return false;
      const stillProcessing = query.state.data?.some(
        (doc) => doc.status === "queued" || doc.status === "processing" || doc.status === "indexing",
      );
      return stillProcessing ? 2000 : false;
    },
  });
}

export function useUploadDocuments() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: uploadDocuments,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents });
    },
  });
}
