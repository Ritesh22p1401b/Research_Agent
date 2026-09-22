"""POST /api/research - runs the full multi-agent research workflow."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.logging import get_logger
from app.core.schemas import ResearchMetrics, ResearchRequest, ResearchResponse
from app.db.crud import insert_trace
from app.db.session import get_session_maker
from app.graph.research_graph import run_research

router = APIRouter(prefix="/api", tags=["research"])
logger = get_logger(__name__)


@router.post("/research", response_model=ResearchResponse)
async def research(request: ResearchRequest) -> ResearchResponse:
    result = await run_research(request.query)

    response = ResearchResponse(
        status=result["status"],
        report=result["report"],
        sources=result["sources"],
        metrics=ResearchMetrics(**result["metrics"]),
        error=result.get("error"),
    )

    try:
        session_maker = get_session_maker()
        async with session_maker() as session:
            await insert_trace(
                session,
                query=request.query,
                trace={"report": result["report"], "sources": result["sources"]},
                latency_ms=result["metrics"]["latency_ms"],
                status=result["status"],
            )
    except Exception:  # noqa: BLE001
        logger.warning("Failed to persist execution trace (Postgres unavailable?)", exc_info=True)

    return response
