"""Qdrant wrapper: collection management, upsert and dense search."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rag.embeddings import embedding_dimension

logger = get_logger(__name__)


@dataclass
class VectorHit:
    id: str
    score: float
    text: str
    metadata: dict[str, Any]


@lru_cache
def get_client():
    from qdrant_client import QdrantClient

    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=30)


def ensure_collection() -> None:
    from qdrant_client.models import Distance, VectorParams

    settings = get_settings()
    client = get_client()
    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection_name in existing:
        return
    client.create_collection(
        collection_name=settings.qdrant_collection_name,
        vectors_config=VectorParams(size=embedding_dimension(), distance=Distance.COSINE),
    )
    logger.info("Created Qdrant collection '%s'", settings.qdrant_collection_name)


def upsert_chunks(chunks: list[str], vectors: list[list[float]], metadatas: list[dict[str, Any]]) -> list[str]:
    from qdrant_client.models import PointStruct

    settings = get_settings()
    client = get_client()
    ensure_collection()

    ids = [str(uuid.uuid4()) for _ in chunks]
    points = [
        PointStruct(id=ids[i], vector=vectors[i], payload={"text": chunks[i], **metadatas[i]})
        for i in range(len(chunks))
    ]
    client.upsert(collection_name=settings.qdrant_collection_name, points=points)
    return ids


def search(query_vector: list[float], top_k: int = 10, filters: dict[str, Any] | None = None) -> list[VectorHit]:
    settings = get_settings()
    client = get_client()

    qdrant_filter = None
    if filters:
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        # A list value means "any of these" (e.g. a set of document ids), a scalar is an exact match.
        qdrant_filter = Filter(
            must=[
                FieldCondition(key=k, match=MatchAny(any=list(v)) if isinstance(v, (list, tuple, set)) else MatchValue(value=v))
                for k, v in filters.items()
            ]
        )

    try:
        # QdrantClient.search() was removed in newer qdrant-client versions
        # in favor of query_points(), which returns a QueryResponse wrapping
        # the hit list in `.points` instead of returning it directly.
        response = client.query_points(
            collection_name=settings.qdrant_collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
        )
        results = response.points
    except Exception:
        logger.warning("Qdrant search failed (is the collection populated/reachable?)", exc_info=True)
        return []

    hits: list[VectorHit] = []
    for point in results:
        payload = dict(point.payload or {})
        text = payload.pop("text", "")
        hits.append(VectorHit(id=str(point.id), score=point.score, text=text, metadata=payload))
    return hits


def delete_by_document(document_id: str) -> None:
    """Removes every chunk of one document (used to make re-ingestion after an interrupted upload idempotent)."""
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    settings = get_settings()
    client = get_client()
    try:
        client.delete(
            collection_name=settings.qdrant_collection_name,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))])
            ),
        )
    except Exception:
        logger.debug("delete_by_document(%s) skipped", document_id, exc_info=True)
