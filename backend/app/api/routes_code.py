"""POST /api/code - the coding agent (LLM first, web search + learning when the LLM is unsure)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents import coding_agent
from app.core.logging import get_logger
from app.core.schemas import ChatRequest
from app.learning import store

router = APIRouter(prefix="/api", tags=["code"])
logger = get_logger(__name__)


class CodeResponse(BaseModel):
    reply: str
    used_web: bool = False
    from_memory: bool = False
    learned: bool = False
    llm_available: bool = True


@router.post("/code", response_model=CodeResponse)
async def code(request: ChatRequest) -> CodeResponse:
    history = [{"role": m.role, "content": m.content} for m in request.history if m.role != "system"]
    try:
        result = await coding_agent.run(request.message, history)
    except Exception as exc:
        logger.exception("Coding agent failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CodeResponse(
        reply=result.reply,
        used_web=result.used_web,
        from_memory=result.from_memory,
        learned=result.learned,
        llm_available=result.llm_available,
    )


@router.get("/learned/stats")
async def learned_stats() -> dict[str, int]:
    return store.stats()
