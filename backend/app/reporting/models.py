"""Plain data structures shared by the report writer and the DOCX builder."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class TableData:
    title: str
    columns: list[str]
    rows: list[list[str]]
    col_widths: list[float] | None = None  # relative widths, normalised by the builder
    note: str | None = None


@dataclass
class ChartData:
    kind: Literal["bar", "hbar", "pie", "line", "heatmap"]
    title: str
    labels: list[str] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    x_label: str = ""
    y_label: str = ""
    unit: str = ""
    note: str | None = None  # e.g. "Source: [3]" or "Analyst assessment"
    points: list[tuple[str, int, int]] = field(default_factory=list)  # heatmap: (risk id, likelihood, impact)


@dataclass
class Block:
    kind: Literal["h2", "h3", "p", "bullets", "numbered", "table", "chart", "callout"]
    text: str = ""
    items: list[str] = field(default_factory=list)
    table: TableData | None = None
    chart: ChartData | None = None
    label: str = ""  # callout heading, e.g. "Key takeaway"


@dataclass
class Chapter:
    title: str
    blocks: list[Block] = field(default_factory=list)
    appendix: bool = False


@dataclass
class SourceRef:
    number: int
    title: str
    url: str | None
    origin: str
    excerpt: str = ""


@dataclass
class ReportDoc:
    title: str
    subtitle: str
    query: str
    date: str
    chapters: list[Chapter] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
