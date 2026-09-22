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
    llm_base_url: str = "http://localhost:8000/v1"
    llm_api_key: str = "EMPTY"
    llm_model: str = "Qwen/Qwen3-8B"
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 2
    llm_temperature: float = 0.3
    llm_max_tokens: int = 2048
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
    max_agent_steps: int = 12
    max_research_retries: int = 2
    max_tool_calls: int = 10
    max_search_results: int = 5
    tool_timeout_seconds: float = 15.0
    db_query_row_limit: int = 200
    db_query_timeout_seconds: float = 5.0
    db_table_allowlist: str = "documents,execution_traces,evaluation_runs"

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
