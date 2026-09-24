"""Renders a ``ReportDoc`` into a professionally formatted, business-style .docx.

Layout rules that keep the document tight (no page waste, no gaps):
- only the cover page and the appendices start on a new page - chapters flow continuously
- headings are ``keep_with_next`` so a heading is never stranded at the bottom of a page
- table rows never split across pages and header rows repeat on every page
- figures are capped at ~3.3in tall and keep their caption on the same page
- one consistent type scale / spacing system (Calibri 10.5pt body, 6pt paragraph spacing)
"""
from __future__ import annotations

import io
import re
from collections.abc import Iterable
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.reporting.charts import render_chart
from app.reporting.models import Chapter, ChartData, ReportDoc, TableData

NAVY = "1F3864"
BLUE = "2E75B6"
LIGHT = "E8F0FA"
BAND = "F3F6FB"
GREY = "595959"
BODY_FONT = "Calibri"
PAGE_W_CM, PAGE_H_CM = 21.0, 29.7
MARGIN_LR_CM, MARGIN_TOP_CM, MARGIN_BOTTOM_CM = 2.2, 2.2, 2.0
TEXT_W_CM = PAGE_W_CM - 2 * MARGIN_LR_CM

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|\[\d+(?:\s*,\s*\d+)*\])")


def _clean(text: object) -> str:
    return _CONTROL_RE.sub("", str(text if text is not None else ""))


def _rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color)


# --------------------------------------------------------------------------- xml helpers
# Word is strict about child order inside these property elements, so every element we add by hand is
# inserted at its schema position instead of being appended.
_TBLPR_ORDER = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize", "tblStyleColBandSize", "tblW", "jc",
                "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption", "tblDescription"]
_TCPR_ORDER = ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap", "tcMar", "textDirection", "tcFitText",
               "vAlign", "hideMark"]
_TRPR_ORDER = ["cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore", "wAfter", "cantSplit", "trHeight", "tblHeader",
               "tblCellSpacing", "jc", "hidden"]
_PPR_AFTER_PBDR = ["shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE",
                   "autoSpaceDN", "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents",
                   "suppressOverlap", "jc", "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle",
                   "rPr", "sectPr", "pPrChange"]


def _put(parent, child, order: list[str]) -> None:
    """Inserts ``child`` into ``parent`` at its position in the schema ``order`` (local tag names)."""
    local = child.tag.split("}")[1]
    later = {qn(f"w:{name}") for name in order[order.index(local) + 1 :]}
    for existing in parent:
        if existing.tag in later:
            existing.addprevious(child)
            return
    parent.append(child)


def _shade(cell, hex_fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), hex_fill)
    _put(tc_pr, shading, _TCPR_ORDER)


def _cell_margins(table, top: int = 50, bottom: int = 50, left: int = 90, right: int = 90) -> None:
    tbl_pr = table._tbl.tblPr
    margins = OxmlElement("w:tblCellMar")
    for side, value in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        margins.append(node)
    _put(tbl_pr, margins, _TBLPR_ORDER)


def _table_borders(table, color: str = "BFC9D9", size: int = 4, inside: bool = True) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    edges = ["top", "left", "bottom", "right"] + (["insideH", "insideV"] if inside else [])
    for edge in edges:
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), str(size))
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), color)
        borders.append(node)
    _put(tbl_pr, borders, _TBLPR_ORDER)


def _fixed_layout(table) -> None:
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    _put(table._tbl.tblPr, layout, _TBLPR_ORDER)


def _row_flags(row, header: bool = False) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    _put(tr_pr, OxmlElement("w:cantSplit"), _TRPR_ORDER)
    if header:
        _put(tr_pr, OxmlElement("w:tblHeader"), _TRPR_ORDER)


def _para_border(paragraph, edge: str, color: str, size: int = 6, space: int = 1) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    borders = p_pr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        _put(p_pr, borders, ["pBdr", *_PPR_AFTER_PBDR])
    node = OxmlElement(f"w:{edge}")
    node.set(qn("w:val"), "single")
    node.set(qn("w:sz"), str(size))
    node.set(qn("w:space"), str(space))
    node.set(qn("w:color"), color)
    borders.append(node)


