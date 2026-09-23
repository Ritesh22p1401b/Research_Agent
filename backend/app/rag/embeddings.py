"""Local embedding model wrapper.

Embeddings run locally (sentence-transformers on CPU/GPU), NOT on the
remote Qwen3/Colab endpoint - that endpoint is reserved for LLM inference
(agentic-research-intelligence-platform.md section 8: "Colab should
primarily be responsible for LLM inference").
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def _get_model():
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    logger.info("Loading embedding model %s on %s", settings.embedding_model_name, settings.embedding_device)
    return SentenceTransformer(settings.embedding_model_name, device=settings.embedding_device)


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def embed_query(query: str) -> list[float]:
    return embed_texts([query])[0]


def embedding_dimension() -> int:
    model = _get_model()
    return int(model.get_sentence_embedding_dimension())


def warm_up() -> None:
    """Loads the embedder, reranker and BM25 index up-front (called once at app startup).

    Without this the first research request pays 10-30s of model loading in the middle of the run.
    """
    from app.rag.bm25 import get_bm25_index
    from app.rag.reranker import _get_cross_encoder

    try:
        _get_model()
        _get_cross_encoder()
        get_bm25_index()
        logger.info("RAG models warmed up")
    except Exception:  # noqa: BLE001
        logger.warning("RAG warm-up failed (will lazy-load on first use)", exc_info=True)
