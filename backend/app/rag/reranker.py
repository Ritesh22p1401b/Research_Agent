"""Cross-encoder reranking of hybrid retrieval candidates."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rag.retriever import RetrievedChunk

logger = get_logger(__name__)


@lru_cache
def _get_cross_encoder():
    from sentence_transformers import CrossEncoder

    settings = get_settings()
    logger.info("Loading reranker model %s", settings.reranker_model_name)
    return CrossEncoder(settings.reranker_model_name)


def rerank(query: str, candidates: list[RetrievedChunk], top_k: int = 5) -> list[RetrievedChunk]:
    if not candidates:
        return []
    try:
        model = _get_cross_encoder()
        pairs = [(query, c.text) for c in candidates]
        scores = model.predict(pairs)
    except Exception:
        logger.warning("Reranker unavailable, falling back to hybrid ranking order", exc_info=True)
        return candidates[:top_k]

    for candidate, score in zip(candidates, scores):
        candidate.rerank_score = float(score)

    ranked = sorted(candidates, key=lambda c: c.rerank_score or 0.0, reverse=True)
    return ranked[:top_k]
