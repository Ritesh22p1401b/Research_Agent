import { z } from "zod";

import {
  type ChatRequest,
  type ChatResponse,
  type DocumentSummary,
  type EvaluateResponse,
  type HealthResponse,
  type ResearchRequest,
  type ResearchResponse,
  type UploadDocumentsResponse,
  chatResponseSchema,
  documentSummarySchema,
  evaluateResponseSchema,
  healthResponseSchema,
  researchResponseSchema,
  uploadDocumentsResponseSchema,
} from "@/lib/api-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";

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

export function postResearch(body: ResearchRequest): Promise<ResearchResponse> {
  return request("/api/research", researchResponseSchema, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function postEvaluate(): Promise<EvaluateResponse> {
  return request("/api/evaluate", evaluateResponseSchema, {
    method: "POST",
  });
}

export function getDocuments(): Promise<DocumentSummary[]> {
  return request("/api/documents", z.array(documentSummarySchema));
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
