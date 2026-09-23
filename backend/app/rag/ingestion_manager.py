"""Background ingestion of uploaded documents with a retrieval-priority pause gate.

Uploaded documents are parsed immediately and become *searchable at once*
(a small in-memory BM25 over their chunks - the "staged" copy), while the
slow part - embedding every chunk and upserting it into Qdrant + the
persistent BM25 index - runs in a background worker in small batches.

Between batches the worker waits on a gate. Whenever an agent needs the
knowledge base it wraps its lookup in ``manager.retrieval()``: that closes the
gate (the worker pauses at the next batch boundary, after the in-flight batch
finishes), the lookup runs with the embedder/Qdrant/BM25 to itself, and when
the last concurrent lookup finishes the gate re-opens and the upload resumes
exactly where it stopped. Retrieval always wins over ingestion.
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are", "was", "were", "what",
    "how", "why", "which", "who", "by", "at", "as", "it", "its", "this", "that", "from", "be", "has", "have",
}
CLASSIFY_TIMEOUT_SECONDS = 45.0


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


@dataclass
class StagedDocument:
    id: str
    title: str
    source: str
    text: str
    chunks: list[str] = field(default_factory=list)
    category: str = "general"
    status: str = "queued"  # queued | indexing | completed | failed
    indexed_chunks: int = 0
    error: str | None = None
    _bm25: Any = None
    _chunk_tokens: list[list[str]] = field(default_factory=list)

    @property
    def progress(self) -> int:
        if self.status == "completed":
            return 100
        if not self.chunks:
            return 0
        return int(100 * self.indexed_chunks / len(self.chunks))

    def search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        """Lexical search over this document's raw chunks (works before/without any embedding)."""
        if not self.chunks:
            return []
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        if not self._chunk_tokens:
            self._chunk_tokens = [_tokens(c) for c in self.chunks]
        scored: list[tuple[str, float]] = []
        wanted = set(query_tokens)
        try:
            if self._bm25 is None:
                from rank_bm25 import BM25Okapi

                self._bm25 = BM25Okapi(self._chunk_tokens)
            scores = self._bm25.get_scores(query_tokens)
            scored = [(c, float(s)) for c, s in zip(self.chunks, scores) if s > 0]
        except Exception:  # noqa: BLE001
            scored = []
        if not scored:  # tiny corpora give BM25 zero/negative idf - fall back to plain term overlap
            for chunk, toks in zip(self.chunks, self._chunk_tokens):
                overlap = len(wanted.intersection(toks))
                if overlap:
                    scored.append((chunk, float(overlap)))
        scored.sort(key=lambda p: p[1], reverse=True)
        return scored[:top_k]


