"""Deterministic, parallel evidence gathering - the "fast" research path.

The original Research Agent runs a ReAct loop per sub-question: every tool
call costs a full LLM round-trip (~30s on the Colab model). The Planner has
already turned the question into focused sub-questions, so those *are* good
search queries - this module runs the knowledge base, the web and the
user's attached documents for all of them concurrently with **zero LLM
calls**, then hands the pooled evidence to the Analysis agent.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.guardrails import StepBudget
from app.core.logging import get_logger
from app.learning import store as learned_store
from app.tools import documents, search

logger = get_logger(__name__)

KB_TOP_K = 4
WEB_TOP_K = 4
DOC_TOP_K = 4


async def gather_for_query(
    query: str,
    document_ids: list[str],
    *,
    budget: StepBudget | None = None,
    tool_timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """KB + web + attached-document retrieval for one query, all in parallel."""
    tasks: dict[str, Any] = {
        "kb": documents.search_knowledge_base(query=query, top_k=KB_TOP_K),
        "web": search.run(query=query, max_results=WEB_TOP_K),
    }
    if document_ids:
        tasks["docs"] = documents.search_attached_documents(query, document_ids, top_k=DOC_TOP_K)

    if budget is not None:
        # Counted for metrics only - these are cheap parallel lookups, not LLM-driven steps, so they
        # deliberately don't consume the MAX_TOOL_CALLS budget meant for the agentic ReAct loops.
        budget.tool_calls += len(tasks)

    keys = list(tasks)
    outputs = await asyncio.gather(
        *(asyncio.wait_for(tasks[k], timeout=tool_timeout) for k in keys), return_exceptions=True
    )
    by_key = dict(zip(keys, outputs))

    evidence: list[dict[str, Any]] = []

    docs_out = by_key.get("docs")
    if isinstance(docs_out, list):
        for hit in docs_out:
            evidence.append(
                {
                    "content": hit["text"],
                    "source_title": hit["title"],
                    "source_url": None,
                    "origin": "uploaded_document",
                    "document_id": hit.get("document_id"),
                }
            )
    elif isinstance(docs_out, BaseException):
        logger.warning("Attached-document retrieval failed for %r: %s", query, docs_out)

    seen_docs = {e["content"] for e in evidence}
    kb_out = by_key["kb"]
    if isinstance(kb_out, dict):
        for r in kb_out.get("results", []):
            if r["text"] in seen_docs:
                continue
            meta = r.get("metadata", {})
            evidence.append(
                {
                    "content": r["text"],
                    "source_title": meta.get("title", "knowledge base"),
                    "source_url": None,
                    "origin": "knowledge_base",
                    "document_id": meta.get("document_id"),
                }
            )
    else:
        logger.warning("KB retrieval failed for %r: %s", query, kb_out)

    web_out = by_key["web"]
    if isinstance(web_out, dict):
        for r in web_out.get("results", []):
            evidence.append(
                {
                    "content": r.get("snippet", ""),
                    "source_title": r.get("title", ""),
                    "source_url": r.get("url", ""),
                    "origin": "web",
                }
            )
        # Learn from the web: remember what was found so later research (and the coding agent) can reuse it.
        web_hits = [r for r in web_out.get("results", []) if r.get("snippet")]
        if web_hits:
            body = "\n".join(f"- {r.get('title', '')}: {r['snippet']}" for r in web_hits)
            sources = [{"title": r.get("title", ""), "url": r.get("url", "")} for r in web_hits]
            await asyncio.to_thread(learned_store.learn, "web", query, body, sources)
    else:
        logger.warning("Web search failed for %r: %s", query, web_out)

    # Previously learned web knowledge on the same topic (helps when the live search is thin or offline).
    for entry in await asyncio.to_thread(learned_store.recall, query, None, 2, 0.6):
        first = (entry.get("sources") or [{}])[0]
        evidence.append(
            {
                "content": entry["content"][:1500],
                "source_title": first.get("title") or f"Learned: {entry['topic'][:60]}",
                "source_url": first.get("url") or None,
                "origin": "web",
            }
        )

    return [e for e in evidence if e["content"]]


async def gather_document_evidence(queries: list[str], document_ids: list[str]) -> list[dict[str, Any]]:
    """Attached-document evidence only (overview + scoped retrieval) - used to seed the agentic ReAct mode."""
    if not document_ids:
        return []
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in await documents.attached_document_overview(document_ids):
        seen.add(hit["text"])
        evidence.append(_doc_item(hit, "uploaded document overview"))
    scoped = await asyncio.gather(*(documents.search_attached_documents(q, document_ids) for q in queries))
    for query, hits in zip(queries, scoped):
        for hit in hits:
            if hit["text"] not in seen:
                seen.add(hit["text"])
                evidence.append(_doc_item(hit, query))
    return evidence


def _doc_item(hit: dict[str, Any], sub_question: str) -> dict[str, Any]:
    return {
        "content": hit["text"],
        "source_title": hit["title"],
        "source_url": None,
        "origin": "uploaded_document",
        "document_id": hit.get("document_id"),
        "sub_question": sub_question,
    }


async def gather_evidence(
    queries: list[str],
    document_ids: list[str],
    *,
    budget: StepBudget | None = None,
    tool_timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """Runs ``gather_for_query`` for every sub-question concurrently and tags each item with its sub-question.

    Attached documents also contribute an "overview" (their opening chunks) once, so the agents always see what
    the user uploaded even when a sub-question shares no vocabulary with it.
    """
    results = await asyncio.gather(
        *(gather_for_query(q, document_ids, budget=budget, tool_timeout=tool_timeout) for q in queries)
    )
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()

    if document_ids:
        for hit in await documents.attached_document_overview(document_ids):
            seen.add(hit["text"])
            evidence.append(
                {
                    "content": hit["text"],
                    "source_title": hit["title"],
                    "source_url": None,
                    "origin": "uploaded_document",
                    "document_id": hit.get("document_id"),
                    "sub_question": "uploaded document overview",
                }
            )

    for query, items in zip(queries, results):
        for item in items:
            key = item["content"]
            if key in seen:
                continue
            seen.add(key)
            item["sub_question"] = query
            evidence.append(item)
    return evidence
