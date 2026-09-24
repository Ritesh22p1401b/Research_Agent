"""POST /api/evaluate - runs the evaluation dataset (section 11 / 16)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.logging import get_logger
from app.core.schemas import EvaluateResponse
from app.evaluation.runner import run_evaluation
from app.llm.client import get_llm_client

router = APIRouter(prefix="/api", tags=["evaluation"])
logger = get_logger(__name__)


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(limit: int | None = Query(default=None, ge=1, le=100)) -> EvaluateResponse:
    try:
        await get_llm_client().ensure_available()
        outcome = await run_evaluation(limit)
    except Exception as exc:
        logger.exception("Evaluation run failed")
        return EvaluateResponse(status="failed", error=str(exc))

    return EvaluateResponse(
        status=outcome["status"],
        total_questions=outcome["total_questions"],
        summary=outcome["summary"],
        results=outcome["results"],
    )