class IngestionManager:
    def __init__(self, batch_size: int | None = None) -> None:
        self._batch_size = batch_size or get_settings().ingest_batch_size
        self._docs: dict[str, StagedDocument] = {}
        self._queue: list[str] = []
        self._worker: asyncio.Task | None = None
        self._gate: asyncio.Event | None = None  # set = ingestion may run
        self._idle: asyncio.Event | None = None  # set = no batch currently in flight
        self._retrievals = 0
        self.paused_for_retrieval = False

    # -- setup ------------------------------------------------------------
    def _ensure_primitives(self) -> None:
        if self._gate is None:
            self._gate = asyncio.Event()
            self._gate.set()
            self._idle = asyncio.Event()
            self._idle.set()

    # -- public API -------------------------------------------------------
    def stage(self, doc: StagedDocument) -> None:
        self._docs[doc.id] = doc

    def get(self, document_id: str) -> StagedDocument | None:
        return self._docs.get(document_id)

    def enqueue(self, document_id: str, *, start: bool = True) -> None:
        if document_id not in self._queue:
            self._queue.append(document_id)
        if start:
            self.ensure_started()

    def ensure_started(self) -> None:
        """Idempotently starts the background worker (also the "KB came up empty" trigger)."""
        self._ensure_primitives()
        if not self._queue and not self._pending_ids():
            return
        for doc_id in self._pending_ids():
            if doc_id not in self._queue:
                self._queue.append(doc_id)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="ingestion-worker")

    def _pending_ids(self) -> list[str]:
        return [d.id for d in self._docs.values() if d.status in {"queued", "indexing"}]

    def unindexed_documents(self, document_ids: list[str] | None = None) -> list[StagedDocument]:
        docs = [d for d in self._docs.values() if d.status in {"queued", "indexing"}]
        if document_ids:
            wanted = set(document_ids)
            docs = [d for d in docs if d.id in wanted]
        return docs

    def search_staged(
        self, query: str, top_k: int = 5, document_ids: list[str] | None = None
    ) -> list[tuple[StagedDocument, str, float]]:
        hits: list[tuple[StagedDocument, str, float]] = []
        for doc in self.unindexed_documents(document_ids):
            hits.extend((doc, chunk, score) for chunk, score in doc.search(query, top_k))
        hits.sort(key=lambda h: h[2], reverse=True)
        return hits[:top_k]

    def snapshot(self) -> dict[str, Any]:
        active = [d for d in self._docs.values() if d.status in {"queued", "indexing"}]
        return {"active": len(active), "paused": self.paused_for_retrieval and bool(active), "queued": len(self._queue)}

    @asynccontextmanager
    async def retrieval(self) -> AsyncIterator[None]:
        """Pauses ingestion for the duration of a knowledge-base lookup, then lets it resume."""
        self._ensure_primitives()
        assert self._gate is not None and self._idle is not None
        self._retrievals += 1
        self._gate.clear()
        if self._pending_ids():
            self.paused_for_retrieval = True
        try:
            await self._idle.wait()  # let the in-flight batch (if any) finish
            yield
        finally:
            self._retrievals -= 1
            if self._retrievals == 0:
                self.paused_for_retrieval = False
                self._gate.set()

    # -- worker -----------------------------------------------------------
    async def _run(self) -> None:
        while self._queue:
            document_id = self._queue.pop(0)
            doc = self._docs.get(document_id)
            if doc is None or doc.status not in {"queued", "indexing"}:
                continue
            try:
                await self._ingest(doc)
            except Exception as exc:
                logger.exception("Ingestion failed for %s", doc.title)
                doc.status, doc.error = "failed", str(exc)
                await self._persist_status(doc)

    async def _ingest(self, doc: StagedDocument) -> None:
        from app.rag import vector_store
        from app.rag.bm25 import BM25Document, get_bm25_index
        from app.rag.chunker import chunk_text
        from app.rag.classification import classify_document, get_known_categories
        from app.rag.embeddings import embed_texts

        doc.status = "indexing"
        await self._persist_status(doc)

        try:
            known = await get_known_categories()
            doc.category = await asyncio.wait_for(classify_document(doc.text, known), CLASSIFY_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001 - classification is a nicety, never a blocker
            doc.category = "general"

        if not doc.chunks:
            doc.chunks = chunk_text(doc.text)
        metadata = {"title": doc.title, "source": doc.source, "document_id": doc.id, "category": doc.category}
        bm25_docs: list[BM25Document] = []

        # Idempotent restart: clear anything a previous, interrupted attempt already wrote.
        await self._run_step(vector_store.delete_by_document, doc.id)
        doc.indexed_chunks = 0

        for start in range(0, len(doc.chunks), self._batch_size):
            batch = doc.chunks[start : start + self._batch_size]

            def index_batch(batch: list[str] = batch) -> list[BM25Document]:
                vectors = embed_texts(batch)
                ids = vector_store.upsert_chunks(batch, vectors, [metadata] * len(batch))
                return [BM25Document(id=i, text=c, metadata=metadata) for i, c in zip(ids, batch)]

            bm25_docs.extend(await self._run_step(index_batch))
            doc.indexed_chunks = min(len(doc.chunks), start + len(batch))

        def finalize() -> None:
            index = get_bm25_index()
            index.add(bm25_docs)
            index.save()

        await self._run_step(finalize)
        doc.status = "completed"
        await self._persist_status(doc, category=doc.category)
        logger.info("Ingested %s (%d chunks, category=%s)", doc.title, len(doc.chunks), doc.category)
        # Now fully in Qdrant + BM25: drop the heavy in-memory staged copy but keep the status row.
        doc.text, doc._bm25, doc._chunk_tokens = "", None, []

    async def _run_step(self, func, *args):
        """Runs one blocking unit of work in a thread, but only while the gate is open."""
        assert self._gate is not None and self._idle is not None
        while True:
            await self._gate.wait()
            if self._gate.is_set():  # re-check: a retrieval may have closed it while we were waking up
                break
        self._idle.clear()
        try:
            return await asyncio.to_thread(func, *args)
        finally:
            self._idle.set()

    async def _persist_status(self, doc: StagedDocument, **extra: Any) -> None:
        try:
            from app.db.crud import get_document_by_id, update_document
            from app.db.session import get_session_maker

            async with get_session_maker()() as session:
                row = await get_document_by_id(session, doc.id)
                if row is None:
                    return
                metadata = dict(row.doc_metadata or {})
                metadata.update({"status": doc.status, **extra})
                await update_document(session, doc.id, doc_metadata=metadata)
        except Exception:
            logger.warning("Could not persist ingestion status for %s", doc.id, exc_info=True)

    # -- recovery ---------------------------------------------------------
    async def recover_interrupted(self) -> int:
        """Re-queues documents left in queued/indexing state by a previous server run."""
        from app.db.crud import list_documents
        from app.db.session import get_session_maker
        from app.rag.loader import load_document

        recovered = 0
        async with get_session_maker()() as session:
            rows = await list_documents(session, limit=500)
        for row in rows:
            status = (row.doc_metadata or {}).get("status")
            if status not in {"queued", "processing", "indexing"} or row.id in self._docs:
                continue
            path = Path(row.source)
            if not path.exists():
                continue
            try:
                loaded = await asyncio.to_thread(load_document, path)
            except Exception:  # noqa: BLE001
                continue
            self.stage(StagedDocument(id=row.id, title=row.title, source=row.source, text=loaded.text))
            self.enqueue(row.id, start=False)
            recovered += 1
        if recovered:
            self.ensure_started()
            logger.info("Recovered %d interrupted document upload(s)", recovered)
        return recovered


_manager: IngestionManager | None = None


def get_ingestion_manager() -> IngestionManager:
    global _manager
    if _manager is None:
        _manager = IngestionManager()
    return _manager
