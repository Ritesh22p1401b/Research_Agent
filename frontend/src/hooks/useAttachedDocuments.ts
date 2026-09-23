import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { getDocumentStatuses, uploadDocuments } from "@/lib/api-client";
import type { DocumentSummary, IngestionSnapshot } from "@/lib/api-types";
import { queryKeys } from "@/lib/query-keys";

export type AttachedDocument = {
  id: string;
  filename: string;
  status: DocumentSummary["status"];
  progress: number;
  paused: boolean;
};

const IN_FLIGHT = new Set<DocumentSummary["status"]>(["queued", "processing", "indexing"]);

/**
 * Documents the user attached to the current research session. Uploading returns immediately (the backend
 * parses the file and makes it searchable at once), while indexing into the knowledge base continues in the
 * background - this hook polls that progress so the UI can show it.
 */
export function useAttachedDocuments() {
  const queryClient = useQueryClient();
  const [attached, setAttached] = useState<{ id: string; filename: string }[]>([]);
  const ids = attached.map((d) => d.id);

  const statuses = useQuery({
    queryKey: queryKeys.documentStatuses(ids),
    queryFn: () => getDocumentStatuses(ids),
    enabled: ids.length > 0,
    refetchInterval: (query) =>
      query.state.data?.documents.some((d) => IN_FLIGHT.has(d.status)) ? 1500 : false,
  });

  const mutation = useMutation({
    mutationFn: uploadDocuments,
    onSuccess: (data) => {
      if (data.queued.length > 0) {
        setAttached((prev) => [
          ...prev,
          ...data.queued
            .filter((q) => !prev.some((p) => p.id === q.document_id))
            .map((q) => ({ id: q.document_id, filename: q.filename })),
        ]);
        toast.success(
          `${data.queued.length} document(s) attached - ready to research now, indexing continues in the background`,
        );
      }
      for (const error of data.errors) toast.error(error);
      queryClient.invalidateQueries({ queryKey: queryKeys.documents });
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Upload failed"),
  });

  const remove = useCallback((id: string) => {
    setAttached((prev) => prev.filter((d) => d.id !== id));
  }, []);

  const clear = useCallback(() => setAttached([]), []);

  const byId = new Map((statuses.data?.documents ?? []).map((d) => [d.id, d]));
  const documents: AttachedDocument[] = attached.map((a) => {
    const live = byId.get(a.id);
    return {
      id: a.id,
      filename: a.filename,
      status: live?.status ?? "queued",
      progress: live?.progress ?? 0,
      paused: live?.paused ?? false,
    };
  });

  const ingestion: IngestionSnapshot | null = statuses.data?.ingestion ?? null;

  return {
    documents,
    ids,
    ingestion,
    upload: (files: File[]) => mutation.mutate(files),
    isUploading: mutation.isPending,
    remove,
    clear,
  };
}
