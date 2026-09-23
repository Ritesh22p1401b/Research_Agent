export const queryKeys = {
  health: ["health"] as const,
  evaluate: ["evaluate"] as const,
  documents: ["documents"] as const,
  documentStatuses: (ids: string[]) => ["document-statuses", ...ids] as const,
  reportJob: (jobId: string) => ["report-job", jobId] as const,
};
