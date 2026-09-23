"""Research Agent: understands the question, searches sources, collects evidence.

Responsibilities (agentic-research-intelligence-platform.md section 5):
web_search(), search_knowledge_base(), get_document().
"""
from __future__ import annotations

import json

from app.agents.base import run_agent_with_tools
from app.core.guardrails import StepBudget
from app.core.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are the Research Agent in a multi-agent research platform.
Your job: given a research question, gather concrete, sourced evidence using
the available tools (web_search, search_knowledge_base, get_document).
Search both the web and the internal knowledge base. When calling
search_knowledge_base, pass a `category` if the question is clearly scoped
to one topic area - this narrows retrieval to only related documents instead
of searching the entire knowledge base. Prefer specific facts, figures and
named sources over generalities. When you are done gathering evidence,
respond with a JSON object ONLY, of the form:
{"evidence": [{"content": "...", "source_title": "...", "source_url": "...", "origin": "web"|"knowledge_base"}]}
Do not include any text outside the JSON object in your final answer."""

TOOLS = ["web_search", "search_knowledge_base", "get_document"]


async def run(
    query: str,
    budget: StepBudget,
    tool_timeout_seconds: float,
    max_tool_iterations: int = 4,
) -> dict:
    user_prompt = f"Research question: {query}\n\nGather evidence to answer this thoroughly."
    result = await run_agent_with_tools(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tool_names=TOOLS,
        budget=budget,
        tool_timeout_seconds=tool_timeout_seconds,
        max_tool_iterations=max_tool_iterations,
    )

    evidence = _parse_evidence(result.content)
    if not evidence:
        # Fall back to raw tool outputs so the pipeline still has something to analyze.
        evidence = _evidence_from_tool_traces(result.tool_traces)

    return {"evidence": evidence, "tool_calls": len(result.tool_traces)}


def _parse_evidence(content: str) -> list[dict]:
    content = content.strip()
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        return []
    try:
        parsed = json.loads(content[start : end + 1])
        return parsed.get("evidence", [])
    except json.JSONDecodeError:
        logger.warning("Research agent produced non-JSON evidence output")
        return []


def _evidence_from_tool_traces(tool_traces) -> list[dict]:
    evidence = []
    for trace in tool_traces:
        if trace.name == "web_search":
            for r in trace.result.get("results", []):
                evidence.append(
                    {
                        "content": r.get("snippet", ""),
                        "source_title": r.get("title", ""),
                        "source_url": r.get("url", ""),
                        "origin": "web",
                    }
                )
        elif trace.name == "search_knowledge_base":
            for r in trace.result.get("results", []):
                evidence.append(
                    {
                        "content": r.get("text", ""),
                        "source_title": r.get("metadata", {}).get("title", "knowledge base"),
                        "source_url": None,
                        "origin": "knowledge_base",
                    }
                )
    return evidence
