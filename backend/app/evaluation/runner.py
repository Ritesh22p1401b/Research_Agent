"""Runs the golden evaluation dataset end-to-end through the research graph."""
from __future__ import annotations

from app.core.logging import get_logger
from app.evaluation import metrics
from app.evaluation.dataset import load_dataset
from app.graph.research_graph import run_research

logger = get_logger(__name__)


async def run_evaluation() -> dict:
    questions = load_dataset()
    if not questions:
        return {"status": "completed", "total_questions": 0, "summary": {}, "results": []}

    results = []
    for q in questions:
        outcome = await run_research(q.question)
        report = outcome["report"] or {}
        sources = outcome["sources"] or []
        source_titles = [s.get("title", "") for s in sources]

        retrieval = metrics.retrieval_recall_precision(source_titles, q.expected_source)
        answer_text = " ".join(
            [report.get("executive_summary", "")] + list(report.get("key_findings", []))
        )
        coverage = metrics.keyword_coverage(answer_text, q.expected_keywords)
        citation_acc = metrics.citation_accuracy(report.get("evidence", []), sources)

        results.append(
            {
                "question": q.question,
                "status": outcome["status"],
                "retrieval_recall": retrieval.recall,
                "retrieval_precision": retrieval.precision,
                "keyword_coverage": coverage,
                "citation_accuracy": citation_acc,
                "latency_ms": outcome["metrics"]["latency_ms"],
                "llm_calls": outcome["metrics"]["llm_calls"],
                "tool_calls": outcome["metrics"]["tool_calls"],
            }
        )

    summary = metrics.aggregate(results)
    return {
        "status": "completed",
        "total_questions": len(questions),
        "summary": summary,
        "results": results,
    }
