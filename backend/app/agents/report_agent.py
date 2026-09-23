"""Report Agent: combines verified findings into the final structured report."""
from __future__ import annotations

from app.agents.base import call_llm_json
from app.core.guardrails import StepBudget
from app.core.schemas import ReportSections

SYSTEM_PROMPT = """You are the Report Agent in a multi-agent research platform.
Combine the verified analysis and evidence into a final research report.
Separate facts (grounded in evidence) from analysis/opinion.

The Critic Agent may flag some claims as "low confidence" (weakly or only
partially supported by evidence). If you include any such claim, hedge the
language explicitly - e.g. "early indications suggest...", "one source
reports, unconfirmed elsewhere...", "preliminary data points to..." - rather
than stating it as settled fact. Do not silently drop low-confidence claims;
hedge them instead so the reader knows to treat them cautiously.

Respond with a JSON object ONLY, matching this shape exactly:
{
  "executive_summary": "...",
  "market_overview": "...",
  "key_findings": ["..."],
  "competitor_analysis": "...",
  "opportunities": ["..."],
  "risks": ["..."],
  "evidence": ["short citation strings, e.g. 'Source Title: key fact'"]
}"""


async def run(
    query: str,
    evidence: list[dict],
    analysis: dict,
    critic: dict,
    budget: StepBudget,
) -> ReportSections:
    low_confidence = critic.get("low_confidence_claims") or []
    hedge_block = (
        "\n\nClaims flagged by the Critic as low-confidence (hedge these if included):\n"
        + "\n".join(f"- {claim}" for claim in low_confidence)
        if low_confidence
        else ""
    )
    user_prompt = (
        f"Research question: {query}\n\n"
        f"Verified analysis:\n{analysis}\n\n"
        f"Evidence available ({len(evidence)} items):\n"
        + "\n".join(f"- {e.get('source_title', 'unknown')}: {e.get('content', '')[:200]}" for e in evidence[:20])
        + hedge_block
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
