/**
 * Zod schemas mirroring backend/app/core/schemas.py exactly. Keep these two
 * files in sync manually - there is no shared codegen between FastAPI and
 * this app yet.
 */
import { z } from "zod";

// --- Chat -------------------------------------------------------------
export const chatMessageSchema = z.object({
  role: z.enum(["user", "assistant", "system"]),
  content: z.string(),
});
export type ChatMessage = z.infer<typeof chatMessageSchema>;

export const chatRequestSchema = z.object({
  message: z.string(),
  history: z.array(chatMessageSchema).default([]),
});
export type ChatRequest = z.infer<typeof chatRequestSchema>;

export const chatUsageSchema = z.object({
  input_tokens: z.number(),
  output_tokens: z.number(),
  total_tokens: z.number(),
  latency_ms: z.number(),
});
export type ChatUsage = z.infer<typeof chatUsageSchema>;

export const chatResponseSchema = z.object({
  reply: z.string(),
  usage: chatUsageSchema,
});
export type ChatResponse = z.infer<typeof chatResponseSchema>;

// --- Research -----------------------------------------------------------
export const researchRequestSchema = z.object({
  query: z.string().min(3),
});
export type ResearchRequest = z.infer<typeof researchRequestSchema>;

export const sourceSchema = z.object({
  title: z.string(),
  url: z.string().nullable(),
  origin: z.enum(["web", "knowledge_base"]),
  snippet: z.string().nullable(),
});
export type Source = z.infer<typeof sourceSchema>;

export const criticVerdictSchema = z.object({
  approved: z.boolean(),
  issues: z.array(z.string()).default([]),
  missing_evidence: z.array(z.string()).default([]),
  low_confidence_claims: z.array(z.string()).default([]),
});
export type CriticVerdict = z.infer<typeof criticVerdictSchema>;

export const reportSectionsSchema = z.object({
  executive_summary: z.string().default(""),
  market_overview: z.string().default(""),
  key_findings: z.array(z.string()).default([]),
  competitor_analysis: z.string().default(""),
  opportunities: z.array(z.string()).default([]),
  risks: z.array(z.string()).default([]),
  evidence: z.array(z.string()).default([]),
  verification: criticVerdictSchema.nullable().default(null),
});
export type ReportSections = z.infer<typeof reportSectionsSchema>;

export const researchMetricsSchema = z.object({
  latency_ms: z.number().default(0),
  llm_calls: z.number().default(0),
  tool_calls: z.number().default(0),
  retries: z.number().default(0),
  total_tokens: z.number().default(0),
});
export type ResearchMetrics = z.infer<typeof researchMetricsSchema>;

export const researchResponseSchema = z.object({
  status: z.enum(["completed", "failed"]),
  report: reportSectionsSchema.or(z.record(z.string(), z.unknown())),
  sources: z.array(sourceSchema).default([]),
  metrics: researchMetricsSchema,
  error: z.string().nullable().default(null),
});
export type ResearchResponse = z.infer<typeof researchResponseSchema>;

// --- Health -----------------------------------------------------------
export const healthResponseSchema = z.object({
  status: z.enum(["ok", "degraded", "error"]),
  llm: z.string(),
  qdrant: z.string().nullable().default(null),
  postgres: z.string().nullable().default(null),
});
export type HealthResponse = z.infer<typeof healthResponseSchema>;

// --- Evaluation ---------------------------------------------------------
export const evaluateResponseSchema = z.object({
  status: z.enum(["completed", "failed"]),
  total_questions: z.number().default(0),
  summary: z.record(z.string(), z.unknown()).default({}),
  results: z.array(z.record(z.string(), z.unknown())).default([]),
  error: z.string().nullable().optional(),
});
export type EvaluateResponse = z.infer<typeof evaluateResponseSchema>;

// --- Documents ----------------------------------------------------------
export const documentSummarySchema = z.object({
  id: z.string(),
  title: z.string(),
  source: z.string(),
  chunk_count: z.number().nullable().default(null),
  category: z.string().nullable().default(null),
  status: z.enum(["processing", "completed", "failed"]).default("completed"),
});
export type DocumentSummary = z.infer<typeof documentSummarySchema>;

export const queuedUploadSchema = z.object({
  document_id: z.string(),
  filename: z.string(),
  status: z.literal("processing"),
});
export type QueuedUpload = z.infer<typeof queuedUploadSchema>;

export const uploadDocumentsResponseSchema = z.object({
  queued: z.array(queuedUploadSchema).default([]),
  errors: z.array(z.string()).default([]),
});
export type UploadDocumentsResponse = z.infer<typeof uploadDocumentsResponseSchema>;

export const ACCEPTED_DOCUMENT_EXTENSIONS = [
  ".pdf",
  ".docx",
  ".md",
  ".markdown",
  ".csv",
  ".json",
  ".html",
  ".htm",
] as const;
