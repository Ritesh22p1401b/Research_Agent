import { z } from "zod";

import {
  type ChatRequest,
  type ChatResponse,
  type CodeResponse,
  type DocumentStatusResponse,
  type DocumentSummary,
  type EvaluateResponse,
  type HealthResponse,
  type ReportJob,
  type ResearchRequest,
  type ResearchResponse,
  type UploadDocumentsResponse,
  chatResponseSchema,
  codeResponseSchema,
  documentStatusResponseSchema,
  documentSummarySchema,
  evaluateResponseSchema,
  healthResponseSchema,
  reportJobSchema,
  researchResponseSchema,
  uploadDocumentsResponseSchema,
} from "@/lib/api-types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  schema: { parse: (data: unknown) => T },
  init?: RequestInit,
): Promise<T> {
  const isFormData = init?.body instanceof FormData;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      `Could not reach the backend at ${API_BASE_URL}. Is it running?`,
      0,
    );
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(body || `Request failed with status ${response.status}`, response.status);
  }

  const data = await response.json();
  return schema.parse(data);
}

export function getHealth(): Promise<HealthResponse> {
  return request("/health", healthResponseSchema);
}

export function postChat(body: ChatRequest): Promise<ChatResponse> {
  return request("/api/chat", chatResponseSchema, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Streams a plain chat reply token-by-token (SSE over fetch). Calls onDelta for every chunk. */
export async function streamChat(
  body: ChatRequest,
  onDelta: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new ApiError(`Chat request failed (HTTP ${response.status})`, response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const event of events) {
      if (!event.startsWith("data:")) continue;
      const payload = JSON.parse(event.slice(5).trim()) as { delta?: string; error?: string };
      if (payload.error) throw new ApiError(payload.error, 502);
      if (payload.delta) onDelta(payload.delta);
    }
  }
}

export function postCode(body: ChatRequest): Promise<CodeResponse> {
  return request("/api/code", codeResponseSchema, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function postResearch(body: ResearchRequest): Promise<ResearchResponse> {
  return request("/api/research", researchResponseSchema, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function postEvaluate(limit?: number): Promise<EvaluateResponse> {
  return request(`/api/evaluate${limit ? `?limit=${limit}` : ""}`, evaluateResponseSchema, {
    method: "POST",
  });
}

export function getDocuments(): Promise<DocumentSummary[]> {
  return request("/api/documents", z.array(documentSummarySchema));
}

export function getDocumentStatuses(ids: string[]): Promise<DocumentStatusResponse> {
  return request(
    `/api/documents/status?ids=${encodeURIComponent(ids.join(","))}`,
    documentStatusResponseSchema,
  );
}

export function getReportJob(jobId: string): Promise<ReportJob> {
  return request(`/api/reports/${encodeURIComponent(jobId)}`, reportJobSchema);
}

export function generateReport(runId: string, depth: "overview" | "standard" | "comprehensive"): Promise<ReportJob> {
  return request("/api/reports/generate", reportJobSchema, {
    method: "POST",
    body: JSON.stringify({ run_id: runId, depth }),
  });
}

export function reportDownloadUrl(jobId: string): string {
  return `${API_BASE_URL}/api/reports/${encodeURIComponent(jobId)}/download`;
}

export function uploadDocuments(files: File[]): Promise<UploadDocumentsResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  return request("/api/documents", uploadDocumentsResponseSchema, {
    method: "POST",
    body: formData,
  });
}

/** Instant .docx of a finished research result (server builds it without any LLM/KB calls). */
export async function exportResearchDocx(query: string, result: ResearchResponse): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/reports/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      report: result.report,
      sources: result.sources,
      metrics: result.metrics,
    }),
  });
  if (!response.ok) {
    throw new ApiError(`Could not create the document (HTTP ${response.status})`, response.status);
  }
  const blob = await response.blob();
  const match = /filename="?([^";]+)"?/.exec(response.headers.get("Content-Disposition") ?? "");
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = match?.[1] ?? "research_report.docx";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
