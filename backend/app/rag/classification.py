"""LLM-based topic classification, used only for single-file uploads.

Batch-ingested documents (scripts/ingest.py) get their category for free
from folder structure (see app/rag/loader.py). Uploads via the frontend's
"+" button have no such structure, so we ask the LLM to classify them
instead - one call per upload, not per batch document.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.crud import list_distinct_categories
from app.db.session import get_session_maker
from app.llm.client import get_llm_client

logger = get_logger(__name__)

CLASSIFY_PROMPT = """You are classifying a document into a topic category for a RAG knowledge base.

Known existing categories: {categories}

Read the document excerpt below. If it clearly fits one of the known categories, use that exact
category name. Otherwise, propose a new short category label (lowercase, snake_case, 1-2 words).

Document excerpt:
{excerpt}

Respond with a JSON object ONLY: {{"category": "..."}}"""

EXCERPT_CHARS = 2000


async def get_known_categories() -> list[str]:
    session_maker = get_session_maker()
    async with session_maker() as session:
        return await list_distinct_categories(session)


async def classify_document(text: str, known_categories: list[str]) -> str:
    prompt = CLASSIFY_PROMPT.format(
        categories=", ".join(known_categories) if known_categories else "(none yet)",
        excerpt=text[:EXCERPT_CHARS],
    )
    try:
        parsed, _ = await get_llm_client().chat_json(messages=[{"role": "user", "content": prompt}])
        category = str(parsed.get("category", "")).strip().lower().replace(" ", "_")
        return category or "general"
    except Exception:
        logger.warning("Document classification failed, defaulting to 'general'", exc_info=True)
        return "general"
