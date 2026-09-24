"""Coding agent: answers coding questions, and when the model is unsure (or unavailable) it searches the
web, reads the best pages, answers from them and *remembers* the result (``app.learning.store``).

Flow: recall a learned answer -> draft with the LLM (self-rated confidence) -> if low confidence / failed:
web search + read pages (code blocks preserved) -> answer grounded in the pages -> learn it.
If the LLM is completely unreachable the web findings themselves are returned.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.logging import get_logger
from app.learning import store
from app.llm.client import get_llm_client
from app.tools import search

logger = get_logger(__name__)

MAX_PAGES = 3
PAGE_CHARS = 3200
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CodingAgent/1.0)", "Accept": "text/html,text/plain"}

DRAFT_SYSTEM = """You are an expert software engineer helping with coding: writing, fixing, explaining and reviewing code.
Reply in Markdown with complete, working, well-commented code in fenced blocks (with the language tag) and a short explanation.
Never invent APIs, function names or library versions. If you are not sure something exists or works, say so.
The very FIRST line of your reply must be exactly one of:
CONFIDENCE: high
CONFIDENCE: low
Use low if the task needs up-to-date/library-specific knowledge you are not certain about, or you may be guessing."""

WEB_SYSTEM = """You are an expert software engineer. Answer the user's coding request using the WEB REFERENCE material below
(official docs, Stack Overflow, GitHub etc.). Prefer what the references show over your own memory; adapt it to the request.
Reply in Markdown: complete working code in fenced blocks with the language tag, then a short explanation.
Do not mention that you were given references; the sources are listed separately."""


@dataclass
class CodingResult:
    reply: str
    used_web: bool = False
    from_memory: bool = False
    learned: bool = False
    llm_available: bool = True
    sources: list[dict[str, str]] = field(default_factory=list)


_PRE_RE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_ENTITIES = {"&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " ", "&amp;": "&"}


def _unescape(text: str) -> str:
    for key, value in _ENTITIES.items():
        text = text.replace(key, value)
    return text


async def _read_page(url: str) -> str:
    """Readable text plus <pre> code blocks of a page ('' on failure)."""
    try:
        async with httpx.AsyncClient(timeout=7, follow_redirects=True, headers=_HEADERS) as client:
            resp = await client.get(url)
        content_type = resp.headers.get("content-type", "")
        if resp.status_code != 200 or ("html" not in content_type and "text" not in content_type):
            return ""
        html = resp.text[:500_000]
    except Exception:  # noqa: BLE001
        return ""
    blocks = [_unescape(_TAG_RE.sub("", b)).strip() for b in _PRE_RE.findall(html)]
    code = "\n\n".join(f"```\n{b[:900]}\n```" for b in blocks if 20 <= len(b) <= 4000)[:2000]
    body = re.sub(r"<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    body = _PRE_RE.sub(" ", body)
    lines = (re.sub(r"\s+", " ", x).strip() for x in re.split(r"[\r\n]+", _unescape(_TAG_RE.sub("\n", body))))
    prose = "\n".join(ln for ln in lines if len(ln) >= 60)
    return (prose[: PAGE_CHARS - len(code)] + "\n" + code).strip()


async def _web_research(question: str) -> tuple[str, list[dict[str, str]]]:
    found = await search.run(query=f"{question} code example", max_results=5)
    results = [r for r in found.get("results", []) if r.get("url")]
    pages = await asyncio.gather(*(_read_page(r["url"]) for r in results[:MAX_PAGES]))
    parts = [
        f"### {r.get('title', '')}\nURL: {r['url']}\n{page or r.get('snippet', '')}"
        for r, page in zip(results, pages)
    ]
    sources = [{"title": r.get("title") or r["url"], "url": r["url"]} for r in results[:5]]
    return "\n\n".join(parts), sources


def _messages(system: str, history: list[dict[str, str]], user: str) -> list[dict[str, Any]]:
    return [{"role": "system", "content": system}, *history[-6:], {"role": "user", "content": user}]


def _split_confidence(text: str) -> tuple[bool, str]:
    m = re.match(r"\s*CONFIDENCE:\s*(high|low)\s*\n?", text, re.IGNORECASE)
    if not m:
        return True, text.strip()
    return m.group(1).lower() == "high", text[m.end():].strip()


def _sources_md(sources: list[dict[str, str]]) -> str:
    if not sources:
        return ""
    return "\n\n**Sources**\n" + "\n".join(f"- [{s['title']}]({s['url']})" for s in sources)


async def run(message: str, history: list[dict[str, str]] | None = None) -> CodingResult:
    history = history or []
    client = get_llm_client()

    remembered = await asyncio.to_thread(store.recall, message, ("coding",), 1, 0.75)
    if remembered:
        entry = remembered[0]
        return CodingResult(
            reply=entry["content"] + _sources_md(entry.get("sources", [])),
            from_memory=True,
            sources=entry.get("sources", []),
        )

    learned_ctx = await asyncio.to_thread(store.recall, message, None, 2, 0.4)
    ctx = "\n\n".join(f"[Previously learned] {e['topic']}\n{e['content'][:1200]}" for e in learned_ctx)
    prompt = message if not ctx else f"{message}\n\n---\nUseful notes learned earlier:\n{ctx}"

    draft, confident, llm_ok = "", False, True
    try:
        result = await client.chat(messages=_messages(DRAFT_SYSTEM, history, prompt), temperature=0.2)
        confident, draft = _split_confidence(result.content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Coding agent draft failed (%s); falling back to the web", exc)
        llm_ok = False

    if llm_ok and confident and draft:
        return CodingResult(reply=draft)

    web_text, sources = await _web_research(message)
    if not web_text:
        if draft:
            return CodingResult(reply=draft + "\n\n> Could not verify this on the web - please test the code.")
        raise RuntimeError("The model is unavailable and the web search returned nothing.")

    if not llm_ok:
        return CodingResult(
            reply="The language model is unavailable right now, so here is what I found on the web:\n\n"
            + web_text[:6000]
            + _sources_md(sources),
            used_web=True,
            llm_available=False,
            sources=sources,
        )

    try:
        final = await client.chat(
            messages=_messages(WEB_SYSTEM + f"\n\nWEB REFERENCE:\n{web_text}", history, message), temperature=0.2
        )
        answer = final.content.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Coding agent web answer failed: %s", exc)
        return CodingResult(reply=(draft or web_text[:5000]) + _sources_md(sources), used_web=True, sources=sources)

    learned = await asyncio.to_thread(store.learn, "coding", message, answer, sources)
    return CodingResult(reply=answer + _sources_md(sources), used_web=True, learned=learned, sources=sources)
