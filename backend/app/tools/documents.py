"""RAG-facing tools: search_knowledge_base (hybrid retrieval) and get_document."""
from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.db.crud import get_document_by_id
from app.db.session import get_session_maker
from app.rag.classification import get_known_categories
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
    matched_category = await _resolve_category(category) if category else None
    try:
        chunks = retrieve(query, top_k=top_k, category=matched_category)
    except Exception:  # noqa: BLE001
        logger.exception("search_knowledge_base failed for query=%r", query)
        return {"results": [], "error": "retrieval_failed"}

    return {
        "results": [
            {
                "text": c.text,
                "metadata": c.metadata,
                "dense_score": c.dense_score,
                "sparse_score": c.sparse_score,
                "rerank_score": c.rerank_score,
            }
            for c in chunks
        ]
    }


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
