"""LangGraph wiring for the multi-agent research workflow.

Follows agentic-research-intelligence-platform.md section 14:

    START -> Research Agent -> Analysis Agent -> Critic Agent
                                                     |
                                    approved --------+--------- rejected
                                        |                          |
                                  Report Agent              Research Agent (retry, bounded)
                                        |
                                       END
"""
from __future__ import annotations

import time
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents import analysis_agent, critic_agent, report_agent, research_agent
from app.core.config import get_settings
from app.core.guardrails import GuardrailError, StepBudget
from app.core.logging import get_logger
from app.core.schemas import Source
from app.graph.state import ResearchState
from app.observability.langfuse_client import trace_span

logger = get_logger(__name__)


def _build_graph(budget: StepBudget, tool_timeout: float):
    graph = StateGraph(ResearchState)

    async def research_node(state: ResearchState) -> dict[str, Any]:
        with trace_span("research_agent", query=state["query"]):
            result = await research_agent.run(state["query"], budget, tool_timeout)
        return {"evidence": state.get("evidence", []) + result["evidence"]}

    async def analysis_node(state: ResearchState) -> dict[str, Any]:
        with trace_span("analysis_agent"):
            analysis = await analysis_agent.run(state["query"], state.get("evidence", []), budget, tool_timeout)
        return {"analysis": analysis}

    async def critic_node(state: ResearchState) -> dict[str, Any]:
        with trace_span("critic_agent"):
            verdict = await critic_agent.run(state["query"], state.get("evidence", []), state.get("analysis", {}), budget)
        return {"critic": verdict.model_dump()}

    async def report_node(state: ResearchState) -> dict[str, Any]:
        with trace_span("report_agent"):
            report = await report_agent.run(state["query"], state.get("evidence", []), state.get("analysis", {}), budget)
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

    graph.add_node("research", research_node)
    graph.add_node("analysis", analysis_node)
    graph.add_node("critic", critic_node)
    graph.add_node("report", report_node)

    graph.set_entry_point("research")
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


async def run_research(query: str) -> dict[str, Any]:
    """Entry point used by POST /api/research."""
    settings = get_settings()
    budget = StepBudget(
        max_steps=settings.max_agent_steps,
        max_tool_calls=settings.max_tool_calls,
        max_retries=settings.max_research_retries,
    )
    graph = _build_graph(budget, settings.tool_timeout_seconds)

    start = time.perf_counter()
    try:
        final_state: ResearchState = await graph.ainvoke({"query": query, "evidence": [], "errors": []})
        status = "completed"
        error = None
    except GuardrailError as exc:
        logger.warning("Research workflow stopped by guardrail: %s", exc)
        final_state = {"report": {}, "sources": []}
        status = "failed"
        error = str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Research workflow failed unexpectedly")
        final_state = {"report": {}, "sources": []}
        status = "failed"
        error = str(exc)

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
