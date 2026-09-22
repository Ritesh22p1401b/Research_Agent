"""Hybrid retrieval: dense (Qdrant) + sparse (BM25) fused via Reciprocal Rank Fusion.

Query path (agentic-research-intelligence-platform.md section 6):
    query -> [vector search, BM25 search] -> RRF fusion -> reranker -> top-k
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.rag import vector_store
from app.rag.bm25 import get_bm25_index
from app.rag.embeddings import embed_query

logger = get_logger(__name__)

RRF_K = 60


@dataclass
class RetrievedChunk:
    id: str
    text: str
    metadata: dict[str, Any]
    dense_score: float | None = None
    sparse_score: float | None = None
    fused_score: float = 0.0
    rerank_score: float | None = None


def hybrid_search(query: str, top_k: int = 20, category: str | None = None) -> list[RetrievedChunk]:
    """Runs dense + sparse search and fuses results with Reciprocal Rank Fusion.

    When `category` is given, both the Qdrant payload filter and the BM25
    post-filter restrict results to that topic - this is the "minimum
    retrieval" scoping the Research Agent can opt into per query.
    """
    query_vector = embed_query(query)
    dense_hits = vector_store.search(query_vector, top_k=top_k, filters={"category": category} if category else None)
    sparse_hits = get_bm25_index().search(query, top_k=top_k, category=category)

    fused: dict[str, RetrievedChunk] = {}

    for rank, hit in enumerate(dense_hits):
        chunk = fused.setdefault(
            hit.id, RetrievedChunk(id=hit.id, text=hit.text, metadata=hit.metadata)
        )
        chunk.dense_score = hit.score
        chunk.fused_score += 1.0 / (RRF_K + rank + 1)

    for rank, (doc, score) in enumerate(sparse_hits):
        chunk = fused.setdefault(
            doc.id, RetrievedChunk(id=doc.id, text=doc.text, metadata=doc.metadata)
        )
        chunk.sparse_score = score
        chunk.fused_score += 1.0 / (RRF_K + rank + 1)

    ranked = sorted(fused.values(), key=lambda c: c.fused_score, reverse=True)
    return ranked[:top_k]


def retrieve(query: str, top_k: int = 5, candidate_pool: int = 20, category: str | None = None) -> list[RetrievedChunk]:
    """Full pipeline: hybrid search -> rerank -> top_k."""
    from app.rag.reranker import rerank

    candidates = hybrid_search(query, top_k=candidate_pool, category=category)
    if not candidates:
        logger.info("No retrieval candidates found for query=%r category=%r", query, category)
        return []
    return rerank(query, candidates, top_k=top_k)