def _add_field(paragraph, instruction: str, placeholder: str = "1", size: float | None = None, color: str | None = None):
    def run_with(child):
        run = paragraph.add_run()
        if size:
            run.font.size = Pt(size)
        if color:
            run.font.color.rgb = _rgb(color)
        run._r.append(child)
        return run

    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run_with(begin)
    run_with(instr)
    run_with(separate)
    result = paragraph.add_run(placeholder)
    if size:
        result.font.size = Pt(size)
    if color:
        result.font.color.rgb = _rgb(color)
    run_with(end)


def _add_hyperlink(paragraph, url: str, text: str, size: float = 9) -> None:
    part = paragraph.part
    r_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), BLUE)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(size * 2)))
    for node in (color, sz, underline):  # schema order: color, sz, u
        r_pr.append(node)
    run.append(r_pr)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    run.append(t)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def _set_style_font(style, name: str, size: float | None = None, bold: bool | None = None, color: str | None = None) -> None:
    style.font.name = name
    r_pr = style.element.get_or_add_rPr()
    fonts = r_pr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        r_pr.append(fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), name)
    if size:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color:
        style.font.color.rgb = _rgb(color)


# --------------------------------------------------------------------------- rich text
def _add_rich_text(paragraph, text: str, size: float | None = None, color: str | None = None, bold: bool = False) -> None:
    for part in _INLINE_RE.split(_clean(text)):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("*") and part.endswith("*") and len(part) > 2 and not part.startswith("**"):
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        elif re.fullmatch(r"\[\d+(?:\s*,\s*\d+)*\]", part):
            run = paragraph.add_run(part)
            run.font.color.rgb = _rgb(BLUE)
            run.font.size = Pt((size or 10.5) - 1)
            run.bold = bold
            continue
        else:
            run = paragraph.add_run(part)
        if size:
            run.font.size = Pt(size)
        if color:
            run.font.color.rgb = _rgb(color)
        if bold:
            run.bold = True


