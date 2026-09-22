"""Central tool registry: maps tool name -> OpenAI function schema + async callable.

Agents pass a subset of ``TOOL_SCHEMAS`` to the LLM for function-calling and
dispatch execution through ``TOOL_FUNCTIONS`` (see agents/base.py). Keeping
this in one place is also what the MCP servers wrap (section 7).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.tools import calculator, database, documents, search

ToolFunc = Callable[..., Awaitable[dict[str, Any]]]

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "web_search": search.TOOL_SCHEMA,
    "search_knowledge_base": documents.SEARCH_KB_TOOL_SCHEMA,
    "get_document": documents.GET_DOCUMENT_TOOL_SCHEMA,
    "calculator": calculator.TOOL_SCHEMA,
    "database_query": database.TOOL_SCHEMA,
}

TOOL_FUNCTIONS: dict[str, ToolFunc] = {
    "web_search": lambda **kwargs: search.run(**kwargs),
    "search_knowledge_base": lambda **kwargs: documents.search_knowledge_base(**kwargs),
    "get_document": lambda **kwargs: documents.get_document(**kwargs),
    "calculator": lambda **kwargs: calculator.run(**kwargs),
    "database_query": lambda **kwargs: database.run(**kwargs),
}


def get_tool_schemas(names: list[str]) -> list[dict[str, Any]]:
    return [TOOL_SCHEMAS[name] for name in names if name in TOOL_SCHEMAS]


def get_tool_function(name: str) -> ToolFunc | None:
    return TOOL_FUNCTIONS.get(name)
