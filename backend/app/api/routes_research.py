"""POST /api/research - runs the full multi-agent research workflow.
GET /api/research/stream - the same workflow, streamed over SSE so the
frontend can show live progress (planning, researching, critic verdict, ...)
instead of waiting on one long request.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.logging import get_logger
from app.core.schemas import ResearchMetrics, ResearchRequest, ResearchResponse
from app.db.crud import insert_trace
from app.db.session import get_session_maker
from app.llm.client import LLMUnavailableError, get_llm_client
from app.graph.research_graph import run_research, run_research_stream

router = APIRouter(prefix="/api", tags=["research"])
logger = get_logger(__name__)


async def _persist_trace(query: str, result: dict[str, Any]) -> None:
    try:
        session_maker = get_session_maker()
        async with session_maker() as session:
            await insert_trace(
                session,
                query=query,
                trace={"report": result["report"], "sources": result["sources"]},
                latency_ms=result["metrics"]["latency_ms"],
                status=result["status"],
            )
    except Exception:
        logger.warning("Failed to persist execution trace (Postgres unavailable?)", exc_info=True)


@router.post("/research", response_model=ResearchResponse)
async def research(request: ResearchRequest) -> ResearchResponse:
    result = await run_research(
        request.query,
        document_ids=request.document_ids,
        mode=request.mode,
        report_depth=request.report_depth,
    )

    response = ResearchResponse(
        status=result["status"],
        report=result["report"],
        sources=result["sources"],
        metrics=ResearchMetrics(**result["metrics"]),
        error=result.get("error"),
        docx_job_id=result.get("docx_job_id"),
        run_id=result.get("run_id"),
    )

    await _persist_trace(request.query, result)
    return response


@router.get("/research/stream")
async def research_stream(
    query: str = Query(..., min_length=3),
    document_ids: str = Query("", description="Comma-separated ids of uploaded documents to ground the research in"),
    mode: Literal["fast", "agentic"] | None = Query(None),
    report_depth: Literal["none", "overview", "standard", "comprehensive"] = Query("none"),
) -> StreamingResponse:
    ids = [i for i in document_ids.split(",") if i]

    async def event_generator():
        try:
            await get_llm_client().ensure_available()  # fail in ~1s with a clear reason, not after the planner stalls
        except LLMUnavailableError as exc:
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
            return
        async for event in run_research_stream(query, document_ids=ids, mode=mode, report_depth=report_depth):
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
            if event["event"] == "done":
                await _persist_trace(query, event["data"])

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
