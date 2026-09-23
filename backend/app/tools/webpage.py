"""Fetches the readable text of a web page (used to deepen report chapters beyond search snippets)."""
from __future__ import annotations

import re
from html.parser import HTMLParser

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg"}
_BLOCK_TAGS = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr", "section", "article"}
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ResearchAgent/1.0)", "Accept": "text/html,text/plain"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self._parts.append(data.strip() + " ")

    def text(self) -> str:
        raw = "".join(self._parts)
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw.splitlines()]
        # Drop menu-like fragments; keep lines that read like sentences.
        return "\n".join(ln for ln in lines if len(ln) >= 40)


async def fetch_page_text(url: str, max_chars: int = 3500, timeout: float = 6.0) -> str:
    """Best-effort: returns "" on any failure (paywall, bot-block, non-HTML, timeout)."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=_HEADERS) as client:
            response = await client.get(url)
        content_type = response.headers.get("content-type", "")
        if response.status_code != 200 or "html" not in content_type and "text" not in content_type:
            return ""
        extractor = _TextExtractor()
        extractor.feed(response.text[:400_000])
        return extractor.text()[:max_chars]
    except Exception:
        logger.debug("fetch_page_text failed for %s", url, exc_info=True)
        return ""
