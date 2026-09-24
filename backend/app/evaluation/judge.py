"""LLM-as-judge scoring for evaluation reports (section 16).

Complements the deterministic heuristics in ``metrics.py`` (keyword coverage,
citation accuracy) with an actual quality judgment from the LLM: does the
report's language stay faithful to the retrieved sources, and does it
substantively answer the question. Runs as a single extra ``chat_json`` call
per question, independent of the per-request ``StepBudget`` since evaluation
runs offline, outside any user-facing guardrail window.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.llm.client import get_llm_client

logger = get_logger(__name__)

JUDGE_PROMPT = """You are an impartial evaluation judge for an AI research report.

Research question:
{question}

Report produced by the AI:
Executive summary: {executive_summary}
Key findings: {key_findings}
Market overview: {market_overview}

Sources the AI had access to:
{sources_block}

Score the report from 0.0 to 1.0 on two dimensions:
- faithfulness: are the report's claims actually grounded in the sources above, with no invented facts?
- completeness: does the report substantively address the research question?

Respond with a JSON object ONLY:
{{"faithfulness": 0.0, "completeness": 0.0, "rationale": "one sentence explaining the scores"}}"""


@dataclass
class JudgeScore:
    faithfulness: float
    completeness: float
    rationale: str


async def judge_report(question: str, report: dict[str, Any], sources: list[dict[str, Any]]) -> JudgeScore:
    sources_block = (
        "\n".join(f"- {s.get('title', 'unknown')}: {s.get('snippet', '') or ''}" for s in sources[:15])
        or "(no sources retrieved)"
    )

    prompt = JUDGE_PROMPT.format(
        question=question,
        executive_summary=report.get("executive_summary", ""),
        key_findings=report.get("key_findings", []),
        market_overview=report.get("market_overview", ""),
        sources_block=sources_block,
    )
    try:
        parsed, _ = await get_llm_client().chat_json(
            messages=[{"role": "user", "content": prompt}], temperature=0.0, max_tokens=200
        )
        return JudgeScore(
            faithfulness=_clamp(parsed.get("faithfulness")),
            completeness=_clamp(parsed.get("completeness")),
            rationale=str(parsed.get("rationale", "")),
        )
    except Exception:
        logger.warning("LLM-judge scoring failed for question=%r", question, exc_info=True)
        return JudgeScore(faithfulness=0.0, completeness=0.0, rationale="judge call failed")


def _clamp(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
