"""Central application settings, loaded from environment variables / .env.

Every other module reads configuration from here rather than calling
``os.getenv`` directly, so the whole app stays configurable without code
changes (see agentic-research-intelligence-platform.md, section 8: "the
agent code should not need to change when the model changes").
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_env: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    cors_origins: str = "http://localhost:3000"

    # --- LLM ---
    # NOTE: this points at a custom transformers-based FastAPI wrapper
    # (GET /health, POST /generate), NOT an OpenAI-compatible /v1 API - no
    # /v1 suffix here. See app/llm/client.py's module docstring for the
    # emulation layer this requires (flattened prompts, text-based tool
    # calling). llm_supports_reasoning is currently unused: this server
    # hardcodes enable_thinking=False and exposes no toggle for it.
    llm_base_url: str = "http://localhost:8000"
    llm_api_key: str = "EMPTY"
    llm_model: str = "Qwen/Qwen3-8B"
    llm_timeout_seconds: float = 240.0
    # Max simultaneous /generate calls from this backend. The Colab wrapper is a
    # sync FastAPI handler (threadpool), so a few concurrent calls overlap on the GPU.
    llm_max_concurrency: int = 2
    llm_max_retries: int = 2
    llm_temperature: float = 0.3
    llm_max_tokens: int = 2048
    llm_top_p: float = 0.8
    llm_supports_reasoning: bool = True
    llm_supports_tool_calling: bool = True

    # --- Embeddings ---
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_device: str = "cpu"
    reranker_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "research_documents"

    # --- Postgres ---
    postgres_dsn: str = "postgresql+asyncpg://research_user:research_pass@localhost:5432/research_platform"
    postgres_readonly_dsn: str = (
        "postgresql+asyncpg://research_readonly:research_readonly_pass@localhost:5432/research_platform"
    )

    # --- Web search ---
    web_search_provider: str = "duckduckgo"
    tavily_api_key: str | None = None
    serper_api_key: str | None = None

    # --- Observability ---
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_enabled: bool = False

    # --- Guardrails ---
    # Bumped from 12/10 to accommodate query decomposition: the planner can
    # fan a broad question out into up to 4 sub-questions, each running its
    # own bounded research pass, before analysis/critic/report even start.
    max_agent_steps: int = 20
    max_research_retries: int = 1
    max_tool_calls: int = 18
    max_search_results: int = 5
    tool_timeout_seconds: float = 15.0
    db_query_row_limit: int = 200
    db_query_timeout_seconds: float = 5.0
    db_table_allowlist: str = "documents,execution_traces,evaluation_runs"

    # --- Research speed ---
    # "fast": planner -> parallel retrieval (KB + web + uploaded docs, no LLM ReAct loops)
    #         -> one analysis call -> critic -> report (4-5 LLM calls total).
    # "agentic": the original ReAct loops per sub-question (slowest, most flexible).
    research_mode: str = "fast"
    planner_max_tokens: int = 300
    analysis_max_tokens: int = 1400
    critic_max_tokens: int = 500
    report_max_tokens: int = 1800

    # --- Document ingestion (uploads) ---
    ingest_batch_size: int = 16  # chunks embedded+upserted per step; pause/resume happens between steps
    ingest_autostart_on_upload: bool = True
    max_upload_mb: int = 50

    # --- DOCX report generation ---
    docx_max_pages: int = 100
    docx_section_concurrency: int = 2
    docx_fetch_pages: bool = True  # fetch full text of top web results for deeper chapters
    reports_dir: str = "data/reports"

    # --- MCP ---
    mcp_tool_allowlist: str = "web_search,search_knowledge_base,database_query,get_document"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def db_table_allowlist_set(self) -> set[str]:
        return {t.strip().lower() for t in self.db_table_allowlist.split(",") if t.strip()}

    @property
    def mcp_tool_allowlist_set(self) -> set[str]:
        return {t.strip() for t in self.mcp_tool_allowlist.split(",") if t.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
