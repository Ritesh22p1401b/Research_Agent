"""Local BM25 sparse index, used alongside Qdrant dense search for hybrid retrieval.

Qdrant handles dense vectors; BM25 handles exact/keyword matching. The
index is small enough (research-assistant scale corpora) to keep in
memory and persist to disk as a pickle built by scripts/ingest.py.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_INDEX_PATH = Path("data") / "bm25_index.pkl"


@dataclass
class BM25Document:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class BM25Index:
    def __init__(self) -> None:
        self._bm25 = None
        self._documents: list[BM25Document] = []

    def build(self, documents: list[BM25Document]) -> None:
        from rank_bm25 import BM25Okapi

        self._documents = documents
        tokenized = [_tokenize(doc.text) for doc in documents]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    def add(self, documents: list[BM25Document]) -> None:
        """Incrementally adds documents (rebuilds the in-memory index; rank_bm25 has no true incremental API)."""
        if not documents:
            return
        self.build(self._documents + documents)

    def search(self, query: str, top_k: int = 10, category: str | None = None) -> list[tuple[BM25Document, float]]:
        if self._bm25 is None or not self._documents:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        pairs = zip(self._documents, scores)
        if category:
            pairs = (p for p in pairs if p[0].metadata.get("category") == category)
        ranked = sorted(pairs, key=lambda pair: pair[1], reverse=True)
        return [(doc, float(score)) for doc, score in ranked[:top_k] if score > 0]

    def save(self, path: Path = DEFAULT_INDEX_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(self._documents, f)

    def load(self, path: Path = DEFAULT_INDEX_PATH) -> bool:
        if not path.exists():
            logger.warning("BM25 index not found at %s; run scripts/ingest.py first", path)
            return False
        with path.open("rb") as f:
            documents: list[BM25Document] = pickle.load(f)
        self.build(documents)
        return True


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


_index_singleton: BM25Index | None = None


def get_bm25_index() -> BM25Index:
    global _index_singleton
    if _index_singleton is None:
        _index_singleton = BM25Index()
        _index_singleton.load()
    return _index_singleton
