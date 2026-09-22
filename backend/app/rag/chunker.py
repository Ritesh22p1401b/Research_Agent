"""Structure-aware chunking with overlap.

Splits on paragraph/heading boundaries first, then falls back to a
character-level sliding window so no chunk exceeds ``chunk_size``.
"""
from __future__ import annotations

import re

PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    paragraphs = [p.strip() for p in PARAGRAPH_SPLIT_RE.split(text) if p.strip()]
    chunks: list[str] = []
    buffer = ""

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_char_window(paragraph, chunk_size, overlap))
            continue

        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) <= chunk_size:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer)
            buffer = paragraph

    if buffer:
        chunks.append(buffer)

    return chunks


def _char_window(text: str, chunk_size: int, overlap: int) -> list[str]:
    step = chunk_size - overlap
    return [text[i : i + chunk_size] for i in range(0, len(text), step) if text[i : i + chunk_size].strip()]
