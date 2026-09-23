"""GET /api/reports/{job_id} - DOCX generation progress; GET /api/reports/{job_id}/download - the file."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.schemas import ReportJob
from app.reporting.jobs import get_job, get_job_file

router = APIRouter(prefix="/api/reports", tags=["reports"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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
