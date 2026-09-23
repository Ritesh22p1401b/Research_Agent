"""Critic Agent: checks factual support, conflicting sources and missing evidence.

See agentic-research-intelligence-platform.md section 5 for the expected
{"approved": bool, "issues": [...], "missing_evidence": [...]} shape.
"""
from __future__ import annotations

from app.agents.base import call_llm_json
from app.core.guardrails import StepBudget
from app.core.schemas import CriticVerdict

SYSTEM_PROMPT = """You are the Critic Agent in a multi-agent research platform.
You receive the collected evidence and the Analysis Agent's findings. Check:
- every important claim/number is backed by at least one evidence item
- there are no unresolved contradictions between sources
- nothing important seems to be missing
- separately, flag any claim that IS backed by evidence but only weakly -
  a single low-quality source, an outdated figure, or partially conflicting
  sources. These don't have to block approval; they just need hedged
  language later. List each as a short claim string.
Respond with a JSON object ONLY:
{"approved": true|false, "issues": ["..."], "missing_evidence": ["..."], "low_confidence_claims": ["..."]}"""


async def run(query: str, evidence: list[dict], analysis: dict, budget: StepBudget) -> CriticVerdict:
    user_prompt = (
        f"Research question: {query}\n\n"
        f"Evidence count: {len(evidence)}\n\n"
        f"Analysis findings:\n{analysis}\n\n"
        "Evaluate this analysis and respond with the verdict JSON now."
    )
    parsed, _ = await call_llm_json(SYSTEM_PROMPT, user_prompt, budget)
    if not parsed:
        # Fail open with an explicit issue rather than silently approving bad output.
        return CriticVerdict(approved=False, issues=["Critic agent returned no parseable verdict"], missing_evidence=[])
    return CriticVerdict(
        approved=bool(parsed.get("approved", False)),
        issues=list(parsed.get("issues", [])),
        missing_evidence=list(parsed.get("missing_evidence", [])),
        low_confidence_claims=list(parsed.get("low_confidence_claims", [])),
    )
