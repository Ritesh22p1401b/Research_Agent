"""Document upload + ingestion status.

POST /api/documents validates and saves each file, parses it right away and
registers it with the ingestion manager (app/rag/ingestion_manager.py), then
returns. From that moment the document is already searchable by the research
agents (lexical search over its chunks); embedding + Qdrant/BM25 indexing runs
in the background and pauses whenever an agent needs the knowledge base.

Accepts pdf, docx, txt, markdown, csv, json and html files (see
app/rag/loader.py SUPPORTED_EXTENSIONS). Each upload is saved under
data/documents/ (same convention as scripts/ingest.py's batch flow).
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.schemas import (
    DocumentStatusResponse,
    DocumentSummary,
    IngestionSnapshot,
    QueuedUpload,
    UploadDocumentsResponse,
)
from app.db.crud import insert_document, list_documents
from app.db.session import get_session_maker
from app.rag.chunker import chunk_text
from app.rag.ingestion_manager import StagedDocument, get_ingestion_manager
from app.rag.loader import SUPPORTED_EXTENSIONS, load_document

router = APIRouter(prefix="/api", tags=["documents"])
logger = get_logger(__name__)

DOCUMENTS_DIR = Path("data") / "documents"


@router.post("/documents", response_model=UploadDocumentsResponse)
async def upload_documents(files: list[UploadFile] = File(...)) -> UploadDocumentsResponse:
    settings = get_settings()
    manager = get_ingestion_manager()
    queued: list[QueuedUpload] = []
    errors: list[str] = []

    for file in files:
        try:
            doc = await _accept_upload(file, settings.max_upload_mb * 1024 * 1024)
            manager.stage(doc)
            manager.enqueue(doc.id, start=settings.ingest_autostart_on_upload)
            queued.append(QueuedUpload(document_id=doc.id, filename=file.filename or doc.title))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to accept upload %r: %s", file.filename, exc)
            errors.append(f"{file.filename}: {exc}")

    return UploadDocumentsResponse(queued=queued, errors=errors)


@router.get("/documents", response_model=list[DocumentSummary])
async def list_uploaded_documents() -> list[DocumentSummary]:
    return await _summaries(limit=100)


@router.get("/documents/status", response_model=DocumentStatusResponse)
async def documents_status(
    ids: str = Query("", description="Comma-separated document ids (empty = all)"),
) -> DocumentStatusResponse:
    wanted = [i for i in ids.split(",") if i]
    docs = await _summaries(limit=200, ids=wanted or None)
    return DocumentStatusResponse(documents=docs, ingestion=IngestionSnapshot(**get_ingestion_manager().snapshot()))


async def _summaries(limit: int, ids: list[str] | None = None) -> list[DocumentSummary]:
    manager = get_ingestion_manager()
    async with get_session_maker()() as session:
        rows = await list_documents(session, limit=limit, ids=ids)

    summaries: list[DocumentSummary] = []
    for row in rows:
        meta = row.doc_metadata or {}
        status = meta.get("status", "completed")
        if status == "processing":  # legacy value from before the ingestion manager existed
            status = "indexing"
        progress = 100 if status == "completed" else 0
        chunk_count = None
        category = meta.get("category")
        live = manager.get(row.id)
        if live is not None:
            status, progress = live.status, live.progress
            chunk_count = len(live.chunks) or None
            if live.status != "queued":
                category = live.category
        summaries.append(
            DocumentSummary(
                id=row.id,
                title=row.title,
                source=row.source,
                category=category,
                status=status,
                progress=progress,
                chunk_count=chunk_count,
                paused=bool(live and live.status in {"queued", "indexing"} and manager.paused_for_retrieval),
            )
        )
    return summaries


async def _accept_upload(file: UploadFile, max_bytes: int) -> StagedDocument:
    """Validate, save to disk, parse, create the DB row and return the staged (searchable) document."""
    original_name = Path(file.filename or "upload").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"unsupported file type '{suffix}' (allowed: {sorted(SUPPORTED_EXTENSIONS)})")

    content = await file.read()
    if not content:
        raise ValueError("file is empty")
    if len(content) > max_bytes:
        raise ValueError(f"exceeds the {max_bytes // (1024 * 1024)}MB upload limit")

    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = DOCUMENTS_DIR / f"{uuid.uuid4().hex[:8]}_{original_name}"
    stored_path.write_bytes(content)

    try:
        loaded = await asyncio.to_thread(load_document, stored_path)
    except Exception as exc:
        stored_path.unlink(missing_ok=True)
        raise ValueError(f"could not read the file ({exc})") from exc
    if not loaded.text.strip():
        stored_path.unlink(missing_ok=True)
        raise ValueError("no extractable text found in the file")

    async with get_session_maker()() as session:
        row = await insert_document(
            session,
            title=original_name,
            source=str(stored_path),
            content=loaded.text,
            metadata={"status": "queued"},
        )

    return StagedDocument(
        id=row.id,
        title=original_name,
        source=str(stored_path),
        text=loaded.text,
        chunks=await asyncio.to_thread(chunk_text, loaded.text),
    )
