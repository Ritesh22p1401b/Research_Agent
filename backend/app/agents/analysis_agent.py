"""Analysis Agent: analyzes evidence, compares information, produces structured findings.

Possible tools (section 5): calculator(), database_query(), python_analysis().
python_analysis is intentionally implemented as the sandboxed `calculator`
tool rather than arbitrary code execution - see app/tools/calculator.py.
"""
from __future__ import annotations

from app.agents.base import call_llm_json, run_agent_with_tools
from app.core.config import get_settings
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


FAST_SYSTEM_PROMPT = (
    SYSTEM_PROMPT.split(", and\nuse the calculator")[0]
    + ". Compute any percentages or growth rates yourself, carefully, and only from figures present in the evidence."
    + "\nRespond with a JSON object ONLY:"
    + SYSTEM_PROMPT.split("Respond with a JSON object ONLY:")[1]
)


async def run(
    query: str,
    evidence: list[dict],
    budget: StepBudget,
    tool_timeout_seconds: float,
    use_tools: bool = True,
) -> dict:
    evidence_block = _format_evidence(evidence)
    user_prompt = (
        f"Research question: {query}\n\nEvidence collected:\n{evidence_block}\n\n"
        "Produce the structured analysis JSON now."
    )
    if use_tools:
        result = await run_agent_with_tools(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            tool_names=TOOLS,
            budget=budget,
            tool_timeout_seconds=tool_timeout_seconds,
        )
        content = result.content.strip()
    else:
        # Fast path: one direct JSON call instead of a tool-calling loop (saves 1-3 LLM round-trips).
        parsed, llm_result = await call_llm_json(
            FAST_SYSTEM_PROMPT, user_prompt, budget, max_tokens=get_settings().analysis_max_tokens
        )
        if parsed:
            return parsed
        content = llm_result.content.strip()

    import json

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
    for i, item in enumerate(evidence[:36]):
        title = item.get("source_title", "unknown")
        lines.append(f"[{i}] ({title}): {item.get('content', '')[:500]}")
    return "\n".join(lines) if lines else "(no evidence collected)"
