"""POST /api/documents - queue documents for background ingestion into the RAG pipeline.

Validation and saving the file to disk happen synchronously (fast, so the
request returns immediately) - parsing, LLM topic classification, chunking,
embedding, the Qdrant upsert and the BM25 index update all happen in a
FastAPI BackgroundTask *after* the response is sent. Uploading a document
never blocks the user; the knowledge base just grows behind the scenes.

Accepts pdf, docx, markdown, csv, json and html files (see
app/rag/loader.py SUPPORTED_EXTENSIONS). Each upload is saved under
data/documents/ (same convention as scripts/ingest.py's batch flow).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, UploadFile
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.logging import get_logger
from app.core.schemas import DocumentSummary, QueuedUpload, UploadDocumentsResponse
from app.db.crud import insert_document, list_documents, update_document
from app.db.session import get_session_maker
from app.rag.bm25 import get_bm25_index
from app.rag.classification import classify_document, get_known_categories
from app.rag.ingestion import chunk_and_index
from app.rag.loader import SUPPORTED_EXTENSIONS, load_document

router = APIRouter(prefix="/api", tags=["documents"])
logger = get_logger(__name__)

DOCUMENTS_DIR = Path("data") / "documents"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB per file


@router.post("/documents", response_model=UploadDocumentsResponse)
async def upload_documents(
    background_tasks: BackgroundTasks, files: list[UploadFile] = File(...)
) -> UploadDocumentsResponse:
    session_maker = get_session_maker()
    queued: list[QueuedUpload] = []
    errors: list[str] = []

    for file in files:
        try:
            stored_path, document_id, filename = await _accept_upload(file, session_maker)
            background_tasks.add_task(_process_upload, stored_path, document_id)
            queued.append(QueuedUpload(document_id=document_id, filename=filename))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to accept upload %r: %s", file.filename, exc)
            errors.append(f"{file.filename}: {exc}")

    return UploadDocumentsResponse(queued=queued, errors=errors)


@router.get("/documents", response_model=list[DocumentSummary])
async def list_uploaded_documents() -> list[DocumentSummary]:
    session_maker = get_session_maker()
    async with session_maker() as session:
        docs = await list_documents(session, limit=100)
    return [
        DocumentSummary(
            id=d.id,
            title=d.title,
            source=d.source,
            category=d.doc_metadata.get("category"),
            status=d.doc_metadata.get("status", "completed"),
        )
        for d in docs
    ]


async def _accept_upload(file: UploadFile, session_maker: async_sessionmaker) -> tuple[Path, str, str]:
    """Fast synchronous part: validate, save to disk, create a placeholder DB row."""
    original_name = Path(file.filename or "upload").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"unsupported file type '{suffix}' (allowed: {sorted(SUPPORTED_EXTENSIONS)})")

    content = await file.read()
    if not content:
        raise ValueError("file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB upload limit")

    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = DOCUMENTS_DIR / f"{uuid.uuid4().hex[:8]}_{original_name}"
    stored_path.write_bytes(content)

    async with session_maker() as session:
        placeholder = await insert_document(
            session, title=original_name, source=str(stored_path), content="", metadata={"status": "processing"}
        )

    return stored_path, placeholder.id, original_name


async def _process_upload(stored_path: Path, document_id: str) -> None:
    """Background task: parse -> classify -> chunk -> embed -> index. Runs after the HTTP response is sent."""
    session_maker = get_session_maker()
    try:
        loaded = load_document(stored_path)
        known_categories = await get_known_categories()
        category = await classify_document(loaded.text, known_categories)

        async with session_maker() as session:
            await update_document(
                session,
                document_id,
                title=loaded.title,
                content=loaded.text,
                doc_metadata={"category": category, "status": "completed"},
            )

        bm25_docs = chunk_and_index(
            loaded.text, title=loaded.title, source=loaded.source, document_id=document_id, category=category
        )
        get_bm25_index().add(bm25_docs)
        get_bm25_index().save()
        logger.info(
            "Background ingestion completed: %s (category=%s, chunks=%d)", stored_path, category, len(bm25_docs)
        )
    except Exception:  # noqa: BLE001
        logger.exception("Background ingestion failed for %s", stored_path)
        async with session_maker() as session:
            await update_document(session, document_id, doc_metadata={"status": "failed"})
