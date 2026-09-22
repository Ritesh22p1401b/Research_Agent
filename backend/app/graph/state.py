"""LangGraph state shared across all research workflow nodes."""
from __future__ import annotations

from typing import Any, TypedDict


class ResearchState(TypedDict, total=False):
    query: str
    evidence: list[dict[str, Any]]
    analysis: dict[str, Any]
    critic: dict[str, Any]
    report: dict[str, Any]
    sources: list[dict[str, Any]]
    retries: int
    errors: list[str]
