"""CLI: load documents from data/documents/, chunk, embed, upsert to Qdrant,
build the BM25 index, and record metadata rows in Postgres.

Usage:
    python scripts/ingest.py [--dir data/documents]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import get_logger  # noqa: E402
from app.db.crud import insert_document  # noqa: E402
from app.db.session import get_session_maker  # noqa: E402
from app.rag.bm25 import BM25Document, BM25Index  # noqa: E402
from app.rag.ingestion import chunk_and_index  # noqa: E402
from app.rag.loader import load_documents_from_dir  # noqa: E402

logger = get_logger(__name__)


async def ingest(directory: Path) -> None:
    documents = load_documents_from_dir(directory)
    if not documents:
        logger.warning("No supported documents found in %s", directory)
        return

    session_maker = get_session_maker()
    bm25_docs: list[BM25Document] = []

    for doc in documents:
        category = doc.category or "general"
        logger.info("Ingesting %s (category=%s)", doc.source, category)
        async with session_maker() as session:
            db_doc = await insert_document(
                session, title=doc.title, source=doc.source, content=doc.text, metadata={"category": category}
            )

        bm25_docs.extend(
            chunk_and_index(doc.text, title=doc.title, source=doc.source, document_id=db_doc.id, category=category)
        )

    index = BM25Index()
    index.build(bm25_docs)
    index.save()
    logger.info("Ingested %d documents, %d chunks. BM25 index saved.", len(documents), len(bm25_docs))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="data/documents", help="Directory containing documents to ingest")
    args = parser.parse_args()
    asyncio.run(ingest(Path(args.dir)))
