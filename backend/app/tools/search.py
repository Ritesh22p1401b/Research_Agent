"""Web search tool with pluggable providers.

Default provider is DuckDuckGo (no API key required) so the platform works
out of the box; set WEB_SEARCH_PROVIDER=tavily|serper with the matching
API key for higher-quality results.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the public web for current information and return titles, URLs and snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "max_results": {"type": "integer", "description": "Maximum number of results to return"},
            },
            "required": ["query"],
        },
    },
}


async def run(query: str, max_results: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    limit = min(max_results or settings.max_search_results, settings.max_search_results)

    provider = settings.web_search_provider.lower()
    try:
        if provider == "tavily" and settings.tavily_api_key:
            results = await _search_tavily(query, limit, settings.tavily_api_key)
        elif provider == "serper" and settings.serper_api_key:
            results = await _search_serper(query, limit, settings.serper_api_key)
        else:
            results = await _search_duckduckgo(query, limit)
    except Exception:  # noqa: BLE001
        logger.exception("web_search failed for query=%r via provider=%s", query, provider)
        return {"results": [], "error": "search_failed"}

    return {"results": results}


async def _search_tavily(query: str, limit: int, api_key: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": limit},
        )
        resp.raise_for_status()
        data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in data.get("results", [])[:limit]
    ]


async def _search_serper(query: str, limit: int, api_key: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": limit},
        )
        resp.raise_for_status()
        data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")}
        for r in data.get("organic", [])[:limit]
    ]


async def _search_duckduckgo(query: str, limit: int) -> list[dict[str, Any]]:
    from ddgs import DDGS

    def _sync_search() -> list[dict[str, Any]]:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=limit))
        return [
            {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in raw
        ]

    import asyncio

    return await asyncio.to_thread(_sync_search)
