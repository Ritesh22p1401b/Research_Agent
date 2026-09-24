"""LangGraph wiring for the multi-agent research workflow.

Follows agentic-research-intelligence-platform.md section 14, extended with a
Planner stage that decomposes broad questions before research begins:

    START -> Planner -> Research Agent -> Analysis Agent -> Critic Agent
                                                                 |
                                                approved --------+--------- rejected
                                                    |                          |
                                              Report Agent          Research Agent (targeted retry, bounded)
                                                    |
                                                   END
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents import (
    analysis_agent,
    critic_agent,
    planner_agent,
    report_agent,
    research_agent,
)
from app.agents import evidence as evidence_gathering
from app.core.config import get_settings
from app.core.guardrails import GuardrailError, StepBudget
from app.core.logging import get_logger
from app.core.schemas import Source
from app.graph.state import ResearchState
from app.observability.langfuse_client import trace_span
from app.tools.documents import get_document

logger = get_logger(__name__)

# Sub-question research passes use a shorter ReAct loop than a single-shot
# query so that decomposition doesn't blow through the step/tool-call budget.
SUB_QUESTION_MAX_TOOL_ITERATIONS = 3


async def _document_titles(document_ids: list[str]) -> list[str]:
    from app.rag.ingestion_manager import get_ingestion_manager

    manager = get_ingestion_manager()
    titles: list[str] = []
    for document_id in document_ids:
        staged = manager.get(document_id)
        if staged is not None:
            titles.append(staged.title)
            continue
        stored = await get_document(document_id)
        if stored.get("title"):
            titles.append(stored["title"])
    return titles


def _build_graph(budget: StepBudget, tool_timeout: float, mode: str = "fast"):
    graph = StateGraph(ResearchState)

    async def planner_node(state: ResearchState) -> dict[str, Any]:
        titles = await _document_titles(state.get("document_ids") or [])
        with trace_span("planner_agent", query=state["query"]):
            sub_questions = await planner_agent.run(state["query"], budget, document_titles=titles)
        logger.info("Planner produced %d sub-question(s) for %r", len(sub_questions), state["query"])
        return {"sub_questions": sub_questions}

    async def research_node(state: ResearchState) -> dict[str, Any]:
        critic = state.get("critic")
        if critic:
            # Targeted retry: only chase what the Critic said was missing,
            # instead of re-running every original sub-question from scratch.
            queries = list(critic.get("missing_evidence") or [])[:3] or [state["query"]]
        else:
            queries = state.get("sub_questions") or [state["query"]]

        document_ids = state.get("document_ids") or []
        with trace_span("research_agent", query=state["query"], sub_questions=queries, mode=mode):
            if mode == "fast":
                # No LLM round-trips: KB + web + uploaded documents for every sub-question, in parallel.
                new_evidence = await evidence_gathering.gather_evidence(
                    queries, document_ids, budget=budget, tool_timeout=max(tool_timeout, 20.0)
                )
            else:
                new_evidence = await evidence_gathering.gather_document_evidence(queries, document_ids)
                for sub_query in queries:
                    result = await research_agent.run(
                        sub_query, budget, tool_timeout, max_tool_iterations=SUB_QUESTION_MAX_TOOL_ITERATIONS
                    )
                    for item in result["evidence"]:
                        item.setdefault("sub_question", sub_query)
                    new_evidence.extend(result["evidence"])
        return {"evidence": state.get("evidence", []) + new_evidence}

    async def analysis_node(state: ResearchState) -> dict[str, Any]:
        with trace_span("analysis_agent"):
            analysis = await analysis_agent.run(
                state["query"], state.get("evidence", []), budget, tool_timeout, use_tools=mode != "fast"
            )
        return {"analysis": analysis}

    async def critic_node(state: ResearchState) -> dict[str, Any]:
        with trace_span("critic_agent"):
            verdict = await critic_agent.run(state["query"], state.get("evidence", []), state.get("analysis", {}), budget)
        return {"critic": verdict.model_dump()}

    async def report_node(state: ResearchState) -> dict[str, Any]:
        with trace_span("report_agent"):
            report = await report_agent.run(
                state["query"], state.get("evidence", []), state.get("analysis", {}), state.get("critic") or {}, budget
            )
        report_dict = report.model_dump()
        report_dict["verification"] = state.get("critic")
        return {"report": report_dict, "sources": _extract_sources(state.get("evidence", []))}

    def route_after_critic(state: ResearchState) -> str:
        critic = state.get("critic", {})
        if critic.get("approved"):
            return "report"
        if budget.take_retry():
            logger.info("Critic rejected analysis, retrying research (retry %d/%d)", budget.retries, budget.max_retries)
            return "research"
        logger.info("Critic rejected analysis but retry budget exhausted; producing report with caveats anyway")
        return "report"

    graph.add_node("planner", planner_node)
    graph.add_node("research", research_node)
    graph.add_node("analysis", analysis_node)
    graph.add_node("critic", critic_node)
    graph.add_node("report", report_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "research")
    graph.add_edge("research", "analysis")
    graph.add_edge("analysis", "critic")
    graph.add_conditional_edges("critic", route_after_critic, {"research": "research", "report": "report"})
    graph.add_edge("report", END)

    return graph.compile()


def _extract_sources(evidence: list[dict]) -> list[dict]:
    seen: dict[str, Source] = {}
    for item in evidence:
        title = item.get("source_title") or "unknown"
        key = item.get("source_url") or title
        if key in seen:
            continue
        seen[key] = Source(
            title=title,
            url=item.get("source_url"),
            origin=item.get("origin", "web"),
            snippet=(item.get("content") or "")[:280],
        )
    return [s.model_dump() for s in seen.values()]


def _package_result(
    final_state: dict[str, Any], budget: StepBudget, start: float, status: str, error: str | None
) -> dict[str, Any]:
    latency_ms = (time.perf_counter() - start) * 1000
    return {
        "status": status,
        "report": final_state.get("report", {}),
        "sources": final_state.get("sources", []),
        "metrics": {
            "latency_ms": latency_ms,
            "llm_calls": budget.llm_calls,
            "tool_calls": budget.tool_calls,
            "retries": budget.retries,
            "total_tokens": 0,
        },
        "error": error,
    }


def _new_budget() -> StepBudget:
    settings = get_settings()
    return StepBudget(
        max_steps=settings.max_agent_steps,
        max_tool_calls=settings.max_tool_calls,
        max_retries=settings.max_research_retries,
    )


def _resolve_mode(mode: str | None) -> str:
    resolved = (mode or get_settings().research_mode or "fast").lower()
    return resolved if resolved in {"fast", "agentic"} else "fast"


async def run_research(
    query: str,
    document_ids: list[str] | None = None,
    mode: str | None = None,
    report_depth: str = "none",
    max_retries: int | None = None,
) -> dict[str, Any]:
    """Entry point used by POST /api/research (and the evaluation runner)."""
    settings = get_settings()
    budget = _new_budget()
    if max_retries is not None:
        budget.max_retries = max_retries
    resolved_mode = _resolve_mode(mode)
    graph = _build_graph(budget, settings.tool_timeout_seconds, resolved_mode)

    start = time.perf_counter()
    initial = {"query": query, "evidence": [], "errors": [], "document_ids": document_ids or [], "mode": resolved_mode}
    try:
        final_state: dict[str, Any] = await graph.ainvoke(initial)
        status, error = "completed", None
    except GuardrailError as exc:
        logger.warning("Research workflow stopped by guardrail: %s", exc)
        final_state, status, error = {"report": {}, "sources": []}, "failed", str(exc)
    except Exception as exc:
        logger.exception("Research workflow failed unexpectedly")
        final_state, status, error = {"report": {}, "sources": []}, "failed", str(exc)

    result = _package_result(final_state, budget, start, status, error)
    _maybe_start_docx(result, query, final_state, report_depth)
    return result


def _maybe_start_docx(result: dict[str, Any], query: str, final_state: dict[str, Any], report_depth: str) -> None:
    """Caches the finished run (so a report can be generated on demand) and optionally starts a DOCX job now."""
    if result["status"] != "completed":
        return
    try:
        from app.reporting.runs import save_run

        result["run_id"] = save_run(query, final_state, result["sources"])
    except Exception:
        logger.exception("Could not cache the research run for report generation")
    if report_depth == "none":
        return
    try:
        from app.reporting.jobs import start_report_job

        result["docx_job_id"] = start_report_job(query, final_state, result["sources"], report_depth)
    except Exception:
        logger.exception("Could not start the DOCX report job")


# --- Progress payloads for each node, kept small since they're streamed ------
def _node_progress(node_name: str, delta: dict[str, Any]) -> dict[str, Any]:
    if node_name == "planner":
        return {"stage": "planner", "sub_questions": delta.get("sub_questions", [])}
    if node_name == "research":
        evidence = delta.get("evidence", [])
        return {
            "stage": "research",
            "evidence_count": len(evidence),
            "uploaded_docs_count": sum(1 for e in evidence if e.get("origin") == "uploaded_document"),
        }
    if node_name == "analysis":
        analysis = delta.get("analysis", {}) or {}
        return {
            "stage": "analysis",
            "key_findings_count": len(analysis.get("key_findings", [])),
            "competitors_count": len(analysis.get("competitors", [])),
        }
    if node_name == "critic":
        critic = delta.get("critic", {}) or {}
        return {
            "stage": "critic",
            "approved": critic.get("approved", False),
            "issues": critic.get("issues", []),
            "low_confidence_claims": critic.get("low_confidence_claims", []),
        }
    if node_name == "report":
        return {"stage": "report", "report": delta.get("report", {}), "sources": delta.get("sources", [])}
    return {"stage": node_name}


async def run_research_stream(
    query: str,
    document_ids: list[str] | None = None,
    mode: str | None = None,
    report_depth: str = "standard",
) -> AsyncIterator[dict[str, Any]]:
    """Streaming counterpart to ``run_research``, used by GET /api/research/stream.

    Yields ``{"event": ..., "data": ...}`` dicts as each graph node finishes,
    via LangGraph's ``stream_mode="updates"`` (one delta dict per node) rather
    than duplicating the node logic - the final ``"done"`` event carries the
    exact same payload shape ``run_research`` returns, so callers only need
    to build one result-handling code path.
    """
    settings = get_settings()
    budget = _new_budget()
    resolved_mode = _resolve_mode(mode)
    graph = _build_graph(budget, settings.tool_timeout_seconds, resolved_mode)

    start = time.perf_counter()
    final_state: dict[str, Any] = {
        "query": query,
        "evidence": [],
        "errors": [],
        "document_ids": document_ids or [],
        "mode": resolved_mode,
    }
    try:
        async for update in graph.astream(final_state, stream_mode="updates"):
            for node_name, delta in update.items():
                final_state.update(delta)
                yield {"event": "node_complete", "data": _node_progress(node_name, delta)}
        status, error = "completed", None
    except GuardrailError as exc:
        logger.warning("Research workflow stopped by guardrail: %s", exc)
        status, error = "failed", str(exc)
        yield {"event": "error", "data": {"message": error}}
    except Exception as exc:
        logger.exception("Research workflow failed unexpectedly")
        status, error = "failed", str(exc)
        yield {"event": "error", "data": {"message": error}}

    result = _package_result(final_state, budget, start, status, error)
    _maybe_start_docx(result, query, final_state, report_depth)
    yield {"event": "done", "data": result}
