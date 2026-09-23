"""Background DOCX report jobs: start, track progress, locate the finished file.

A job is started automatically when a research run finishes (see
``app.graph.research_graph._maybe_start_docx``) and runs independently of the
HTTP request that triggered it, so closing the tab never loses the report.
Job state lives in memory; the finished ``.docx`` is written to
``settings.reports_dir`` and stays downloadable after a server restart.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.schemas import ReportJob

logger = get_logger(__name__)

_jobs: dict[str, ReportJob] = {}
_paths: dict[str, Path] = {}
_tasks: set[asyncio.Task] = set()

_STATE_KEYS = ("query", "sub_questions", "evidence", "analysis", "critic", "report", "document_ids")


def _reports_dir() -> Path:
    path = Path(get_settings().reports_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def start_report_job(query: str, final_state: dict[str, Any], sources: list[dict], depth: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = ReportJob(job_id=job_id, status="queued", stage="queued", message="Queued")
    snapshot = {key: final_state.get(key) for key in _STATE_KEYS}
    task = asyncio.create_task(_run(job_id, query, snapshot, depth), name=f"docx-{job_id}")
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job_id


def get_job(job_id: str) -> ReportJob | None:
    job = _jobs.get(job_id)
    if job is not None:
        return job
    path = _reports_dir() / f"{job_id}.docx"
    if path.exists():  # generated before a server restart
        _paths[job_id] = path
        return ReportJob(job_id=job_id, status="completed", stage="done", message="Report ready", percent=100, filename=path.name)
    return None


def get_job_file(job_id: str) -> tuple[Path, str] | None:
    job = get_job(job_id)
    if job is None or job.status != "completed":
        return None
    path = _paths.get(job_id) or _reports_dir() / f"{job_id}.docx"
    return (path, job.filename or path.name) if path.exists() else None


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:60] or "Report"


async def _run(job_id: str, query: str, state: dict[str, Any], depth: str) -> None:
    from app.graph.research_graph import _document_titles
    from app.reporting.docx_builder import build_docx, estimate_pages
    from app.reporting.writer import build_report

    job = _jobs[job_id]

    def progress(stage: str, message: str, percent: int, **extra: Any) -> None:
        job.status, job.stage, job.message = "running", stage, message
        job.percent = max(job.percent, min(percent, 99))
        if "sections_done" in extra:
            job.sections_done = extra["sections_done"]
        if "sections_total" in extra:
            job.sections_total = extra["sections_total"]

    try:
        progress("starting", "Preparing the report", 1)
        titles = await _document_titles(state.get("document_ids") or [])
        document = await build_report(query, state, depth, progress, document_titles=titles)
        progress("rendering", "Rendering charts and formatting the document", 96)
        path = _reports_dir() / f"{job_id}.docx"
        await asyncio.to_thread(build_docx, document, path)
        _paths[job_id] = path
        job.pages_estimate = estimate_pages(document)
        job.filename = f"{_slug(document.title)}.docx"
        job.status, job.stage, job.percent, job.message = "completed", "done", 100, "Report ready"
        logger.info("DOCX report %s generated (~%d pages, %s)", job_id, job.pages_estimate, path)
    except Exception as exc:
        logger.exception("DOCX report job %s failed", job_id)
        job.status, job.stage, job.error = "failed", "failed", str(exc) or exc.__class__.__name__
        job.message = "Report generation failed"
