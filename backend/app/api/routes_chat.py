"""POST /api/chat - a direct passthrough chat completion (Phase 1 deliverable, section 20)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.logging import get_logger
from app.core.schemas import ChatRequest, ChatResponse, ChatUsage
from app.llm.client import get_llm_client

router = APIRouter(prefix="/api", tags=["chat"])
logger = get_logger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    messages = [{"role": m.role, "content": m.content} for m in request.history]
    messages.append({"role": "user", "content": request.message})

    try:
        result = await get_llm_client().chat(messages=messages)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Chat completion failed")
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc

    return ChatResponse(
        reply=result.content,
        usage=ChatUsage(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            total_tokens=result.usage.total_tokens,
            latency_ms=result.latency_ms,
        ),
    )
