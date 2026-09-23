"""RAG-facing tools: search_knowledge_base (hybrid retrieval) and get_document."""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.logging import get_logger
from app.db.crud import get_document_by_id
from app.db.session import get_session_maker
from app.rag.chunker import chunk_text
from app.rag.classification import get_known_categories
from app.rag.ingestion_manager import get_ingestion_manager
from app.rag.retriever import retrieve

logger = get_logger(__name__)

SEARCH_KB_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "description": (
            "Search internal documents (hybrid dense+BM25 retrieval, reranked) for relevant passages. "
            "If the question clearly relates to one specific topic area (e.g. financial, technical, "
            "competitors, hr_operations, market_research, products, policies_sops, security_compliance, "
            "customer_support, company), pass it as `category` to narrow retrieval to just that topic and "
            "reduce noise. Leave `category` empty to search everything."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "top_k": {"type": "integer", "description": "Number of passages to return"},
                "category": {"type": "string", "description": "Optional topic category to restrict the search to"},
            },
            "required": ["query"],
        },
    },
}

GET_DOCUMENT_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_document",
        "description": "Fetch the full content and metadata of a document by its id.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "The document id"},
            },
            "required": ["document_id"],
        },
    },
}


async def search_knowledge_base(query: str, top_k: int = 5, category: str | None = None) -> dict[str, Any]:
    """Hybrid KB search that cooperates with background ingestion of uploaded documents.

    - Runs under ``manager.retrieval()`` so any in-progress upload pauses for the lookup and resumes after.
    - Documents that are uploaded but not fully indexed yet are searched lexically from memory and merged in,
      so a fresh upload is usable immediately.
    - If the indexed KB has nothing for the query and uploads are pending, ingestion is (re)started.
    """
    manager = get_ingestion_manager()
    matched_category = await _resolve_category(category) if category else None
    async with manager.retrieval():
        try:
            chunks = await asyncio.to_thread(retrieve, query, top_k, 20, matched_category)
        except Exception:  # noqa: BLE001
            logger.exception("search_knowledge_base failed for query=%r", query)
            chunks = None
        staged = manager.search_staged(query, top_k=top_k)

    if not chunks:
        manager.ensure_started()  # KB came up empty -> make sure pending uploads are being ingested

    if chunks is None and not staged:
        return {"results": [], "error": "retrieval_failed"}

    results = [
        {
            "text": c.text,
            "metadata": c.metadata,
            "dense_score": c.dense_score,
            "sparse_score": c.sparse_score,
            "rerank_score": c.rerank_score,
        }
        for c in (chunks or [])
    ]
    seen = {r["text"] for r in results}
    for doc, text, score in staged:
        if text in seen:
            continue
        seen.add(text)
        results.append(
            {
                "text": text,
                "metadata": {"title": doc.title, "source": doc.source, "document_id": doc.id, "category": doc.category},
                "dense_score": None,
                "sparse_score": score,
                "rerank_score": None,
            }
        )
    return {"results": results[: top_k + len(staged)]}


async def search_attached_documents(query: str, document_ids: list[str], top_k: int = 4) -> list[dict[str, Any]]:
    """Retrieval scoped to the documents the user attached to this research run.

    Indexed chunks come from Qdrant/BM25 filtered by document id (reranked); chunks of documents that are still
    being ingested come from the in-memory staged copy. Always paused-ingestion-safe via ``manager.retrieval()``.
    """
    if not document_ids:
        return []
    manager = get_ingestion_manager()
    async with manager.retrieval():
        try:
            chunks = await asyncio.to_thread(retrieve, query, top_k, 20, None, document_ids)
        except Exception:  # noqa: BLE001
            logger.warning("Scoped retrieval failed for attached documents", exc_info=True)
            chunks = []
        staged = manager.search_staged(query, top_k=top_k, document_ids=document_ids)

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in chunks:
        seen.add(c.text)
        out.append({"text": c.text, "title": c.metadata.get("title", "uploaded document"), "document_id": c.metadata.get("document_id")})
    for doc, text, _score in staged:
        if text not in seen:
            seen.add(text)
            out.append({"text": text, "title": doc.title, "document_id": doc.id})
    return out


async def attached_document_overview(document_ids: list[str], chunks_per_doc: int = 2) -> list[dict[str, Any]]:
    """The opening chunks of each attached document - guarantees the agents always see what the user uploaded,
    even when a sub-question shares no vocabulary with it."""
    manager = get_ingestion_manager()
    out: list[dict[str, Any]] = []
    for document_id in document_ids:
        doc = manager.get(document_id)
        if doc is not None and doc.chunks:
            out.extend({"text": c, "title": doc.title, "document_id": doc.id} for c in doc.chunks[:chunks_per_doc])
            continue
        # Fully ingested (staged copy dropped): read the stored text from Postgres instead.
        stored = await get_document(document_id)
        text = (stored.get("content") or "").strip()
        if text:
            out.extend(
                {"text": c, "title": stored.get("title", "uploaded document"), "document_id": document_id}
                for c in chunk_text(text)[:chunks_per_doc]
            )
    return out


async def _resolve_category(requested: str) -> str | None:
    """Matches the LLM's freely-chosen category string against real ones.

    The tool schema only lists examples, not a strict enum (categories grow
    over time as new documents get classified), so an unrecognized guess is
    dropped rather than treated as an error - retrieval just falls back to
    searching everything, which is always safe.
    """
    known = await get_known_categories()
    normalized = requested.strip().lower().replace(" ", "_")
    for candidate in known:
        if candidate.lower() == normalized:
            return candidate
    logger.info("search_knowledge_base: unrecognized category %r (known: %s), searching unfiltered", requested, known)
    return None


async def get_document(document_id: str) -> dict[str, Any]:
    session_maker = get_session_maker()
    async with session_maker() as session:
        doc = await get_document_by_id(session, document_id)
    if doc is None:
        return {"error": "not_found"}
    return {
        "id": doc.id,
        "title": doc.title,
        "source": doc.source,
        "content": doc.content,
        "metadata": doc.doc_metadata,
    }
