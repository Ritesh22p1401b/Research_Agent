"""LLM-specific configuration, re-exported from the central Settings.

Kept as its own module (per the suggested project layout) so the rest of
the codebase can do ``from app.llm.config import get_llm_settings`` without
depending on the whole app config surface.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    max_retries: int
    temperature: float
    max_tokens: int
    supports_reasoning: bool
    supports_tool_calling: bool


def get_llm_settings() -> LLMSettings:
    s = get_settings()
    return LLMSettings(
        base_url=s.llm_base_url,
        api_key=s.llm_api_key,
        model=s.llm_model,
        timeout_seconds=s.llm_timeout_seconds,
        max_retries=s.llm_max_retries,
        temperature=s.llm_temperature,
        max_tokens=s.llm_max_tokens,
        supports_reasoning=s.llm_supports_reasoning,
        supports_tool_calling=s.llm_supports_tool_calling,
    )
