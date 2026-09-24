"""Runs the golden evaluation dataset end-to-end through the research graph."""
from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import get_logger
from app.evaluation import metrics
from app.evaluation.dataset import load_dataset
from app.evaluation.judge import judge_report
from app.graph.research_graph import run_research

logger = get_logger(__name__)


async def run_evaluation(limit: int | None = None) -> dict:
    questions = load_dataset()
    if limit and 0 < limit < len(questions):
        # Evenly spaced sample so a quick run still covers every question category.
        step = len(questions) / limit
        questions = [questions[int(i * step)] for i in range(limit)]
    if not questions:
        return {"status": "completed", "total_questions": 0, "summary": {}, "results": []}

    semaphore = asyncio.Semaphore(max(1, get_settings().eval_concurrency))

    async def evaluate_one(q) -> dict:
        async with semaphore:
            outcome = await run_research(q.question, max_retries=get_settings().eval_max_retries)
            report = outcome["report"] or {}
            sources = outcome["sources"] or []
            source_titles = [s.get("title", "") for s in sources]

            retrieval = metrics.retrieval_recall_precision(source_titles, q.expected_source)
            answer_text = " ".join([report.get("executive_summary", "")] + list(report.get("key_findings", [])))
            coverage = metrics.keyword_coverage(answer_text, q.expected_keywords)
            citation_acc = metrics.citation_accuracy(report.get("evidence", []), sources)
            judge = await judge_report(q.question, report, sources)

            return {
                "question": q.question,
                "status": outcome["status"],
                "retrieval_recall": retrieval.recall,
                "retrieval_precision": retrieval.precision,
                "keyword_coverage": coverage,
                "citation_accuracy": citation_acc,
                "judge_faithfulness": judge.faithfulness,
                "judge_completeness": judge.completeness,
                "judge_rationale": judge.rationale,
                "latency_ms": outcome["metrics"]["latency_ms"],
                "llm_calls": outcome["metrics"]["llm_calls"],
                "tool_calls": outcome["metrics"]["tool_calls"],
            }

    # Questions run concurrently (bounded) instead of one after another; result order is preserved.
    results = list(await asyncio.gather(*(evaluate_one(q) for q in questions)))

    summary = metrics.aggregate(results)
    return {
        "status": "completed",
        "total_questions": len(questions),
        "summary": summary,
        "results": results,
    }
