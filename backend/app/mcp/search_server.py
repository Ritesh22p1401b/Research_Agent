"""MCP server exposing search capabilities (web_search, search_knowledge_base).

Run standalone with:
    python -m app.mcp.search_server

Guardrails (section 7): only allowlisted tools are exposed, every call is
logged and bounded by TOOL_TIMEOUT_SECONDS.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.core.guardrails import run_with_timeout
from app.core.logging import get_logger
from app.tools import documents, search

logger = get_logger(__name__)
settings = get_settings()

mcp = FastMCP("research-search-server")


def _allowed(name: str) -> bool:
    if name not in settings.mcp_tool_allowlist_set:
        logger.warning("Blocked MCP call to non-allowlisted tool: %s", name)
        return False
    return True


@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> dict:
    """Search the public web and return titles, URLs and snippets."""
    if not _allowed("web_search"):
        return {"error": "tool_not_allowed"}
    logger.info("MCP web_search: %r", query)
    return await run_with_timeout(
        search.run, query=query, max_results=max_results, timeout=settings.tool_timeout_seconds, tool_name="web_search"
    )


@mcp.tool()
async def search_knowledge_base(query: str, top_k: int = 5) -> dict:
    """Hybrid dense+BM25 search over the internal document knowledge base."""
    if not _allowed("search_knowledge_base"):
        return {"error": "tool_not_allowed"}
    logger.info("MCP search_knowledge_base: %r", query)
    return await run_with_timeout(
        documents.search_knowledge_base,
        query=query,
        top_k=top_k,
        timeout=settings.tool_timeout_seconds,
        tool_name="search_knowledge_base",
    )


if __name__ == "__main__":
    mcp.run()
