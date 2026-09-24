"""GET /api/reports/{job_id} - DOCX generation progress; GET /api/reports/{job_id}/download - the file."""
from __future__ import annotations

import asyncio
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.core.schemas import ReportJob
from app.reporting.jobs import get_job, get_job_file
from app.reporting.quick_export import build_quick_docx

router = APIRouter(prefix="/api/reports", tags=["reports"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ExportRequest(BaseModel):
    query: str = ""
    report: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] | None = None


@router.post("/export")
async def export_report(body: ExportRequest) -> Response:
    """Instant .docx of a finished research result. No LLM/KB calls, so background indexing is untouched."""
    data = await asyncio.to_thread(build_quick_docx, body.query, body.report, body.sources, body.metrics)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", body.query).strip("_")[:50] or "research"
    return Response(
        content=data,
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{slug}_report.docx"'},
    )


@router.get("/{job_id}", response_model=ReportJob)
async def report_status(job_id: str) -> ReportJob:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown report job")
    return job


@router.get("/{job_id}/download")
async def download_report(job_id: str) -> FileResponse:
    found = get_job_file(job_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Report is not ready (or does not exist)")
    path, filename = found
    return FileResponse(path, media_type=DOCX_MEDIA_TYPE, filename=filename)
