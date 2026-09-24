"""Persistent "learned from the web" memory shared by the coding agent and the research agents.

Whenever an agent had to go to the web to answer something, what it found is saved here (JSON file,
lexical retrieval, deduplicated, capped). Later questions are checked against this memory *before*
the model or the web, so the platform gets more capable the more it is used.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

STORE_PATH = Path("data/learned/knowledge.json")
MAX_ENTRIES = 600
_TOKEN_RE = re.compile(r"[a-z0-9_#+.]{2,}")
_STOP = {"the", "and", "for", "with", "how", "what", "why", "can", "you", "use", "using", "this", "that", "from", "are", "write", "make", "create"}
_lock = threading.Lock()


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP}


def _load() -> list[dict[str, Any]]:
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        logger.warning("Learned-knowledge store unreadable; starting empty", exc_info=True)
        return []


def _save(entries: list[dict[str, Any]]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STORE_PATH)


def learn(kind: str, topic: str, content: str, sources: list[dict[str, str]] | None = None) -> bool:
    """Stores one learned item. Returns False if it was empty or too short to be useful."""
    topic, content = topic.strip(), content.strip()
    if not topic or len(content) < 40:
        return False
    key = " ".join(sorted(_tokens(topic)))[:200] + "|" + kind
    with _lock:
        entries = _load()
        for existing in entries:
            if existing.get("key") == key:
                existing.update(content=content[:6000], sources=sources or [], updated=time.time())
                _save(entries)
                return True
        entries.append(
            {"key": key, "kind": kind, "topic": topic, "content": content[:6000], "sources": sources or [], "updated": time.time()}
        )
        _save(entries[-MAX_ENTRIES:])
    return True


def recall(query: str, kinds: tuple[str, ...] | None = None, limit: int = 3, min_overlap: float = 0.5) -> list[dict[str, Any]]:
    """Best matches by token overlap with the question (topic weighted double)."""
    q = _tokens(query)
    if not q:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in _load():
        if kinds and entry.get("kind") not in kinds:
            continue
        topic_hits = len(q & _tokens(entry["topic"]))
        body_hits = len(q & _tokens(entry["content"][:1500]))
        score = (2 * topic_hits + body_hits) / (len(q) * 3)
        if score >= min_overlap:
            scored.append((score, entry))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [e for _, e in scored[:limit]]


def stats() -> dict[str, int]:
    entries = _load()
    return {
        "total": len(entries),
        "coding": sum(e.get("kind") == "coding" for e in entries),
        "web": sum(e.get("kind") == "web" for e in entries),
    }
