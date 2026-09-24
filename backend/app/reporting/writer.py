"""Builds the content of a long-form business research report from a finished research run.

Pipeline (each step degrades gracefully - a failed LLM call never aborts the report):

1. Outline     - one LLM call designs chapters/sections and per-chapter search queries.
2. Deep dive   - per chapter, KB + web + uploaded-document retrieval and full-page fetches (no LLM).
3. Writing     - one LLM call per section produces grounded prose, a takeaway and (optionally) a table/chart.
                 Every figure in a chart must literally appear in the evidence shown to the model.
4. Synthesis   - risk register (+ heat map), recommendations and conclusion; executive summary,
                 methodology, competitor chart and source appendices are assembled deterministically.
5. Page cap    - the document is trimmed if the estimate would exceed ``docx_max_pages``.
"""
from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlparse

from app.agents.evidence import gather_for_query
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.client import get_llm_client
from app.rag.ingestion_manager import _tokens as tokenize
from app.reporting.docx_builder import estimate_pages
from app.reporting.models import (
    Block,
    Chapter,
    ChartData,
    ReportDoc,
    SourceRef,
    TableData,
)
from app.tools.webpage import fetch_page_text

logger = get_logger(__name__)

Progress = Callable[..., None]

DEPTHS: dict[str, dict[str, int]] = {
    "standard": {"chapters": 6, "sections": 3, "words": 380, "evidence": 7, "fetch": 2},
    "comprehensive": {"chapters": 10, "sections": 4, "words": 560, "evidence": 9, "fetch": 3},
    # overview: a tight 5-6 page briefing
    "overview": {"chapters": 3, "sections": 2, "words": 230, "evidence": 5, "fetch": 1},
}
# Hard page caps per size (comprehensive uses settings.docx_max_pages = 100). Sizes: overview 5-6, standard 15-20,
# comprehensive 50-100 pages.
PAGE_CAPS: dict[str, int] = {"overview": 6, "standard": 20}
MIN_BODY_SECTIONS = 3  # the page cap trims sections from the end but always keeps at least this many
RESERVED_CHAPTER = re.compile(r"executive summary|recommendation|methodolog|conclusion|source|reference|appendix|risk", re.IGNORECASE)
CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


# --------------------------------------------------------------------------- evidence pool
class EvidencePool:
    """De-duplicated, numbered evidence shared by every chapter (the numbers become [n] citations)."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self._index: dict[str, int] = {}

    def add(self, *, title: str, url: str | None, origin: str, text: str, chapter: int | None = None) -> int:
        text = (text or "").strip()
        key = (url or "").strip() or f"{title.strip().lower()}|{text[:80].lower()}"
        found = self._index.get(key)
        if found is None:
            found = len(self.items) + 1
            self._index[key] = found
            self.items.append(
                {"id": found, "title": title or "Untitled source", "url": url or None, "origin": origin, "text": text, "chapters": set()}
            )
        else:
            item = self.items[found - 1]
            if len(text) > len(item["text"]) and text[:60] != item["text"][:60]:
                item["text"] += "\n" + text  # different passage from the same source
        if chapter is not None:
            self.items[found - 1]["chapters"].add(chapter)
        return found

    def get(self, evidence_id: int) -> dict[str, Any]:
        return self.items[evidence_id - 1]


def _best_window(text: str, tokens: set[str], size: int) -> str:
    if len(text) <= size:
        return text
    best, best_score = text[:size], -1
    for start in range(0, len(text) - size // 2, max(size // 2, 1)):
        window = text[start : start + size]
        score = len(tokens.intersection(tokenize(window)))
        if score > best_score:
            best, best_score = window, score
    return best


def _select_evidence(pool: EvidencePool, chapter_idx: int, query_text: str, limit: int) -> list[dict[str, Any]]:
    tokens = set(tokenize(query_text))
    scored = []
    for item in pool.items:
        overlap = len(tokens.intersection(tokenize(item["text"][:1500] + " " + item["title"])))
        bonus = 3 if chapter_idx in item["chapters"] else 0
        scored.append((overlap + bonus, item))
    scored.sort(key=lambda p: p[0], reverse=True)
    return [item for score, item in scored[:limit] if score > 0] or [item for _, item in scored[:limit]]


# --------------------------------------------------------------------------- LLM helpers
async def _chat_text(prompt: str, max_tokens: int, temperature: float = 0.35) -> str:
    result = await get_llm_client().chat(messages=[{"role": "user", "content": prompt}], temperature=temperature, max_tokens=max_tokens)
    return result.content


async def _chat_json(prompt: str, max_tokens: int) -> dict[str, Any]:
    parsed, _ = await get_llm_client().chat_json(messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=max_tokens)
    return parsed if isinstance(parsed, dict) else {}


# --------------------------------------------------------------------------- outline
OUTLINE_PROMPT = """You are the lead editor of a professional business research report.

Research question: {query}
Report depth: {depth}

What the research team already found:
{findings}

Sub-questions investigated:
{sub_questions}
{documents}
Design the report outline. Rules:
- {chapters} chapters at most, ordered logically: context and background first, then deep-dive topics, then implications.
- Do NOT create chapters for: executive summary, risks, recommendations, methodology, conclusion or sources - those are generated separately.
- Each chapter has 2 to {sections} sections. A section heading is specific and informative (not "Overview" alone).
- For each chapter give 2 web-search queries that would find in-depth material for it.
- Set "table": true on sections best presented with a comparison or summary table; set "chart": true only on sections likely to contain numeric data (market size, growth, share, revenue, counts, rankings).

