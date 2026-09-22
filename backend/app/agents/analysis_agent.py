"""Analysis Agent: analyzes evidence, compares information, produces structured findings.

Possible tools (section 5): calculator(), database_query(), python_analysis().
python_analysis is intentionally implemented as the sandboxed `calculator`
tool rather than arbitrary code execution - see app/tools/calculator.py.
"""
from __future__ import annotations

from app.agents.base import run_agent_with_tools
from app.core.guardrails import StepBudget
from app.core.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are the Analysis Agent in a multi-agent research platform.
You receive evidence collected by the Research Agent. Analyze it: compare
sources, identify trends, opportunities, risks and named competitors, and
use the calculator tool for any arithmetic (growth rates, market-size
comparisons, percentages). You may also use database_query for internal
structured data if relevant. Respond with a JSON object ONLY:
{
  "key_findings": ["..."],
  "opportunities": ["..."],
  "risks": ["..."],
  "competitors": ["..."],
  "market_overview": "...",
  "numbers": [{"claim": "...", "value": "...", "supporting_evidence_index": 0}]
}
Do not include any text outside the JSON object."""

TOOLS = ["calculator", "database_query"]


async def run(query: str, evidence: list[dict], budget: StepBudget, tool_timeout_seconds: float) -> dict:
    evidence_block = _format_evidence(evidence)
    user_prompt = (
        f"Research question: {query}\n\nEvidence collected:\n{evidence_block}\n\n"
        "Produce the structured analysis JSON now."
    )
    result = await run_agent_with_tools(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tool_names=TOOLS,
        budget=budget,
        tool_timeout_seconds=tool_timeout_seconds,
    )

    import json

    content = result.content.strip()
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        logger.warning("Analysis agent produced non-JSON output")
        return {"key_findings": [], "opportunities": [], "risks": [], "competitors": [], "market_overview": ""}
    try:
        return json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("Analysis agent JSON parse failed")
        return {"key_findings": [], "opportunities": [], "risks": [], "competitors": [], "market_overview": ""}


def _format_evidence(evidence: list[dict]) -> str:
    lines = []
    for i, item in enumerate(evidence[:30]):
        title = item.get("source_title", "unknown")
        lines.append(f"[{i}] ({title}): {item.get('content', '')[:500]}")
    return "\n".join(lines) if lines else "(no evidence collected)"
