"""CLI: create database tables from the SQLAlchemy models (dev convenience,
in place of a full Alembic migration history for this interview-scale project).

Usage:
    python scripts/create_tables.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import get_logger  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import get_engine  # noqa: E402

logger = get_logger(__name__)


async def create_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created (documents, execution_traces, evaluation_runs).")


if __name__ == "__main__":
    asyncio.run(create_tables())