Respond with a JSON object ONLY:
{{"title": "report title", "subtitle": "one line", "chapters": [{{"title": "...", "search_queries": ["...", "..."], "sections": [{{"heading": "...", "focus": "one sentence on what this section must cover", "table": false, "chart": false}}]}}]}}"""


def _fallback_outline(query: str, analysis: dict, cfg: dict[str, int]) -> dict[str, Any]:
    chapters = [
        ("Background and Market Context", ["Landscape overview", "Key drivers and trends"]),
        ("Key Findings in Depth", ["Principal findings", "Supporting evidence"]),
        ("Competitive Landscape", ["Major players", "Positioning and differentiation"]),
        ("Opportunities and Growth Levers", ["Growth opportunities", "Enablers and prerequisites"]),
    ]
    if not analysis.get("competitors"):
        chapters.pop(2)
    return {
        "title": query.strip().rstrip("?").capitalize()[:110],
        "subtitle": "Comprehensive research analysis",
        "chapters": [
            {
                "title": title,
                "search_queries": [f"{query} {title}"],
                "sections": [{"heading": h, "focus": f"{h} in the context of: {query}", "table": False, "chart": False} for h in sections],
            }
            for title, sections in chapters[: cfg["chapters"]]
        ],
    }


def _sanitize_outline(raw: dict[str, Any], query: str, analysis: dict, cfg: dict[str, int]) -> dict[str, Any]:
    chapters = []
    for chapter in raw.get("chapters") or []:
        title = str(chapter.get("title", "")).strip()
        if not title or RESERVED_CHAPTER.search(title):
            continue
        sections = []
        for section in (chapter.get("sections") or [])[: cfg["sections"]]:
            heading = str(section.get("heading", "")).strip()
            if heading:
                sections.append(
                    {
                        "heading": heading[:120],
                        "focus": str(section.get("focus", heading))[:300],
                        "table": bool(section.get("table")),
                        "chart": bool(section.get("chart")),
                    }
                )
        if sections:
            queries = [str(q).strip() for q in (chapter.get("search_queries") or []) if str(q).strip()][:2]
            chapters.append({"title": title[:110], "search_queries": queries or [f"{query} {title}"], "sections": sections})
        if len(chapters) >= cfg["chapters"]:
            break
    if not chapters:
        return _fallback_outline(query, analysis, cfg)
    return {
        "title": str(raw.get("title") or query)[:140],
        "subtitle": str(raw.get("subtitle") or "Comprehensive research analysis")[:200],
        "chapters": chapters,
    }


# --------------------------------------------------------------------------- section writing
SECTION_PROMPT = """You are a senior business research analyst writing one section of a formal report.

Report topic: {query}
Chapter: {chapter}
Section: {heading}
What this section must cover: {focus}
Other sections in this chapter (do not repeat them): {siblings}

Evidence (numbered - cite as [n]):
{evidence}

Writing rules:
- About {words} words of polished, specific, professional prose. Plain paragraphs separated by blank lines; a short bullet list (lines starting with "- ") is fine where it aids clarity. No headings, no markdown symbols other than **bold** for key terms.
- Every factual claim, figure or date must come from the evidence above and carry a citation like [3] or [2, 5]. If the evidence does not support something, do not state it - say the available data is limited instead. Never invent numbers, names or dates.
- Compare and interpret the evidence (implications, trade-offs), do not just list it.

