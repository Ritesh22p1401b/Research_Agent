"""Basic CRUD helpers used by ingestion, tools and evaluation."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, EvaluationRun, ExecutionTrace


async def insert_document(session: AsyncSession, *, title: str, source: str, content: str, metadata: dict[str, Any] | None = None) -> Document:
    doc = Document(title=title, source=source, content=content, doc_metadata=metadata or {})
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def get_document_by_id(session: AsyncSession, document_id: str) -> Document | None:
    result = await session.execute(select(Document).where(Document.id == document_id))
    return result.scalar_one_or_none()


async def update_document(session: AsyncSession, document_id: str, **fields: Any) -> None:
    """Used by background ingestion to fill in a placeholder row once processing finishes."""
    doc = await get_document_by_id(session, document_id)
    if doc is None:
        return
    for key, value in fields.items():
        setattr(doc, key, value)
    await session.commit()


async def list_documents(session: AsyncSession, limit: int = 50, ids: list[str] | None = None) -> list[Document]:
    """Newest first, so recent uploads are never hidden behind a large ingested corpus; ``ids`` narrows to specific rows."""
    query = select(Document).order_by(Document.created_at.desc()).limit(limit)
    if ids:
        query = query.where(Document.id.in_(ids))
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_distinct_categories(session: AsyncSession) -> list[str]:
    category = Document.doc_metadata["category"].as_string()
    result = await session.execute(select(category).distinct().where(category.isnot(None)))
    return sorted({row for row in result.scalars().all() if row})


async def insert_trace(session: AsyncSession, *, query: str, trace: dict[str, Any], latency_ms: float, status: str) -> ExecutionTrace:
    record = ExecutionTrace(query=query, trace=trace, latency_ms=latency_ms, status=status)
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def insert_evaluation_run(session: AsyncSession, *, summary: dict[str, Any], results: dict[str, Any]) -> EvaluationRun:
    record = EvaluationRun(summary=summary, results=results)
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record
