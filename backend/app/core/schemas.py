"""Shared Pydantic schemas used across API routes, agents and the graph."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Chat -----------------------------------------------------------------
class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)


class ChatUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0


class ChatResponse(BaseModel):
    reply: str
    usage: ChatUsage


# --- Research ---------------------------------------------------------------
class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, description="The research question to investigate")


class Source(BaseModel):
    title: str
    url: str | None = None
    origin: Literal["web", "knowledge_base"] = "web"
    snippet: str | None = None


class EvidenceItem(BaseModel):
    content: str
    source: Source
    relevance_score: float | None = None


class CriticVerdict(BaseModel):
    approved: bool
    issues: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    low_confidence_claims: list[str] = Field(default_factory=list)


class ReportSections(BaseModel):
    executive_summary: str = ""
    market_overview: str = ""
    key_findings: list[str] = Field(default_factory=list)
    competitor_analysis: str = ""
    opportunities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    verification: CriticVerdict | None = None


class ResearchMetrics(BaseModel):
    latency_ms: float = 0.0
    llm_calls: int = 0
    tool_calls: int = 0
    retries: int = 0
    total_tokens: int = 0


class ResearchResponse(BaseModel):
    status: Literal["completed", "failed"]
    report: ReportSections | dict[str, Any] = Field(default_factory=dict)
    sources: list[Source] = Field(default_factory=list)
    metrics: ResearchMetrics = Field(default_factory=ResearchMetrics)
    error: str | None = None


# --- Health -----------------------------------------------------------------
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    llm: str
    qdrant: str | None = None
    postgres: str | None = None


# --- Evaluation ---------------------------------------------------------------
class EvaluateResponse(BaseModel):
    status: Literal["completed", "failed"]
    total_questions: int = 0
    summary: dict[str, Any] = Field(default_factory=dict)
    results: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


# --- Documents ----------------------------------------------------------------
class DocumentSummary(BaseModel):
    id: str
    title: str
    source: str
    chunk_count: int | None = None
    category: str | None = None
    status: Literal["processing", "completed", "failed"] = "completed"


class QueuedUpload(BaseModel):
    document_id: str
    filename: str
    status: Literal["processing"] = "processing"


class UploadDocumentsResponse(BaseModel):
    queued: list[QueuedUpload] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