Reply in EXACTLY this format:
### TEXT
(the section prose)
### TAKEAWAY
(one sentence: the single most important insight of this section)
{table_spec}{chart_spec}"""

TABLE_SPEC = """### TABLE
A JSON object {"title": "...", "columns": ["...", "..."], "rows": [["...", "..."]]} with 2-6 columns and 3-8 short-cell rows summarising facts FROM THE EVIDENCE (add a "Source" column with [n] citations). If the evidence cannot support a table, write {}.
"""
CHART_SPEC = """### CHART
A JSON object {"type": "bar" | "hbar" | "pie" | "line", "title": "...", "labels": ["...", "..."], "values": [1, 2], "unit": "%" or "USD bn" etc., "x_label": "", "y_label": ""} using ONLY numbers that appear verbatim in the evidence (at least 3 comparable values; pie needs 2+ parts of a whole). If the evidence has no such numbers, write {}.
"""


@dataclass
class SectionResult:
    heading: str
    blocks: list[Block] = field(default_factory=list)
    takeaway: str = ""
    evidence_ids: set[int] = field(default_factory=set)
    used_fallback: bool = False


def _split_markers(raw: str) -> dict[str, str]:
    parts = re.split(r"^\s*###\s*(TEXT|TAKEAWAY|TABLE|CHART)\s*:?\s*$", raw, flags=re.MULTILINE | re.IGNORECASE)
    if len(parts) < 3:
        return {"TEXT": raw.strip()}
    return {parts[i].upper(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def _filter_citations(text: str, allowed: set[int]) -> str:
    def repl(match: re.Match) -> str:
        kept = [n for n in (int(x) for x in re.split(r"\s*,\s*", match.group(1))) if n in allowed]
        return f"[{', '.join(str(n) for n in kept)}]" if kept else ""

    return re.sub(r"\s{2,}", " ", CITATION_RE.sub(repl, text))


def _prose_to_blocks(text: str) -> list[Block]:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    bullet_re, number_re = re.compile(r"^([-*•])\s+"), re.compile(r"^\d+[.)]\s+")
    blocks: list[Block] = []
    for chunk in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in chunk.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        i = 0
        lead: list[str] = []
        while i < len(lines) and not (bullet_re.match(lines[i]) or number_re.match(lines[i])):
            lead.append(lines[i])
            i += 1
        if lead:
            blocks.append(Block("p", text=" ".join(lead)))
        rest = lines[i:]
        if not rest:
            continue
        if all(number_re.match(ln) for ln in rest):
            blocks.append(Block("numbered", items=[number_re.sub("", ln) for ln in rest]))
        else:
            blocks.append(Block("bullets", items=[bullet_re.sub("", number_re.sub("", ln)) for ln in rest]))
    return blocks


def _parse_json_obj(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        value = json.loads(text[start : end + 1])
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _parse_table(text: str, fallback_title: str, allowed: set[int]) -> TableData | None:
    data = _parse_json_obj(text)
    columns = [str(c).strip() for c in (data.get("columns") or [])][:6]
    rows_raw = data.get("rows") or []
    if len(columns) < 2 or not isinstance(rows_raw, list) or len(rows_raw) < 2:
        return None
    rows = []
    for row in rows_raw[:10]:
        if not isinstance(row, list):
            continue
        cells = [_filter_citations(str(c).strip(), allowed)[:240] for c in row[: len(columns)]]
        cells += [""] * (len(columns) - len(cells))
        if any(cells):
            rows.append(cells)
    if len(rows) < 2:
        return None
    return TableData(title=str(data.get("title") or fallback_title)[:140], columns=columns, rows=rows)


def _to_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d[\d,]*\.?\d*", str(value))
    return float(match.group(0).replace(",", "")) if match else None


def _grounded(values: list[float], corpus: str) -> bool:
    """A chart is only kept if (nearly) every plotted number literally appears in the evidence text."""
    normalized = re.sub(r"(?<=\d),(?=\d{3})", "", corpus)
    hits = 0
    for value in values:
        forms = {f"{value:g}", f"{value:.1f}", f"{value:.2f}"}
        if float(value).is_integer():
            forms.add(str(int(value)))
        if any(re.search(rf"(?<![\d.]){re.escape(f)}(?!\d)", normalized) for f in forms):
            hits += 1
    return hits >= max(2, int(0.75 * len(values) + 0.5))


def _parse_chart(text: str, fallback_title: str, corpus: str, allowed: set[int]) -> ChartData | None:
    data = _parse_json_obj(text)
    kind = str(data.get("type", "")).lower()
    labels = [str(x).strip() for x in (data.get("labels") or [])]
    values = [_to_number(v) for v in (data.get("values") or [])]
    if kind not in {"bar", "hbar", "pie", "line"} or len(labels) != len(values) or any(v is None for v in values):
        return None
    numbers = [float(v) for v in values if v is not None]
    if len(numbers) < (2 if kind == "pie" else 3) or len(numbers) > 12:
        return None
    if kind == "pie" and any(v < 0 for v in numbers):
        return None
    if not _grounded(numbers, corpus):
        logger.info("Dropped ungrounded chart %r", data.get("title"))
        return None
    return ChartData(
        kind=kind,  # type: ignore[arg-type]
        title=str(data.get("title") or fallback_title)[:140],
        labels=labels,
        values=numbers,
        unit=str(data.get("unit", ""))[:20],
        x_label=str(data.get("x_label", ""))[:60],
        y_label=str(data.get("y_label", ""))[:60],
        note="Figures as reported in the cited sources",
    )


async def _write_section(
    *,
    query: str,
    chapter_idx: int,
    chapter: dict[str, Any],
    section: dict[str, Any],
    pool: EvidencePool,
    cfg: dict[str, int],
    semaphore: asyncio.Semaphore,
) -> SectionResult:
    heading = section["heading"]
    focus_text = f"{chapter['title']} {heading} {section['focus']}"
    picked = _select_evidence(pool, chapter_idx, focus_text, cfg["evidence"])
    tokens = set(tokenize(focus_text))
    allowed = {item["id"] for item in picked}
    evidence_block = "\n".join(
        f"[{item['id']}] {item['title']}: {_best_window(item['text'], tokens, 850).replace(chr(10), ' ')}" for item in picked
    ) or "(no specific evidence found - keep the section short and state that data is limited)"
    corpus = "\n".join(item["text"] for item in picked)
    siblings = "; ".join(s["heading"] for s in chapter["sections"] if s["heading"] != heading) or "(none)"
    words = cfg["words"]
    max_tokens = int(words * 1.55) + 120 + (420 if section["table"] else 0) + (380 if section["chart"] else 0)

    prompt = SECTION_PROMPT.format(
        query=query,
        chapter=chapter["title"],
        heading=heading,
        focus=section["focus"],
        siblings=siblings,
        evidence=evidence_block,
        words=words,
        table_spec=TABLE_SPEC if section["table"] else "",
        chart_spec=CHART_SPEC if section["chart"] else "",
    )
    result = SectionResult(heading=heading, evidence_ids=set(allowed))
    try:
        async with semaphore:
            raw = await _chat_text(prompt, max_tokens=min(max_tokens, 2400))
        parts = _split_markers(raw)
        prose = _filter_citations(parts.get("TEXT", ""), allowed)
        result.blocks = _prose_to_blocks(prose)
        if sum(len(b.text.split()) + sum(len(i.split()) for i in b.items) for b in result.blocks) < 40:
            raise ValueError("section too short")
        result.takeaway = _filter_citations(parts.get("TAKEAWAY", ""), allowed).strip()
        if "TABLE" in parts:
            table = _parse_table(parts["TABLE"], heading, allowed)
            if table:
                result.blocks.append(Block("table", table=table))
        if "CHART" in parts:
            chart = _parse_chart(parts["CHART"], heading, corpus, allowed)
            if chart:
                result.blocks.append(Block("chart", chart=chart))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Section %r fell back to raw evidence: %s", heading, exc)
        result.used_fallback = True
        result.takeaway = ""
        bullets = [
            f"{item['title']}: {_best_window(item['text'], tokens, 320).replace(chr(10), ' ').strip()} [{item['id']}]"
            for item in picked[:5]
        ]
        result.blocks = [Block("p", text="The narrative for this section could not be generated automatically; the most relevant evidence gathered is listed below."), Block("bullets", items=bullets)] if bullets else []
    return result


# --------------------------------------------------------------------------- deep research
async def _research_chapter(
    query: str,
    chapter_idx: int,
    chapter: dict[str, Any],
    document_ids: list[str],
    pool: EvidencePool,
    cfg: dict[str, int],
    fetched: set[str],
    fetch_pages: bool,
) -> None:
    results = await asyncio.gather(
        *(gather_for_query(q, document_ids, tool_timeout=25.0) for q in chapter["search_queries"]), return_exceptions=True
    )
    to_fetch: list[tuple[int, str]] = []
    for items in results:
        if isinstance(items, BaseException):
            continue
        for item in items:
            evidence_id = pool.add(
                title=item["source_title"],
                url=item.get("source_url"),
                origin=item["origin"],
                text=item["content"],
                chapter=chapter_idx,
            )
            url = item.get("source_url")
            if fetch_pages and item["origin"] == "web" and url and url not in fetched:
                to_fetch.append((evidence_id, url))
    picked = []
    for evidence_id, url in to_fetch:
        if url not in fetched and len(picked) < cfg["fetch"]:
            fetched.add(url)
            picked.append((evidence_id, url))
    pages = await asyncio.gather(*(fetch_page_text(url) for _, url in picked), return_exceptions=True)
    for (evidence_id, _), page in zip(picked, pages):
        if isinstance(page, str) and len(page) > 200:
            item = pool.get(evidence_id)
            item["text"] = (item["text"] + "\n" + page).strip()


# --------------------------------------------------------------------------- synthesis calls
RISK_PROMPT = """You are a risk analyst. Build a risk register for this research topic: {query}

