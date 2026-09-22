"""Shared chunk -> embed -> Qdrant-upsert logic.

Used by both scripts/ingest.py (batch directory ingestion, full BM25
rebuild at the end) and app/api/routes_documents.py (single-file upload
from the frontend, incremental BM25 update per file) so the two paths
never duplicate the actual indexing logic.
"""
from __future__ import annotations

from app.rag import vector_store
from app.rag.bm25 import BM25Document
from app.rag.chunker import chunk_text
from app.rag.embeddings import embed_texts


def chunk_and_index(
    text: str, *, title: str, source: str, document_id: str, category: str = "general"
) -> list[BM25Document]:
    chunks = chunk_text(text)
    if not chunks:
        return []

    vectors = embed_texts(chunks)
    metadata = {"title": title, "source": source, "document_id": document_id, "category": category}
    point_ids = vector_store.upsert_chunks(chunks, vectors, [metadata] * len(chunks))
    return [BM25Document(id=point_id, text=chunk, metadata=metadata) for point_id, chunk in zip(point_ids, chunks)]
