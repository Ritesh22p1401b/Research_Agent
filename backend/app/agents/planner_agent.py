"""Planner Agent: decomposes a research question into focused sub-questions.

Runs once, before the Research Agent, so a broad ask like "Analyze the Indian
EV market" becomes several narrower searches (market size, competitors,
risks, ...) instead of one unfocused ReAct loop. Narrow questions are left
as a single sub-question so simple factual queries don't pay the extra
LLM-call overhead.
"""
from __future__ import annotations

from app.agents.base import call_llm_json
from app.core.guardrails import StepBudget
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_SUB_QUESTIONS = 4

SYSTEM_PROMPT = """You are the Planning Agent in a multi-agent research platform.
Given a research question, decide how to break it down for thorough research.

- If the question is broad or multi-faceted (e.g. "analyze the X market",
  "research company Y"), split it into 2-4 focused sub-questions that
  together cover distinct angles (e.g. market size/trends, competitors,
  risks/opportunities, financials/operations) - whatever angles are actually
  relevant to this question.
- If the question is already narrow and specific (a single fact or a
  yes/no question), just return it unchanged as the only sub-question.

Respond with a JSON object ONLY, of the form:
{"sub_questions": ["...", "..."]}
Do not include any text outside the JSON object."""


async def run(query: str, budget: StepBudget) -> list[str]:
    user_prompt = f'Research question: "{query}"\n\nProduce the sub-questions JSON now.'
    parsed, _ = await call_llm_json(SYSTEM_PROMPT, user_prompt, budget)

    sub_questions = _clean(parsed.get("sub_questions") if parsed else None)
    if not sub_questions:
        logger.info("Planner returned no usable sub-questions, falling back to the original query")
        return [query]
    return sub_questions


def _clean(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in raw:
        text = str(item).strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        cleaned.append(text)
        if len(cleaned) >= MAX_SUB_QUESTIONS:
            break
    return cleaned