Risks flagged during the research:
{risks}

Concerns raised by the verification agent:
{issues}

Evidence highlights:
{evidence}

Return a JSON object ONLY:
{{"risks": [{{"risk": "short title: one clarifying sentence", "category": "Market|Regulatory|Operational|Financial|Technology|Competitive|Reputational", "likelihood": 1-5, "impact": 1-5, "mitigation": "specific, actionable mitigation", "refs": [evidence numbers]}}]}}
Give 5 to 8 risks. Ratings (1 = lowest, 5 = highest) are your professional judgement of the evidence - be consistent and conservative."""

RECS_PROMPT = """You are a strategy consultant. Based on the research below, write recommendations and a conclusion for: {query}

Key findings:
{findings}

Opportunities:
{opportunities}

Risks:
{risks}

Return a JSON object ONLY:
{{"recommendations": [{{"action": "imperative, specific recommendation", "rationale": "why, tied to the findings (cite [n] if relevant)", "priority": "High|Medium|Low", "timeframe": "Immediate (0-3 months)|Near-term (3-12 months)|Long-term (12+ months)"}}], "conclusion": "one substantive paragraph (100-160 words) concluding the report"}}
Give 4 to 7 recommendations, most important first."""


def _bullets(items: list[Any], limit: int = 8) -> str:
    return "\n".join(f"- {str(i)[:300]}" for i in list(items)[:limit]) or "- (none)"


def _rating(score: int) -> str:
    return "Critical" if score >= 15 else "High" if score >= 10 else "Medium" if score >= 5 else "Low"


async def _risk_chapter(query: str, analysis: dict, report: dict, critic: dict, pool: EvidencePool) -> Chapter | None:
    highlights = "\n".join(f"[{i['id']}] {i['title']}: {i['text'][:220].replace(chr(10), ' ')}" for i in pool.items[:14])
    risks_in = list(analysis.get("risks", [])) + list(report.get("risks", []))
    prompt = RISK_PROMPT.format(query=query, risks=_bullets(risks_in, 10), issues=_bullets(critic.get("issues", [])), evidence=highlights)
    try:
        data = await _chat_json(prompt, max_tokens=1500)
    except Exception:
        logger.warning("Risk register generation failed", exc_info=True)
        data = {}
    risks = []
    for index, raw in enumerate(data.get("risks") or [], start=1):
        try:
            likelihood, impact = int(raw["likelihood"]), int(raw["impact"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (1 <= likelihood <= 5 and 1 <= impact <= 5):
            continue
        risks.append(
            {
                "id": f"R{len(risks) + 1}",
                "risk": str(raw.get("risk", "")).strip()[:300],
                "category": str(raw.get("category", "General")).strip()[:30],
                "likelihood": likelihood,
                "impact": impact,
                "mitigation": str(raw.get("mitigation", "")).strip()[:300],
            }
        )
        if len(risks) >= 8:
            break
    blocks: list[Block] = []
    if risks:
        risks.sort(key=lambda r: r["likelihood"] * r["impact"], reverse=True)
        for i, r in enumerate(risks, start=1):
            r["id"] = f"R{i}"
        blocks.append(
            Block(
                "p",
                text=(
                    f"This chapter consolidates {len(risks)} risks identified during the research and verification stages. "
                    "Each risk is scored as likelihood multiplied by impact on a 5-point scale. The ratings are an analyst "
                    "assessment of the evidence, not measured probabilities, and should be validated against internal data."
                ),
            )
        )
        blocks.append(
            Block(
                "chart",
                chart=ChartData(
                    kind="heatmap",
                    title="Risk matrix (likelihood x impact)",
                    points=[(r["id"], r["likelihood"], r["impact"]) for r in risks],
                    note="Analyst assessment",
                ),
            )
        )
        blocks.append(
            Block(
                "table",
                table=TableData(
                    title="Risk register",
                    columns=["ID", "Risk", "Category", "L", "I", "Score", "Rating", "Mitigation"],
                    rows=[
                        [r["id"], r["risk"], r["category"], str(r["likelihood"]), str(r["impact"]),
                         str(r["likelihood"] * r["impact"]), _rating(r["likelihood"] * r["impact"]), r["mitigation"]]
                        for r in risks
                    ],
                    col_widths=[0.6, 3.6, 1.4, 0.45, 0.45, 0.7, 1.0, 3.6],
                    note="L = likelihood, I = impact (1-5). Score = L x I. Rating: Critical >= 15, High >= 10, Medium >= 5, else Low.",
                ),
            )
        )
        top = risks[:3]
        blocks.append(
            Block("callout", label="Priority risks", text="; ".join(f"{r['id']} {r['risk'].split(':')[0]} ({_rating(r['likelihood'] * r['impact'])})" for r in top))
        )
    elif risks_in:
        blocks.append(Block("p", text="Risks flagged during the research (automatic scoring was unavailable, so they are listed without ratings):"))
        blocks.append(Block("bullets", items=[str(r)[:300] for r in risks_in[:10]]))
    else:
        return None
    return Chapter(title="Risk Assessment", blocks=blocks)


async def _recommendations_chapter(query: str, analysis: dict, report: dict, chapter_takeaways: list[str]) -> tuple[Chapter, str]:
    findings = list(report.get("key_findings", [])) or list(analysis.get("key_findings", []))
    prompt = RECS_PROMPT.format(
        query=query,
        findings=_bullets(findings + chapter_takeaways, 12),
        opportunities=_bullets(list(analysis.get("opportunities", [])) + list(report.get("opportunities", [])), 8),
        risks=_bullets(list(analysis.get("risks", [])) + list(report.get("risks", [])), 8),
    )
    try:
        data = await _chat_json(prompt, max_tokens=1600)
    except Exception:
        logger.warning("Recommendations generation failed", exc_info=True)
        data = {}
    recs = []
    for raw in data.get("recommendations") or []:
        action = str(raw.get("action", "")).strip()
        if action:
            recs.append(
                [
                    str(raw.get("priority", "Medium")).strip().title()[:8],
                    action[:300],
                    str(raw.get("rationale", "")).strip()[:360],
                    str(raw.get("timeframe", "")).strip()[:40],
                ]
            )
    if not recs:  # deterministic fallback from the analysis so the chapter is never empty
        for opp in (list(analysis.get("opportunities", [])) + list(report.get("opportunities", [])))[:5]:
            recs.append(["Medium", f"Pursue: {str(opp)[:240]}", "Identified as an opportunity in the research analysis.", "Near-term (3-12 months)"])
    order = {"High": 0, "Medium": 1, "Low": 2}
    recs.sort(key=lambda r: order.get(r[0], 1))
    conclusion = str(data.get("conclusion", "")).strip()
    blocks: list[Block] = []
    if recs:
        blocks.append(Block("h2", text="Recommendations"))
        blocks.append(
            Block(
                "table",
                table=TableData(
                    title="Prioritised recommendations",
                    columns=["Priority", "Recommendation", "Rationale", "Timeframe"],
                    rows=recs,
                    col_widths=[1.0, 4.2, 4.6, 2.0],
                ),
            )
        )
        high = [r[1] for r in recs if r[0] == "High"][:5]
        if high:
            blocks.append(Block("h2", text="Immediate next steps"))
            blocks.append(Block("numbered", items=high))
    if conclusion:
        blocks.append(Block("h2", text="Conclusion"))
        blocks.append(Block("p", text=conclusion))
    return Chapter(title="Strategic Recommendations and Conclusion", blocks=blocks), conclusion


# --------------------------------------------------------------------------- deterministic chapters
def _domain(url: str | None) -> str:
    return urlparse(url).netloc.removeprefix("www.") if url else ""


def _competitor_chart(analysis: dict, pool: EvidencePool) -> Block | None:
    names = [str(c).strip() for c in analysis.get("competitors", []) if str(c).strip()][:12]
    if len(names) < 3:
        return None
    corpus = [(i["title"] + " " + i["text"]).lower() for i in pool.items]
    counts = [(n, sum(1 for c in corpus if n.lower() in c)) for n in names]
    counts = sorted((p for p in counts if p[1] > 0), key=lambda p: p[1], reverse=True)
    if len(counts) < 3:
        return None
    return Block(
        "chart",
        chart=ChartData(
            kind="hbar",
            title="Competitor visibility: evidence items mentioning each company",
            labels=[n for n, _ in counts],
            values=[float(c) for _, c in counts],
            x_label="Evidence items",
            note=f"Counted across {len(pool.items)} collected sources",
        ),
    )


def _executive_summary(
    report: dict,
    analysis: dict,
    takeaways: list[tuple[str, str]],
    conclusion: str,
    id_by_index: list[int],
    critic: dict,
    compact: bool = False,
) -> Chapter:
    blocks: list[Block] = []
    summary = str(report.get("executive_summary", "")).strip()
    if summary:
        blocks.append(Block("p", text=summary))
    findings = list(report.get("key_findings", []))[: 5 if compact else 8] or list(analysis.get("key_findings", []))[: 5 if compact else 8]
    if findings:
        blocks.append(Block("h2", text="Key findings"))
        blocks.append(Block("bullets", items=[str(f) for f in findings]))
    if takeaways and not compact:
        blocks.append(Block("h2", text="Key takeaways by chapter"))
        blocks.append(Block("numbered", items=[f"**{title}.** {text}" for title, text in takeaways[:10]]))
    numbers = [n for n in (analysis.get("numbers") or []) if isinstance(n, dict) and n.get("claim") and n.get("value") is not None]
    if len(numbers) >= 2 and not compact:
        rows = []
        for n in numbers[:10]:
            idx = n.get("supporting_evidence_index")
            ref = f"[{id_by_index[idx]}]" if isinstance(idx, int) and 0 <= idx < len(id_by_index) else ""
            rows.append([str(n["claim"])[:200], str(n["value"])[:60], ref])
        blocks.append(Block("h2", text="Key figures"))
        blocks.append(Block("table", table=TableData(title="Key figures identified in the research", columns=["Claim", "Value", "Source"], rows=rows, col_widths=[6, 2, 1])))
    verification = "approved by the Critic Agent" if critic.get("approved") else "reviewed by the Critic Agent, which flagged open issues (see Methodology)"
    blocks.append(Block("callout", label="Confidence", text=f"The analysis behind this report was {verification}. Claims backed by only a single or weak source are hedged in the text."))
    if conclusion:
        blocks.append(Block("callout", label="Bottom line", text=conclusion.split(". ")[0].rstrip(".") + "."))
    return Chapter(title="Executive Summary", blocks=blocks)


def _methodology(
    sub_questions: list[str],
    pool: EvidencePool,
    critic: dict,
    chapter_names: list[str],
    fallback_sections: int,
    document_titles: list[str],
) -> Chapter:
    origin_counts = Counter(i["origin"] for i in pool.items)
    labels = {"web": "Web sources", "knowledge_base": "Knowledge base", "uploaded_document": "Uploaded documents"}
    blocks = [
        Block("h2", text="Research approach"),
        Block(
            "p",
            text=(
                "The research was carried out by a pipeline of specialised agents. A Planner decomposed the question into focused "
                "sub-questions; a Research stage retrieved evidence from the internal knowledge base, the public web"
                + (" and the documents supplied by the user" if document_titles else "")
                + "; an Analysis agent compared sources and extracted findings; a Critic agent verified claims against the evidence and flagged "
                "weakly supported statements; and a Report stage wrote each chapter using only numbered, citable evidence."
            ),
        ),
    ]
    if document_titles:
        blocks.append(Block("p", text="Documents supplied for this research: " + "; ".join(document_titles) + "."))
    if sub_questions:
        blocks.append(Block("h2", text="Research questions investigated"))
        blocks.append(Block("numbered", items=sub_questions))
    blocks.append(Block("h2", text="Evidence base"))
    blocks.append(
        Block(
            "p",
            text=f"The report draws on {len(pool.items)} distinct sources: "
            + ", ".join(f"{origin_counts[k]} {labels[k].lower()}" for k in labels if origin_counts.get(k))
            + ". Every numbered citation in the text refers to the source register in Appendix A.",
        )
    )
    if len(origin_counts) >= 2:
        blocks.append(
            Block(
                "chart",
                chart=ChartData(
                    kind="pie",
                    title="Evidence base by source type",
                    labels=[labels.get(k, k) for k in origin_counts],
                    values=[float(v) for v in origin_counts.values()],
                ),
            )
        )
    per_chapter = [(name, sum(1 for i in pool.items if idx in i["chapters"])) for idx, name in enumerate(chapter_names)]
    per_chapter = [p for p in per_chapter if p[1] > 0]
    if len(per_chapter) >= 3:
        blocks.append(
            Block(
                "chart",
                chart=ChartData(
                    kind="hbar",
                    title="Sources retrieved per report chapter",
                    labels=[n for n, _ in per_chapter],
                    values=[float(c) for _, c in per_chapter],
                    x_label="Sources",
                ),
            )
        )
    domains = Counter(_domain(i["url"]) for i in pool.items if i["url"])
    top = [(d, c) for d, c in domains.most_common(8) if d]
    if len(top) >= 3:
        blocks.append(
            Block(
                "chart",
                chart=ChartData(kind="hbar", title="Most frequently cited web domains", labels=[d for d, _ in top], values=[float(c) for _, c in top], x_label="Sources"),
            )
        )
    blocks.append(Block("h2", text="Verification and confidence"))
    issues = [str(i) for i in critic.get("issues", [])]
    low = [str(c) for c in critic.get("low_confidence_claims", [])]
    if critic.get("approved") and not issues:
        blocks.append(Block("p", text="The Critic Agent approved the analysis: important claims were found to be supported by at least one evidence item and no unresolved contradictions were flagged."))
    else:
        blocks.append(Block("p", text="The Critic Agent raised the following concerns about the analysis. Treat related statements with corresponding caution."))
        if issues:
            blocks.append(Block("bullets", items=issues[:8]))
    if low:
        blocks.append(Block("p", text="Claims supported only weakly (single source, dated or partially conflicting figures) and therefore hedged in the text:"))
        blocks.append(Block("bullets", items=low[:8]))
    blocks.append(Block("h2", text="Limitations"))
    limits = [
        "Web evidence is limited to what public search returned at the time of research; paywalled or very recent material may be missing.",
        "Narrative text is generated by a language model from the cited evidence. Figures in charts were checked against the source text, but all figures should be verified before use in decisions.",
        "Risk likelihood and impact ratings are analyst judgement, not statistical estimates.",
    ]
    if fallback_sections:
        limits.append(f"{fallback_sections} section(s) could not be drafted automatically and list the raw evidence instead.")
    blocks.append(Block("bullets", items=limits))
    return Chapter(title="Research Methodology and Evidence Base", blocks=blocks)


def _appendices(pool: EvidencePool, depth: str) -> list[Chapter]:
    type_names = {"web": "Web", "knowledge_base": "Knowledge base", "uploaded_document": "Uploaded document"}
    register = Chapter(
        title="Appendix A - Source Register",
        appendix=True,
        blocks=[
            Block("p", text="All sources cited in this report. Reference numbers correspond to the [n] citations in the text."),
            Block(
                "table",
                table=TableData(
                    title="Source register",
                    columns=["Ref", "Source", "Type", "Link"],
                    rows=[[str(i["id"]), i["title"][:140], type_names.get(i["origin"], i["origin"]), i["url"] or "-"] for i in pool.items],
                    col_widths=[0.6, 5, 1.6, 5],
                ),
            ),
        ],
    )
    if depth == "overview":  # keep the briefing to a compact source list
        register.blocks[1].table.rows = register.blocks[1].table.rows[:10]
        return [register]
    limit = 60 if depth == "standard" else 150
    excerpts = Chapter(
        title="Appendix B - Evidence Excerpts",
        appendix=True,
        blocks=[
            Block("p", text="Key passage retrieved from each source, for traceability."),
            Block(
                "table",
                table=TableData(
                    title="Evidence excerpts",
                    columns=["Ref", "Excerpt"],
                    rows=[[str(i["id"]), re.sub(r"\s+", " ", i["text"]).strip()[:340]] for i in pool.items[:limit]],
                    col_widths=[0.6, 11],
                ),
            ),
        ],
    )
    return [register, excerpts]


# --------------------------------------------------------------------------- page cap
def _fit_to_cap(doc: ReportDoc, cap: int) -> None:
    if estimate_pages(doc) <= cap:
        return
    doc.chapters = [c for c in doc.chapters if "Evidence Excerpts" not in c.title]
    guard = 0
    while estimate_pages(doc) > cap and guard < 500:
        guard += 1
        body = [c for c in doc.chapters if not c.appendix and c.title not in {"Executive Summary", "Research Methodology and Evidence Base"}]
        candidates = [c for c in body if any(b.kind == "h2" for b in c.blocks)]
        if not candidates or sum(1 for c in body for b in c.blocks if b.kind == "h2") <= MIN_BODY_SECTIONS:
            break
        chapter = candidates[-1]
        last_h2 = max(i for i, b in enumerate(chapter.blocks) if b.kind == "h2")
        if last_h2 == 0:
            doc.chapters.remove(chapter)
        else:
            del chapter.blocks[last_h2:]


# --------------------------------------------------------------------------- entry point
async def build_report(
    query: str,
    state: dict[str, Any],
    depth: str,
    progress: Progress,
    document_titles: list[str] | None = None,
) -> ReportDoc:
    settings = get_settings()
    cfg = DEPTHS.get(depth, DEPTHS["standard"])
    analysis: dict = state.get("analysis") or {}
    critic: dict = state.get("critic") or {}
    report: dict = state.get("report") or {}
    document_ids: list[str] = state.get("document_ids") or []
    sub_questions: list[str] = state.get("sub_questions") or []
    document_titles = document_titles or []

    pool = EvidencePool()
    id_by_index: list[int] = []
    for item in state.get("evidence") or []:
        id_by_index.append(pool.add(
            title=item.get("source_title") or "Untitled source",
            url=item.get("source_url"),
            origin=item.get("origin", "web"),
            text=item.get("content", ""),
        ))

    # 1. outline ---------------------------------------------------------------
    progress("outline", "Designing the report structure", 3)
    findings = _bullets(list(report.get("key_findings", [])) or list(analysis.get("key_findings", [])), 8)
    prompt = OUTLINE_PROMPT.format(
        query=query,
        depth=depth,
        findings=findings,
        sub_questions=_bullets(sub_questions, 6),
        documents=("\nUploaded documents that MUST be covered: " + "; ".join(document_titles) + "\n") if document_titles else "",
        chapters=cfg["chapters"],
        sections=cfg["sections"],
    )
    try:
        outline = _sanitize_outline(await _chat_json(prompt, max_tokens=1800), query, analysis, cfg)
    except Exception:
        logger.warning("Outline generation failed; using the fallback outline", exc_info=True)
        outline = _fallback_outline(query, analysis, cfg)
    chapters_spec = outline["chapters"]
    if depth == "overview":  # a 5-6 page briefing: no tables, a single chart
        for ci, chapter in enumerate(chapters_spec):
            for si, section in enumerate(chapter["sections"]):
                section["table"] = False
                section["chart"] = bool(ci == 0 and si == 0)
    total_sections = sum(len(c["sections"]) for c in chapters_spec)

    # 2. deep research per chapter ---------------------------------------------
    progress("research", "Researching each chapter in depth", 8, sections_total=total_sections)
    fetched: set[str] = set()
    gate = asyncio.Semaphore(2)

    async def research_one(idx: int, chapter: dict[str, Any]) -> None:
        async with gate:
            await _research_chapter(query, idx, chapter, document_ids, pool, cfg, fetched, settings.docx_fetch_pages)
        progress("research", f"Researched: {chapter['title']}", 8 + int(22 * (idx + 1) / len(chapters_spec)))

    await asyncio.gather(*(research_one(i, c) for i, c in enumerate(chapters_spec)), return_exceptions=True)

    # 3. write every section -----------------------------------------------------
    progress("writing", "Writing chapters", 30, sections_done=0, sections_total=total_sections)
    semaphore = asyncio.Semaphore(max(1, settings.docx_section_concurrency))
    done = 0

    async def write_one(idx: int, chapter: dict[str, Any], section: dict[str, Any]) -> SectionResult:
        nonlocal done
        result = await _write_section(query=query, chapter_idx=idx, chapter=chapter, section=section, pool=pool, cfg=cfg, semaphore=semaphore)
        done += 1
        progress("writing", f"Wrote: {section['heading']}", 30 + int(58 * done / max(total_sections, 1)), sections_done=done, sections_total=total_sections)
        return result

    jobs = [[write_one(i, c, s) for s in c["sections"]] for i, c in enumerate(chapters_spec)]
    flat = await asyncio.gather(*(job for chapter_jobs in jobs for job in chapter_jobs))
    results_iter = iter(flat)

    body_chapters: list[Chapter] = []
    takeaways: list[tuple[str, str]] = []
    fallback_sections = 0
    for chapter in chapters_spec:
        blocks: list[Block] = []
        chapter_takeaways: list[str] = []
        for section in chapter["sections"]:
            result = next(results_iter)
            fallback_sections += int(result.used_fallback)
            blocks.append(Block("h2", text=result.heading))
            blocks.extend(result.blocks)
            if result.takeaway:
                blocks.append(Block("callout", label="Key takeaway", text=result.takeaway))
                chapter_takeaways.append(result.takeaway)
        if re.search(r"compet|landscape|rival|market share", chapter["title"], re.IGNORECASE):
            chart = _competitor_chart(analysis, pool)
            if chart:
                blocks.append(chart)
        if chapter_takeaways:
            takeaways.append((chapter["title"], chapter_takeaways[0]))
        body_chapters.append(Chapter(title=chapter["title"], blocks=blocks))

    # 4. synthesis -----------------------------------------------------------------
    progress("synthesis", "Assessing risks and drafting recommendations", 90)
    risk_result, recs_result = await asyncio.gather(
        _risk_chapter(query, analysis, report, critic, pool),
        _recommendations_chapter(query, analysis, report, [t for _, t in takeaways]),
        return_exceptions=True,
    )
    risk_chapter = None if isinstance(risk_result, BaseException) else risk_result
    if isinstance(recs_result, BaseException):
        logger.warning("Recommendations chapter failed: %s", recs_result)
        recs_chapter, conclusion = None, ""
    else:
        recs_chapter, conclusion = recs_result

    progress("assembling", "Assembling the document", 94)
    origin_counts = Counter(i["origin"] for i in pool.items)
    doc = ReportDoc(
        title=outline["title"],
        subtitle=outline["subtitle"],
        query=query,
        date=date.today().strftime("%d %B %Y"),
        meta={
            "source_mix": ", ".join(
                f"{origin_counts[k]} {n}" for k, n in (("web", "web"), ("knowledge_base", "knowledge base"), ("uploaded_document", "uploaded")) if origin_counts.get(k)
            )
            or "web",
        },
    )
    compact = depth == "overview"
    doc.compact = compact
    doc.chapters = [_executive_summary(report, analysis, takeaways, conclusion, id_by_index, critic, compact), *body_chapters]
    if risk_chapter:
        if compact:  # briefing: register only (no heat map), top risks
            risk_chapter.blocks = [b for b in risk_chapter.blocks if b.kind != "chart"]
            for b in risk_chapter.blocks:
                if b.kind == "table" and b.table:
                    b.table.rows = b.table.rows[:4]
        doc.chapters.append(risk_chapter)
    if recs_chapter and recs_chapter.blocks:
        if compact:
            for b in recs_chapter.blocks:
                if b.kind == "table" and b.table:
                    b.table.rows = b.table.rows[:4]
        doc.chapters.append(recs_chapter)
    if not compact:
        doc.chapters.append(_methodology(sub_questions, pool, critic, [c["title"] for c in chapters_spec], fallback_sections, document_titles))
    doc.chapters.extend(_appendices(pool, depth))
    doc.sources = [SourceRef(i["id"], i["title"], i["url"], i["origin"], i["text"][:300]) for i in pool.items]

    _fit_to_cap(doc, min(settings.docx_max_pages, PAGE_CAPS.get(depth, settings.docx_max_pages)))
    return doc
