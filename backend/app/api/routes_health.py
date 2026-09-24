"""GET /health - checks connectivity to the remote LLM (and, best-effort, Qdrant/Postgres)."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.logging import get_logger
from app.core.schemas import HealthResponse
from app.llm.client import get_llm_client

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    llm_ok = await get_llm_client().health_check()

    qdrant_status = _check_qdrant()
    postgres_status = None  # kept lightweight; DB health is checked at ingest/query time

    overall = "ok" if llm_ok else "degraded"
    return HealthResponse(
        status=overall,
        llm="connected" if llm_ok else "unreachable",
        qdrant=qdrant_status,
        postgres=postgres_status,
    )


def _check_qdrant() -> str:
    try:
        from app.rag.vector_store import get_client

        get_client().get_collections()
        return "connected"
    except Exception:
        logger.debug("Qdrant health check failed", exc_info=True)
        return "unreachable"
