"""Read-only database_query tool.

Guardrails (section 15, "Database safety"):
  - only SELECT statements are allowed (regex-enforced, single statement)
  - only tables in DB_TABLE_ALLOWLIST may be queried
  - runs against a read-only DB role/DSN, never the read/write app DSN
  - row limit and query timeout are enforced server-side
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from app.core.config import get_settings
from app.core.guardrails import UnsafeSQLError
from app.core.logging import get_logger
from app.db.session import get_readonly_session_maker

logger = get_logger(__name__)

_SELECT_RE = re.compile(r"^\s*SELECT\s", re.IGNORECASE)
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE|EXEC|CALL|MERGE)\b",
    re.IGNORECASE,
)
_FROM_TABLE_RE = re.compile(r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
_MULTI_STATEMENT_RE = re.compile(r";\s*\S")

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "database_query",
        "description": (
            "Run a read-only SQL SELECT query against allowlisted tables "
            "(documents, execution_traces, evaluation_runs). No writes are permitted."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A single SELECT statement"},
            },
            "required": ["sql"],
        },
    },
}


def validate_query(sql: str) -> None:
    stripped = sql.strip().rstrip(";")
    if not _SELECT_RE.match(stripped):
        raise UnsafeSQLError("Only SELECT statements are allowed")
    if _FORBIDDEN_KEYWORDS.search(stripped):
        raise UnsafeSQLError("Query contains a disallowed keyword")
    if _MULTI_STATEMENT_RE.search(sql):
        raise UnsafeSQLError("Only a single statement is allowed")

    settings = get_settings()
    tables = {m.group(1).lower() for m in _FROM_TABLE_RE.finditer(stripped)}
    if not tables:
        raise UnsafeSQLError("Could not determine target table")
    disallowed = tables - settings.db_table_allowlist_set
    if disallowed:
        raise UnsafeSQLError(f"Table(s) not allowed: {', '.join(sorted(disallowed))}")


def _enforce_limit(sql: str, row_limit: int) -> str:
    stripped = sql.strip().rstrip(";")
    if re.search(r"\bLIMIT\s+\d+\s*$", stripped, re.IGNORECASE):
        return stripped
    return f"{stripped} LIMIT {row_limit}"


async def run(sql: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        validate_query(sql)
    except UnsafeSQLError as exc:
        logger.warning("Rejected unsafe database_query: %s (%s)", sql, exc)
        return {"error": str(exc)}

    bounded_sql = _enforce_limit(sql, settings.db_query_row_limit)
    session_maker = get_readonly_session_maker()
    try:
        async with session_maker() as session:
            await session.execute(text(f"SET LOCAL statement_timeout = {int(settings.db_query_timeout_seconds * 1000)}"))
            result = await session.execute(text(bounded_sql))
            rows = [dict(row._mapping) for row in result.fetchall()]
        return {"rows": rows, "row_count": len(rows)}
    except Exception:
        logger.exception("database_query execution failed for: %s", bounded_sql)
        return {"error": "query_execution_failed"}