# --------------------------------------------------------------------------- builder
class _Builder:
    def __init__(self, report: ReportDoc) -> None:
        self.report = report
        self.doc = Document()
        self.figure_no = 0
        self.table_no = 0
        self._break_pending = False  # next heading starts a new page (avoids an empty paragraph carrying a page break)
        self._setup_page()
        self._setup_styles()

    # -- setup ---------------------------------------------------------------
    def _setup_page(self) -> None:
        section = self.doc.sections[0]
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = Cm(PAGE_W_CM), Cm(PAGE_H_CM)
        section.left_margin = section.right_margin = Cm(MARGIN_LR_CM)
        section.top_margin, section.bottom_margin = Cm(MARGIN_TOP_CM), Cm(MARGIN_BOTTOM_CM)
        section.header_distance = section.footer_distance = Cm(1.0)
        section.different_first_page_header_footer = True  # cover page stays clean

    def _setup_styles(self) -> None:
        styles = self.doc.styles
        normal = styles["Normal"]
        _set_style_font(normal, BODY_FONT, 10.5, color="262626")
        normal.paragraph_format.space_after = Pt(6)
        normal.paragraph_format.space_before = Pt(0)
        normal.paragraph_format.line_spacing = 1.12

        for name, size, color, before, after in (
            ("Heading 1", 17, NAVY, 18, 8),
            ("Heading 2", 13, BLUE, 12, 4),
            ("Heading 3", 11, GREY, 8, 3),
        ):
            style = styles[name]
            _set_style_font(style, BODY_FONT, size, True, color)
            fmt = style.paragraph_format
            fmt.space_before, fmt.space_after = Pt(before), Pt(after)
            fmt.keep_with_next = True
            fmt.keep_together = True
            fmt.line_spacing = 1.0

        caption = styles["Caption"]
        _set_style_font(caption, BODY_FONT, 9, True, GREY)
        caption.font.italic = False
        caption.paragraph_format.space_before = Pt(2)
        caption.paragraph_format.space_after = Pt(5)

        bullet = styles["List Bullet"]
        bullet.paragraph_format.space_after = Pt(3)

        props = self.doc.core_properties
        props.title = _clean(self.report.title)
        props.subject = _clean(self.report.query)[:250]
        props.author = "Agentic Research Intelligence Platform"
        props.keywords = "research report, multi-agent RAG"

    # -- public --------------------------------------------------------------
    def build(self, path: Path) -> None:
        if self.report.compact:
            self._compact_title()
        else:
            self._cover()
            self._toc()
        chapter_no = 0
        appendix_started = False
        for index, chapter in enumerate(self.report.chapters):
            if chapter.appendix:
                heading = chapter.title
                if not appendix_started:
                    appendix_started = True
                    self._page_break()
            elif index == 0:
                heading = chapter.title  # executive summary is unnumbered
            else:
                chapter_no += 1
                heading = f"{chapter_no}. {chapter.title}"
            self._heading(heading, 1)
            self._chapter_blocks(chapter, chapter_no if not chapter.appendix and index else 0)
        self._header_footer()
        self._enable_field_update()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save(str(path))

    # -- pieces --------------------------------------------------------------
    def _page_break(self) -> None:
        self._break_pending = True

    def _consume_break(self, paragraph) -> None:
        if self._break_pending:
            paragraph.paragraph_format.page_break_before = True
            self._break_pending = False

    def _compact_title(self) -> None:
        """Overview briefings skip the cover page and contents: a title block sits at the top of page 1."""
        doc = self.doc
        title = doc.add_paragraph()
        title.paragraph_format.space_after = Pt(2)
        run = title.add_run(_clean(self.report.title))
        run.font.size, run.bold, run.font.color.rgb = Pt(22), True, _rgb(NAVY)
        if self.report.subtitle:
            sub = doc.add_paragraph()
            sub.paragraph_format.space_after = Pt(2)
            sub_run = sub.add_run(_clean(self.report.subtitle))
            sub_run.font.size, sub_run.font.color.rgb = Pt(12), _rgb(GREY)
        meta = doc.add_paragraph()
        meta.paragraph_format.space_after = Pt(8)
        meta_run = meta.add_run(f"Overview briefing  |  {self.report.date}  |  Sources: {self.report.meta.get('source_mix', 'web')}")
        meta_run.font.size, meta_run.italic, meta_run.font.color.rgb = Pt(9), True, _rgb(GREY)
        _para_border(meta, "bottom", NAVY, size=8)

    def _cover(self) -> None:
        doc = self.doc
        band = doc.add_table(rows=1, cols=1)
        band.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = band.rows[0].cells[0]
        _shade(cell, NAVY)
        _cell_margins(band, 500, 500, 420, 420)
        first = cell.paragraphs[0]
        first.paragraph_format.space_after = Pt(4)
        run = first.add_run("RESEARCH REPORT")
        run.font.size, run.bold = Pt(10), True
        run.font.color.rgb = _rgb("9DC3E6")
        title = cell.add_paragraph()
        title.paragraph_format.space_before = Pt(60)
        title.paragraph_format.space_after = Pt(10)
        title.paragraph_format.line_spacing = 1.0
        run = title.add_run(_clean(self.report.title))
        run.font.size, run.bold = Pt(30), True
        run.font.color.rgb = _rgb("FFFFFF")
        if self.report.subtitle:
            sub = cell.add_paragraph()
            sub.paragraph_format.space_after = Pt(70)
            run = sub.add_run(_clean(self.report.subtitle))
            run.font.size = Pt(14)
            run.font.color.rgb = _rgb("D6E4F5")

        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(30)

        meta = self.report.meta
        rows = [
            ("Research question", self.report.query),
            ("Date", self.report.date),
            ("Evidence base", f"{len(self.report.sources)} sources ({meta.get('source_mix', 'web, knowledge base')})"),
            ("Method", "Multi-agent pipeline: planner, research, analysis, critic (verification) and report agents"),
            ("Prepared by", "Agentic Research Intelligence Platform"),
        ]
        table = doc.add_table(rows=0, cols=2)
        _fixed_layout(table)
        _cell_margins(table, 80, 80, 100, 100)
        _table_borders(table, "D9E2F0", 4)
        for label, value in rows:
            cells = table.add_row().cells
            cells[0].width, cells[1].width = Cm(4.0), Cm(TEXT_W_CM - 4.0)
            _shade(cells[0], LIGHT)
            p = cells[0].paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(label)
            r.bold, r.font.size = True, Pt(9.5)
            r.font.color.rgb = _rgb(NAVY)
            p = cells[1].paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            _add_rich_text(p, value, 10)
        self._page_break()

    def _toc(self) -> None:
        heading = self.doc.add_paragraph()
        heading.paragraph_format.space_after = Pt(10)
        self._consume_break(heading)
        run = heading.add_run("Contents")
        run.bold, run.font.size = True, Pt(20)
        run.font.color.rgb = _rgb(NAVY)
        _para_border(heading, "bottom", BLUE, 8, 4)

        # Multi-paragraph TOC field: Word refreshes it (with page numbers) when the document is opened;
        # the pre-filled entries below are what viewers that don't update fields will show.
        entries: list[tuple[int, str]] = []
        chapter_no = 0
        for index, chapter in enumerate(self.report.chapters):
            if chapter.appendix or index == 0:
                entries.append((1, chapter.title))
            else:
                chapter_no += 1
                entries.append((1, f"{chapter_no}. {chapter.title}"))
            section_no = 0
            for block in chapter.blocks:
                if block.kind == "h2":
                    section_no += 1
                    numbered = not chapter.appendix and index != 0
                    entries.append((2, f"{chapter_no}.{section_no} {block.text}" if numbered else block.text))

        paragraphs = []
        for level, text in entries:
            p = self.doc.add_paragraph()
            p.paragraph_format.space_after = Pt(2 if level == 2 else 3)
            p.paragraph_format.space_before = Pt(5 if level == 1 else 0)
            p.paragraph_format.left_indent = Cm(0.0 if level == 1 else 0.7)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(TEXT_W_CM), WD_TAB_ALIGNMENT.RIGHT)
            run = p.add_run(_clean(text))
            run.font.size = Pt(10.5 if level == 1 else 9.5)
            run.bold = level == 1
            paragraphs.append(p)

        if paragraphs:
            first, last = paragraphs[0], paragraphs[-1]
            begin_run = first.runs[0]._r
            fld_begin = OxmlElement("w:fldChar")
            fld_begin.set(qn("w:fldCharType"), "begin")
            instr = OxmlElement("w:instrText")
            instr.set(qn("xml:space"), "preserve")
            instr.text = ' TOC \\o "1-2" \\h \\z \\u '
            separate = OxmlElement("w:fldChar")
            separate.set(qn("w:fldCharType"), "separate")
            for offset, node in enumerate((fld_begin, instr, separate)):
                holder = OxmlElement("w:r")
                holder.append(node)
                begin_run.addprevious(holder)
            fld_end = OxmlElement("w:fldChar")
            fld_end.set(qn("w:fldCharType"), "end")
            end_run = OxmlElement("w:r")
            end_run.append(fld_end)
            last._p.append(end_run)
        self._page_break()

    def _heading(self, text: str, level: int) -> None:
        paragraph = self.doc.add_heading(_clean(text), level=level)
        self._consume_break(paragraph)
        if level == 1:
            _para_border(paragraph, "bottom", BLUE, 8, 3)

    def _chapter_blocks(self, chapter: Chapter, chapter_no: int) -> None:
        section_no = 0
        for block in chapter.blocks:
            if block.kind == "h2":
                section_no += 1
                label = f"{chapter_no}.{section_no} {block.text}" if chapter_no else block.text
                self._heading(label, 2)
            elif block.kind == "h3":
                self._heading(block.text, 3)
            elif block.kind == "p":
                self._paragraph(block.text)
            elif block.kind == "bullets":
                self._bullets(block.items)
            elif block.kind == "numbered":
                self._numbered(block.items)
            elif block.kind == "table" and block.table:
                self._table(block.table)
            elif block.kind == "chart" and block.chart:
                self._chart(block.chart)
            elif block.kind == "callout":
                self._callout(block.label, block.text)

    def _paragraph(self, text: str) -> None:
        paragraph = self.doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _add_rich_text(paragraph, text)

    def _bullets(self, items: Iterable[str]) -> None:
        for item in items:
            paragraph = self.doc.add_paragraph(style="List Bullet")
            _add_rich_text(paragraph, item)

    def _numbered(self, items: Iterable[str]) -> None:
        for number, item in enumerate(items, start=1):
            paragraph = self.doc.add_paragraph()
            fmt = paragraph.paragraph_format
            fmt.left_indent, fmt.first_line_indent = Cm(0.75), Cm(-0.75)
            fmt.space_after = Pt(3)
            fmt.tab_stops.add_tab_stop(Cm(0.75))
            run = paragraph.add_run(f"{number}.\t")
            run.bold = True
            run.font.color.rgb = _rgb(BLUE)
            _add_rich_text(paragraph, item)

    def _callout(self, label: str, text: str) -> None:
        table = self.doc.add_table(rows=1, cols=1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _fixed_layout(table)
        _cell_margins(table, 90, 90, 160, 140)
        cell = table.rows[0].cells[0]
        cell.width = Cm(TEXT_W_CM)
        _shade(cell, LIGHT)
        tc_pr = cell._tc.get_or_add_tcPr()
        borders = OxmlElement("w:tcBorders")
        left = OxmlElement("w:left")
        left.set(qn("w:val"), "single")
        left.set(qn("w:sz"), "24")
        left.set(qn("w:color"), BLUE)
        borders.append(left)
        _put(tc_pr, borders, _TCPR_ORDER)
        _row_flags(table.rows[0])
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_after = Pt(0)
        if label:
            run = paragraph.add_run(f"{_clean(label)}  ")
            run.bold = True
            run.font.color.rgb = _rgb(NAVY)
        _add_rich_text(paragraph, text, 10)
        self._spacer()

    def _spacer(self, points: float = 4) -> None:
        paragraph = self.doc.add_paragraph()
        fmt = paragraph.paragraph_format
        fmt.space_after = Pt(0)
        fmt.space_before = Pt(0)
        fmt.line_spacing = Pt(points)
        for run in paragraph.runs:
            run.font.size = Pt(2)

    def _table(self, data: TableData) -> None:
        if not data.columns or not data.rows:
            return
        self.table_no += 1
        caption = self.doc.add_paragraph(style="Caption")
        caption.paragraph_format.keep_with_next = True
        caption.paragraph_format.space_before = Pt(6)
        _add_rich_text(caption, f"Table {self.table_no}: {data.title}")

        ncols = len(data.columns)
        table = self.doc.add_table(rows=1, cols=ncols)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _fixed_layout(table)
        _cell_margins(table)
        _table_borders(table)
        widths = self._column_widths(data)
        for i, name in enumerate(data.columns):
            cell = table.rows[0].cells[i]
            cell.width = Cm(widths[i])
            _shade(cell, NAVY)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.keep_with_next = True
            run = p.add_run(_clean(name))
            run.bold, run.font.size = True, Pt(9)
            run.font.color.rgb = _rgb("FFFFFF")
        _row_flags(table.rows[0], header=True)

        for r_index, row in enumerate(data.rows):
            cells = table.add_row().cells
            _row_flags(table.rows[-1])
            for i in range(ncols):
                cell = cells[i]
                cell.width = Cm(widths[i])
                if r_index % 2 == 1:
                    _shade(cell, BAND)
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                value = row[i] if i < len(row) else ""
                if isinstance(value, str) and value.startswith("http"):
                    _add_hyperlink(p, value, value if len(value) <= 60 else value[:57] + "...", 8)
                else:
                    _add_rich_text(p, value, 9)
        if data.note:
            note = self.doc.add_paragraph()
            note.paragraph_format.space_before = Pt(2)
            _add_rich_text(note, data.note, 8.5, GREY)
            for run in note.runs:
                run.italic = True
        else:
            self._spacer(6)

    @staticmethod
    def _column_widths(data: TableData) -> list[float]:
        ncols = len(data.columns)
        if data.col_widths and len(data.col_widths) == ncols:
            weights = [max(w, 0.1) for w in data.col_widths]
        else:
            weights = []
            for i in range(ncols):
                longest = max([len(str(data.columns[i]))] + [len(str(r[i])) for r in data.rows if i < len(r)])
                weights.append(min(max(longest, 8), 60) ** 0.85)
        total = sum(weights)
        return [TEXT_W_CM * w / total for w in weights]

    def _chart(self, chart: ChartData) -> None:
        try:
            png = render_chart(chart)
        except Exception:  # noqa: BLE001 - a chart must never break the whole report
            return
        self.figure_no += 1
        holder = self.doc.add_paragraph()
        holder.alignment = WD_ALIGN_PARAGRAPH.CENTER
        holder.paragraph_format.keep_with_next = True
        holder.paragraph_format.space_before = Pt(6)
        holder.paragraph_format.space_after = Pt(2)
        width = Cm(13.2 if chart.kind == "heatmap" else 15.2)
        holder.add_run().add_picture(io.BytesIO(png), width=width)
        caption = self.doc.add_paragraph(style="Caption")
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_rich_text(caption, f"Figure {self.figure_no}: {chart.title}")
        if chart.note:
            run = caption.add_run(f"  ({_clean(chart.note)})")
            run.bold = False
            run.italic = True
            run.font.size = Pt(8.5)

    def _header_footer(self) -> None:
        section = self.doc.sections[0]
        header = section.header
        header.is_linked_to_previous = False
        p = header.paragraphs[0]
        p.paragraph_format.tab_stops.add_tab_stop(Cm(TEXT_W_CM), WD_TAB_ALIGNMENT.RIGHT)
        title = _clean(self.report.title)
        run = p.add_run(title if len(title) <= 70 else title[:67] + "...")
        run.font.size, run.bold = Pt(8.5), True
        run.font.color.rgb = _rgb(NAVY)
        run = p.add_run("\tResearch Report")
        run.font.size = Pt(8.5)
        run.font.color.rgb = _rgb(GREY)
        _para_border(p, "bottom", "BFC9D9", 4, 4)

        footer = section.footer
        footer.is_linked_to_previous = False
        p = footer.paragraphs[0]
        p.paragraph_format.tab_stops.add_tab_stop(Cm(TEXT_W_CM), WD_TAB_ALIGNMENT.RIGHT)
        _para_border(p, "top", "BFC9D9", 4, 4)
        run = p.add_run(f"Agentic Research Intelligence Platform  |  {self.report.date}\tPage ")
        run.font.size = Pt(8.5)
        run.font.color.rgb = _rgb(GREY)
        _add_field(p, "PAGE", "1", 8.5, GREY)
        run = p.add_run(" of ")
        run.font.size = Pt(8.5)
        run.font.color.rgb = _rgb(GREY)
        _add_field(p, "NUMPAGES", "1", 8.5, GREY)

    def _enable_field_update(self) -> None:
        settings = self.doc.settings.element
        node = OxmlElement("w:updateFields")
        node.set(qn("w:val"), "true")
        for tag in ("w:hdrShapeDefaults", "w:footnotePr", "w:endnotePr", "w:compat", "w:docVars", "w:rsids"):
            anchor = settings.find(qn(tag))
            if anchor is not None:
                anchor.addprevious(node)
                return
        settings.append(node)


def build_docx(report: ReportDoc, path: Path) -> Path:
    _Builder(report).build(path)
    return path


def estimate_pages(report: ReportDoc) -> int:
    """Rough page estimate (A4, 10.5pt body) used to enforce the page cap before rendering."""
    pages = 0.6 if report.compact else 2.0  # cover + contents (contents may spill; counted below)
    headings = sum(1 + sum(1 for b in c.blocks if b.kind == "h2") for c in report.chapters)
    pages += headings / 45
    for chapter in report.chapters:
        pages += 0.06
        for block in chapter.blocks:
            if block.kind == "h2":
                pages += 0.04
            elif block.kind in {"p", "callout"}:
                pages += (len(block.text.split()) / 480) + 0.012
            elif block.kind in {"bullets", "numbered"}:
                pages += sum(len(i.split()) / 430 + 0.01 for i in block.items)
            elif block.kind == "table" and block.table:
                pages += 0.1 + sum(0.03 + max(len(str(c)) for c in r) / 5000 for r in block.table.rows) if block.table.rows else 0
            elif block.kind == "chart":
                pages += 0.4
    return max(3, int(pages + 0.999))
