"""Async SQLAlchemy engine/session management for PostgreSQL."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_readonly_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None
_readonly_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().postgres_dsn, pool_pre_ping=True)
    return _engine


def get_readonly_engine() -> AsyncEngine:
    """Separate engine bound to a read-only DB role, used only by the database_query tool.

    Guardrail (see section 15 "Database safety"): the read/write app DSN must
    never be used to satisfy an LLM-driven query.
    """
    global _readonly_engine
    if _readonly_engine is None:
        _readonly_engine = create_async_engine(get_settings().postgres_readonly_dsn, pool_pre_ping=True)
    return _readonly_engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_maker


def get_readonly_session_maker() -> async_sessionmaker[AsyncSession]:
    global _readonly_session_maker
    if _readonly_session_maker is None:
        _readonly_session_maker = async_sessionmaker(get_readonly_engine(), expire_on_commit=False)
    return _readonly_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a read/write session."""
    async with get_session_maker()() as session:
        yield session
