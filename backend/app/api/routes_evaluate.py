"""POST /api/evaluate - runs the evaluation dataset (section 11 / 16)."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.logging import get_logger
from app.core.schemas import EvaluateResponse
from app.evaluation.runner import run_evaluation

router = APIRouter(prefix="/api", tags=["evaluation"])
logger = get_logger(__name__)


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate() -> EvaluateResponse:
    try:
        outcome = await run_evaluation()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Evaluation run failed")
        return EvaluateResponse(status="failed", error=str(exc))

    return EvaluateResponse(
        status=outcome["status"],
        total_questions=outcome["total_questions"],
        summary=outcome["summary"],
        results=outcome["results"],
    )
