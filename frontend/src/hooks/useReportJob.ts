import { useQuery } from "@tanstack/react-query";

import { getReportJob } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

/** Polls the background DOCX generation job until it completes or fails. */
export function useReportJob(jobId: string | null) {
  return useQuery({
    queryKey: queryKeys.reportJob(jobId ?? ""),
    queryFn: () => getReportJob(jobId as string),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" ? false : 2000;
    },
    retry: 1,
  });
}
