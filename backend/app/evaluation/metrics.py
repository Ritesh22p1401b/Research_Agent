"""Evaluation metrics (section 16): retrieval recall/precision, keyword-based
answer relevance/faithfulness heuristics, latency and token usage.

These are intentionally simple, deterministic heuristics rather than an
LLM-as-judge, so the evaluation suite runs without extra LLM calls/cost.
Swap in an LLM-judge in ``answer_relevance`` if higher-fidelity scoring is
needed later - the function signature is already isolated for that.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetrievalScore:
    recall: float
    precision: float


def retrieval_recall_precision(retrieved_sources: list[str], expected_source: str | None) -> RetrievalScore:
    if not expected_source:
        return RetrievalScore(recall=1.0, precision=1.0)
    hit = any(expected_source.lower() in src.lower() for src in retrieved_sources)
    recall = 1.0 if hit else 0.0
    precision = (1 / len(retrieved_sources)) if hit and retrieved_sources else 0.0
    return RetrievalScore(recall=recall, precision=precision)


def keyword_coverage(answer_text: str, expected_keywords: list[str] | None) -> float:
    if not expected_keywords:
        return 1.0
    answer_lower = answer_text.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
    return hits / len(expected_keywords)


def citation_accuracy(report_evidence: list[str], sources: list[dict]) -> float:
    """Fraction of report citation strings that reference a known source title."""
    if not report_evidence:
        return 0.0
    titles = {s.get("title", "").lower() for s in sources}
    matched = sum(1 for e in report_evidence if any(t and t in e.lower() for t in titles))
    return matched / len(report_evidence)


def aggregate(results: list[dict]) -> dict:
    if not results:
        return {}
    n = len(results)
    return {
        "count": n,
        "avg_retrieval_recall": sum(r["retrieval_recall"] for r in results) / n,
        "avg_retrieval_precision": sum(r["retrieval_precision"] for r in results) / n,
        "avg_keyword_coverage": sum(r["keyword_coverage"] for r in results) / n,
        "avg_citation_accuracy": sum(r["citation_accuracy"] for r in results) / n,
        "avg_latency_ms": sum(r["latency_ms"] for r in results) / n,
        "avg_llm_calls": sum(r["llm_calls"] for r in results) / n,
        "avg_tool_calls": sum(r["tool_calls"] for r in results) / n,
        "task_success_rate": sum(1 for r in results if r["status"] == "completed") / n,
    }
