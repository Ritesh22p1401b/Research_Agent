"""MCP server exposing read-only database/document capabilities.

Run standalone with:
    python -m app.mcp.database_server

Guardrails (section 7 & 15): read-only DB role, table allowlist, row limits
and query timeouts are enforced inside app.tools.database.run itself.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.core.guardrails import run_with_timeout
from app.core.logging import get_logger
from app.tools import database, documents

logger = get_logger(__name__)
settings = get_settings()

mcp = FastMCP("research-database-server")


def _allowed(name: str) -> bool:
    if name not in settings.mcp_tool_allowlist_set:
        logger.warning("Blocked MCP call to non-allowlisted tool: %s", name)
        return False
    return True


@mcp.tool()
async def database_query(sql: str) -> dict:
    """Run a read-only SELECT query against allowlisted tables."""
    if not _allowed("database_query"):
        return {"error": "tool_not_allowed"}
    logger.info("MCP database_query: %s", sql)
    return await run_with_timeout(
        database.run, sql=sql, timeout=settings.tool_timeout_seconds, tool_name="database_query"
    )


@mcp.tool()
async def get_document(document_id: str) -> dict:
    """Fetch a document's full content and metadata by id."""
    if not _allowed("get_document"):
        return {"error": "tool_not_allowed"}
    logger.info("MCP get_document: %s", document_id)
    return await run_with_timeout(
        documents.get_document,
        document_id=document_id,
        timeout=settings.tool_timeout_seconds,
        tool_name="get_document",
    )


if __name__ == "__main__":
    mcp.run()
