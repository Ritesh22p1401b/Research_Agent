"""Report Agent: combines verified findings into the final structured report."""
from __future__ import annotations

from app.agents.base import call_llm_json
from app.core.guardrails import StepBudget
from app.core.schemas import ReportSections

SYSTEM_PROMPT = """You are the Report Agent in a multi-agent research platform.
Combine the verified analysis and evidence into a final research report.
Separate facts (grounded in evidence) from analysis/opinion. Respond with a
JSON object ONLY, matching this shape exactly:
{
  "executive_summary": "...",
  "market_overview": "...",
  "key_findings": ["..."],
  "competitor_analysis": "...",
  "opportunities": ["..."],
  "risks": ["..."],
  "evidence": ["short citation strings, e.g. 'Source Title: key fact'"]
}"""


async def run(query: str, evidence: list[dict], analysis: dict, budget: StepBudget) -> ReportSections:
    user_prompt = (
        f"Research question: {query}\n\n"
        f"Verified analysis:\n{analysis}\n\n"
        f"Evidence available ({len(evidence)} items):\n"
        + "\n".join(f"- {e.get('source_title', 'unknown')}: {e.get('content', '')[:200]}" for e in evidence[:20])
        + "\n\nProduce the final report JSON now."
    )
    parsed, _ = await call_llm_json(SYSTEM_PROMPT, user_prompt, budget)
    if not parsed:
        return ReportSections(
            executive_summary="Report generation failed to produce structured output.",
            key_findings=list(analysis.get("key_findings", [])),
            opportunities=list(analysis.get("opportunities", [])),
            risks=list(analysis.get("risks", [])),
        )
    return ReportSections(
        executive_summary=parsed.get("executive_summary", ""),
        market_overview=parsed.get("market_overview", ""),
        key_findings=list(parsed.get("key_findings", [])),
        competitor_analysis=parsed.get("competitor_analysis", ""),
        opportunities=list(parsed.get("opportunities", [])),
        risks=list(parsed.get("risks", [])),
        evidence=list(parsed.get("evidence", [])),
    )
