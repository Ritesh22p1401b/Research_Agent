"""FastAPI application entry point.

Run locally with:
    uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes_chat, routes_documents, routes_evaluate, routes_health, routes_research
from app.core.config import get_settings
from app.core.guardrails import GuardrailError
from app.core.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting Agentic Research Intelligence Platform (env=%s)", settings.app_env)
    logger.info("LLM endpoint: %s (model=%s)", settings.llm_base_url, settings.llm_model)
    yield


app = FastAPI(
    title="Agentic Research Intelligence Platform",
    description="Multi-agent RAG + MCP + remote Qwen3 inference research assistant.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router)
app.include_router(routes_chat.router)
app.include_router(routes_research.router)
app.include_router(routes_evaluate.router)
app.include_router(routes_documents.router)


@app.exception_handler(GuardrailError)
async def guardrail_error_handler(request: Request, exc: GuardrailError) -> JSONResponse:
    logger.warning("Guardrail triggered on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=429, content={"error": str(exc)})
