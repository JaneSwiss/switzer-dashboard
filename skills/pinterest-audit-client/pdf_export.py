"""
pdf_export.py — Branded PDF export for Pinterest Client Audit.
Styled to match the Switzertemplates visual identity.
Uses ReportLab (already installed).
"""

from __future__ import annotations
import re
import sys
from pathlib import Path
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether,
)
from reportlab.lib.colors import HexColor
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics import renderPDF

# ── Brand colours ──────────────────────────────────────────────────────────────
BG          = HexColor("#faf7f4")   # warm cream page background
ESPRESSO    = HexColor("#2c1810")   # deep title text
CHOCOLATE   = HexColor("#8d6e63")   # accent, section labels
TAUPE       = HexColor("#bbb0aa")   # rules, secondary text
SAND        = HexColor("#a5988e")   # muted labels
CHARCOAL    = HexColor("#383838")   # body text
CREAM       = HexColor("#f8f5f2")   # table alt row
WHITE       = HexColor("#ffffff")
ROW_ALT     = HexColor("#f4f0ec")   # table alternating row

PAGE_W, PAGE_H = A4
MARGIN = 22 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


# ── Styles ─────────────────────────────────────────────────────────────────────

def build_styles():
    base = getSampleStyleSheet()

    def S(name, parent="Normal", **kw):
        return ParagraphStyle(name, parent=base[parent], **kw)

    return {
        "cover_title": ParagraphStyle(
            "cover_title", fontSize=36, textColor=ESPRESSO,
            fontName="Times-Bold", alignment=TA_LEFT, leading=42, spaceAfter=4,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", fontSize=16, textColor=CHOCOLATE,
            fontName="Times-Italic", alignment=TA_LEFT, leading=22, spaceAfter=12,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta", fontSize=9, textColor=SAND,
            fontName="Helvetica", alignment=TA_LEFT, leading=14,
        ),
        "section_label": ParagraphStyle(
            "section_label", fontSize=8, textColor=CHOCOLATE,
            fontName="Helvetica-Bold", alignment=TA_LEFT, leading=12,
            spaceBefore=14, spaceAfter=2, letterSpacing=1.5,
        ),
        "h2": ParagraphStyle(
            "h2", fontSize=14, textColor=ESPRESSO,
            fontName="Times-Bold", alignment=TA_LEFT, leading=18,
            spaceBefore=16, spaceAfter=2,
        ),
        "h3": ParagraphStyle(
            "h3", fontSize=11, textColor=CHOCOLATE,
            fontName="Helvetica-Bold", alignment=TA_LEFT, leading=15,
            spaceBefore=10, spaceAfter=2,
        ),
        "h4": ParagraphStyle(
            "h4", fontSize=9.5, textColor=CHARCOAL,
            fontName="Helvetica-Bold", alignment=TA_LEFT, leading=13,
            spaceBefore=6, spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "body", fontSize=9, textColor=CHARCOAL,
            fontName="Helvetica", leading=14, spaceAfter=4,
        ),
        "body_small": ParagraphStyle(
            "body_small", fontSize=8, textColor=CHARCOAL,
            fontName="Helvetica", leading=12, spaceAfter=2,
        ),
        "meta": ParagraphStyle(
            "meta", fontSize=8, textColor=SAND,
            fontName="Helvetica-Oblique", leading=12, spaceAfter=2,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontSize=9, textColor=CHARCOAL,
            fontName="Helvetica", leading=13, leftIndent=12,
            firstLineIndent=-8, spaceAfter=2,
        ),
        "numbered": ParagraphStyle(
            "numbered", fontSize=9, textColor=CHARCOAL,
            fontName="Helvetica", leading=13, leftIndent=14,
            firstLineIndent=-14, spaceAfter=3,
        ),
        "tbl_header": ParagraphStyle(
            "tbl_header", fontSize=8, textColor=WHITE,
            fontName="Helvetica-Bold", leading=11,
        ),
        "tbl_cell": ParagraphStyle(
            "tbl_cell", fontSize=8, textColor=CHARCOAL,
            fontName="Helvetica", leading=11,
        ),
        "stat_value": ParagraphStyle(
            "stat_value", fontSize=20, textColor=CHOCOLATE,
            fontName="Times-Bold", alignment=TA_CENTER, leading=24,
        ),
        "stat_label": ParagraphStyle(
            "stat_label", fontSize=7.5, textColor=SAND,
            fontName="Helvetica", alignment=TA_CENTER, leading=11,
        ),
        "pill": ParagraphStyle(
            "pill", fontSize=8.5, textColor=ESPRESSO,
            fontName="Helvetica", alignment=TA_CENTER, leading=12,
        ),
        "footer": ParagraphStyle(
            "footer", fontSize=7, textColor=TAUPE,
            fontName="Helvetica", alignment=TA_CENTER,
        ),
    }


# ── Page template ──────────────────────────────────────────────────────────────

class AuditDoc(BaseDocTemplate):
    def __init__(self, filename, niche: str, run_date: str, **kw):
        super().__init__(filename, pagesize=A4, **kw)
        self.niche = niche
        self.run_date = run_date
        self._build_templates()

    def _build_templates(self):
        # Cover page — full bleed, no header/footer chrome
        cover_frame = Frame(
            MARGIN, MARGIN,
            CONTENT_W, PAGE_H - 2 * MARGIN,
            id="cover",
        )
        # Content pages
        content_frame = Frame(
            MARGIN, MARGIN + 10 * mm,
            CONTENT_W, PAGE_H - 2 * MARGIN - 22 * mm,
            id="content",
        )
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[cover_frame], onPage=self._draw_cover_bg),
            PageTemplate(id="content", frames=[content_frame], onPage=self._draw_page_chrome),
        ])

    def _draw_cover_bg(self, canvas, doc):
        canvas.saveState()
        # Warm cream background
        canvas.setFillColor(BG)
        canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        # Left accent bar
        canvas.setFillColor(CHOCOLATE)
        canvas.rect(0, 0, 5 * mm, PAGE_H, fill=1, stroke=0)
        # Bottom strip
        canvas.setFillColor(ESPRESSO)
        canvas.rect(0, 0, PAGE_W, 12 * mm, fill=1, stroke=0)
        canvas.setFillColor(TAUPE)
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(PAGE_W / 2, 4.5 * mm, "PINTEREST NICHE AUDIT  ·  SWITZERTEMPLATES.COM")
        canvas.restoreState()

    def _draw_page_chrome(self, canvas, doc):
        canvas.saveState()
        # Warm cream background
        canvas.setFillColor(BG)
        canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        # Top rule line
        canvas.setStrokeColor(TAUPE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, PAGE_H - 16 * mm, PAGE_W - MARGIN, PAGE_H - 16 * mm)
        # Top label
        canvas.setFillColor(TAUPE)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(MARGIN, PAGE_H - 13 * mm, "PINTEREST NICHE AUDIT")
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 13 * mm, self.run_date)
        # Bottom rule + footer
        canvas.setStrokeColor(TAUPE)
        canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
        canvas.setFillColor(TAUPE)
        canvas.drawCentredString(
            PAGE_W / 2, 10 * mm,
            f"switzertemplates.com  ·  Page {doc.page}"
        )
        # Left accent bar (thin)
        canvas.setFillColor(CHOCOLATE)
        canvas.rect(0, 0, 2.5 * mm, PAGE_H, fill=1, stroke=0)
        canvas.restoreState()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r'<font color="#8d6e63"><b>\1</b></font>', text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<link href="\2" color="#8d6e63"><u>\1</u></link>',
        text,
    )
    return text


def _section_header(text: str, styles) -> list:
    """Uppercase small-caps section header with rule — matches PDF visual style."""
    return [
        Spacer(1, 4 * mm),
        Paragraph(text.upper(), styles["section_label"]),
        HRFlowable(width="100%", thickness=0.8, color=CHOCOLATE,
                   spaceBefore=1, spaceAfter=6),
    ]


def _build_table(raw_rows: list[list[str]], styles) -> Table | None:
    if len(raw_rows) < 2:
        return None

    def cell(text: str, is_header: bool = False) -> Paragraph:
        text = _inline(_escape(text.strip()))
        return Paragraph(text, styles["tbl_header"] if is_header else styles["tbl_cell"])

    header = raw_rows[0]
    data_rows = [r for r in raw_rows[1:] if not all(re.match(r"^[-:]+$", c.strip()) for c in r if c.strip())]

    table_data = [[cell(h, True) for h in header]]
    for row in data_rows:
        while len(row) < len(header):
            row.append("")
        table_data.append([cell(c) for c in row[:len(header)]])

    # Column width distribution
    col_n = len(header)
    col_w = [CONTENT_W / col_n] * col_n

    # Widen first substantive column
    wide_idx = next(
        (i for i, h in enumerate(header)
         if h.lower().strip() in ("keyword", "buyer question", "board name", "keyword / angle", "#")),
        0,
    )
    if col_n > 2:
        bonus = CONTENT_W * 0.18
        col_w[wide_idx] += bonus
        shrink = bonus / (col_n - 1)
        col_w = [w - shrink if i != wide_idx else w for i, w in enumerate(col_w)]

    ts = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  CHARCOAL),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  8),
        ("TOPPADDING",    (0, 0), (-1, 0),  5),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("FONTSIZE",      (0, 1), (-1, -1), 7.5),
        ("TOPPADDING",    (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, ROW_ALT]),
        ("GRID",          (0, 0), (-1, -1), 0.3, TAUPE),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ])

    return Table(table_data, colWidths=col_w, style=ts, repeatRows=1, hAlign="LEFT")


def _stat_cards(stats: list[dict], styles) -> Table:
    """Render stat cards as a horizontal table row."""
    n = len(stats)
    if n == 0:
        return None
    w = CONTENT_W / n

    header_cells = []
    label_cells = []
    for s in stats:
        header_cells.append(Paragraph(_escape(str(s.get("value", ""))), styles["stat_value"]))
        label_cells.append(Paragraph(_escape(str(s.get("label", ""))), styles["stat_label"]))

    ts = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, CHOCOLATE),
        ("GRID",          (0, 0), (-1, -1), 0.3, TAUPE),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ])
    tbl = Table(
        [header_cells, label_cells],
        colWidths=[w] * n,
        style=ts,
        hAlign="LEFT",
    )
    return tbl


def _keyword_pills(keywords: list[str], styles) -> Table | None:
    """Render keyword list as a grid of pill-style cells."""
    if not keywords:
        return None

    per_row = 3
    pill_w = CONTENT_W / per_row
    rows = []
    row = []
    for i, kw in enumerate(keywords):
        row.append(Paragraph(_escape(kw), styles["pill"]))
        if len(row) == per_row:
            rows.append(row)
            row = []
    if row:
        while len(row) < per_row:
            row.append(Paragraph("", styles["pill"]))
        rows.append(row)

    ts = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("BOX",           (0, 0), (-1, -1), 0.5, TAUPE),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, TAUPE),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [WHITE, ROW_ALT]),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
    ])
    return Table(rows, colWidths=[pill_w] * per_row, style=ts, hAlign="LEFT")


def _colour_swatches(table_rows: list[list[str]], styles) -> Table | None:
    """Render colour palette table with actual coloured swatch boxes."""
    # Expects rows like: [Colour Name, Hex, Mood, Use in Pins]
    if not table_rows:
        return None

    swatch_w = 14 * mm
    rest_w = CONTENT_W - swatch_w
    col_widths = [swatch_w, rest_w * 0.22, rest_w * 0.30, rest_w * 0.48]

    rows = []
    # Header
    rows.append([
        Paragraph("", styles["tbl_header"]),
        Paragraph("COLOUR", styles["tbl_header"]),
        Paragraph("MOOD", styles["tbl_header"]),
        Paragraph("USE IN PINS", styles["tbl_header"]),
    ])

    for row in table_rows:
        while len(row) < 4:
            row.append("")
        colour_name = row[0].strip()
        hex_code = row[1].strip()
        mood = row[2].strip()
        use = row[3].strip()

        # Try to create a coloured swatch
        try:
            swatch_color = HexColor(hex_code if hex_code.startswith("#") else f"#{hex_code}")
            d = Drawing(swatch_w, 10 * mm)
            d.add(Rect(1 * mm, 1 * mm, swatch_w - 2 * mm, 8 * mm,
                       fillColor=swatch_color, strokeColor=TAUPE, strokeWidth=0.3))
            swatch_cell = d
        except Exception:
            swatch_cell = Paragraph("", styles["tbl_cell"])

        rows.append([
            swatch_cell,
            Paragraph(f"<b>{_escape(colour_name)}</b><br/><font color='#a5988e'>{_escape(hex_code)}</font>",
                      styles["tbl_cell"]),
            Paragraph(_escape(mood), styles["tbl_cell"]),
            Paragraph(_escape(use), styles["tbl_cell"]),
        ])

    ts = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  CHARCOAL),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  7.5),
        ("TOPPADDING",    (0, 0), (-1, 0),  5),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, ROW_ALT]),
        ("GRID",          (0, 0), (-1, -1), 0.3, TAUPE),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ])
    return Table(rows, colWidths=col_widths, style=ts, hAlign="LEFT")


# ── Markdown parser ────────────────────────────────────────────────────────────

def parse_markdown(md_text: str, styles) -> list:
    flowables = []
    lines = md_text.splitlines()
    i = 0
    in_stat_grid = False
    stat_cards_buffer = []
    keyword_list_mode = False
    keyword_items = []
    in_colour_table = False
    colour_rows = []

    while i < len(lines):
        line = lines[i]

        # ── Stat grid HTML blocks ──────────────────────────────────────────
        if '<div class="stat-grid">' in line:
            in_stat_grid = True
            stat_cards_buffer = []
            i += 1
            continue

        if in_stat_grid:
            if '</div>' in line and 'stat-card' not in line:
                # End of grid
                in_stat_grid = False
                if stat_cards_buffer:
                    tbl = _stat_cards(stat_cards_buffer, styles)
                    if tbl:
                        flowables.append(tbl)
                        flowables.append(Spacer(1, 4 * mm))
                i += 1
                continue
            # Parse individual stat card
            val_m = re.search(r'class="stat-value">([^<]+)<', line)
            lbl_m = re.search(r'class="stat-label">([^<]+)<', line)
            if val_m and lbl_m:
                stat_cards_buffer.append({
                    "value": val_m.group(1),
                    "label": lbl_m.group(1),
                })
            i += 1
            continue

        # ── HR ─────────────────────────────────────────────────────────────
        if re.match(r"^---+$", line.strip()):
            flowables.append(HRFlowable(
                width="100%", thickness=0.4, color=TAUPE,
                spaceBefore=6, spaceAfter=6,
            ))
            i += 1
            continue

        # ── H1 (skip — shown in cover) ─────────────────────────────────────
        if line.startswith("# ") and not line.startswith("## "):
            i += 1
            continue

        # ── H2 — section header style ──────────────────────────────────────
        if line.startswith("## "):
            text = line[3:].strip()
            flowables += _section_header(text, styles)
            keyword_list_mode = (
                "trending keywords" in text.lower() or
                "keywords in your niche" in text.lower()
            )
            if keyword_list_mode:
                keyword_items = []
            i += 1
            continue

        # ── H3 ─────────────────────────────────────────────────────────────
        if line.startswith("### "):
            # Flush keyword pills before new subsection
            if keyword_list_mode and keyword_items:
                tbl = _keyword_pills(keyword_items, styles)
                if tbl:
                    flowables.append(tbl)
                    flowables.append(Spacer(1, 4 * mm))
                keyword_items = []
                keyword_list_mode = False
            text = _inline(_escape(line[4:].strip()))
            flowables.append(Paragraph(text, styles["h3"]))
            i += 1
            continue

        # ── H4 ─────────────────────────────────────────────────────────────
        if line.startswith("#### "):
            text = _inline(_escape(line[5:].strip()))
            flowables.append(Paragraph(text, styles["h4"]))
            i += 1
            continue

        # ── Table ──────────────────────────────────────────────────────────
        if line.startswith("|"):
            raw_rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip("|").split("|")]
                raw_rows.append(cells)
                i += 1

            # Detect colour palette table (has "hex" in header)
            header_lower = " ".join(raw_rows[0]).lower() if raw_rows else ""
            data_rows = [r for r in raw_rows[1:] if not all(re.match(r"^[-:]+$", c.strip()) for c in r if c.strip())]

            if "hex" in header_lower or "colour name" in header_lower or "color name" in header_lower:
                tbl = _colour_swatches(data_rows, styles)
            else:
                all_rows = [raw_rows[0]] + data_rows
                tbl = _build_table(all_rows, styles)

            if tbl:
                flowables.append(tbl)
                flowables.append(Spacer(1, 3 * mm))
            continue

        # ── Numbered list ──────────────────────────────────────────────────
        if re.match(r"^\d+\. ", line):
            if keyword_list_mode:
                # Collect keywords for pill display
                while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                    m = re.match(r"^\d+\. (.+)", lines[i])
                    if m:
                        keyword_items.append(m.group(1).strip())
                    i += 1
                continue
            else:
                while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                    m = re.match(r"^(\d+)\. (.+)", lines[i])
                    num = m.group(1)
                    text = _inline(_escape(m.group(2).strip()))
                    flowables.append(Paragraph(
                        f'<font color="#8d6e63"><b>{num}.</b></font>  {text}',
                        styles["numbered"],
                    ))
                    i += 1
                continue

        # ── Bullet list ────────────────────────────────────────────────────
        if re.match(r"^[-*] ", line):
            while i < len(lines) and re.match(r"^[-*] ", lines[i]):
                text = _inline(_escape(lines[i][2:].strip()))
                flowables.append(Paragraph(f"•  {text}", styles["bullet"]))
                i += 1
            continue

        # ── Bold-only line → h4 ────────────────────────────────────────────
        if re.match(r"^\*\*[^*]+\*\*$", line.strip()):
            text = line.strip()[2:-2]
            flowables.append(Paragraph(_escape(text), styles["h4"]))
            i += 1
            continue

        # ── Italic line → meta ─────────────────────────────────────────────
        if re.match(r"^\*[^*].+[^*]\*$", line.strip()):
            text = line.strip().strip("*")
            flowables.append(Paragraph(_escape(text), styles["meta"]))
            i += 1
            continue

        # ── Metadata lines (** prefix) ─────────────────────────────────────
        if line.strip().startswith("**"):
            text = _inline(_escape(line.strip()))
            flowables.append(Paragraph(text, styles["body"]))
            i += 1
            continue

        # ── Empty line ─────────────────────────────────────────────────────
        if not line.strip():
            flowables.append(Spacer(1, 1.5 * mm))
            i += 1
            continue

        # ── Default paragraph ──────────────────────────────────────────────
        text = _inline(_escape(line.strip()))
        if text:
            flowables.append(Paragraph(text, styles["body"]))
        i += 1

    # Flush any remaining keyword pills
    if keyword_list_mode and keyword_items:
        tbl = _keyword_pills(keyword_items, styles)
        if tbl:
            flowables.append(tbl)

    return flowables


# ── Cover page ─────────────────────────────────────────────────────────────────

def build_cover(niche: str, products: str, run_date: str, styles) -> list:
    items = []
    items.append(Spacer(1, 20 * mm))

    items.append(Paragraph("Pinterest", ParagraphStyle(
        "cv1", fontSize=14, textColor=CHOCOLATE,
        fontName="Helvetica", leading=18, letterSpacing=3,
    )))
    items.append(Spacer(1, 2 * mm))
    items.append(Paragraph("Niche Audit", styles["cover_title"]))
    items.append(Spacer(1, 1 * mm))
    items.append(Paragraph(niche, styles["cover_sub"]))
    items.append(Spacer(1, 6 * mm))
    items.append(HRFlowable(
        width="40%", thickness=1.5, color=CHOCOLATE,
        spaceAfter=8, hAlign="LEFT",
    ))
    items.append(Spacer(1, 4 * mm))
    items.append(Paragraph(f"Generated  {run_date}", styles["cover_meta"]))
    items.append(Spacer(1, 2 * mm))
    items.append(Paragraph(f"Products / Services:  {products}", styles["cover_meta"]))
    items.append(Spacer(1, 20 * mm))

    # Section index
    toc = [
        "01  Niche Overview",
        "02  Trending Keywords",
        "03  Keyword Cluster Groupings",
        "04  What Buyers Are Asking",
        "05  Pinterest Trends in Your Niche",
        "06  Content Gap Opportunities",
        "07  Pinterest Strategy & Growth Plan",
        "08  Board Structure Recommendations",
    ]
    toc_style = ParagraphStyle(
        "toc", fontSize=9, textColor=CHARCOAL,
        fontName="Helvetica", leading=20, leftIndent=0,
    )
    for entry in toc:
        items.append(Paragraph(entry, toc_style))

    return items


# ── Main export ────────────────────────────────────────────────────────────────

def export_pdf(md_path: Path) -> str:
    content = md_path.read_text(encoding="utf-8")

    # Extract metadata
    title_m = re.search(r"^# Pinterest Niche Audit — (.+)$", content, re.MULTILINE)
    niche = title_m.group(1) if title_m else "Pinterest Audit"

    date_m = re.search(r"\*\*Generated:\*\* (\S+)", content)
    run_date = date_m.group(1) if date_m else datetime.now().strftime("%Y-%m-%d")

    products_m = re.search(r"\*\*Products/Services:\*\* (.+)$", content, re.MULTILINE)
    products = products_m.group(1).strip() if products_m else ""

    pdf_path = md_path.with_suffix(".pdf")
    styles = build_styles()

    doc = AuditDoc(
        str(pdf_path), niche=niche, run_date=run_date,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + 18 * mm, bottomMargin=MARGIN + 12 * mm,
    )

    story = []

    # Cover (uses cover template — no header/footer chrome)
    story.append(NextPageTemplate("cover"))
    story += build_cover(niche, products, run_date, styles)
    story.append(PageBreak())

    # Body (switches to content template)
    story.append(NextPageTemplate("content"))
    story += parse_markdown(content, styles)

    doc.build(story)
    return str(pdf_path)


# Allow NextPageTemplate import
from reportlab.platypus import NextPageTemplate


if __name__ == "__main__":
    from pathlib import Path
    import glob, os

    if len(sys.argv) > 1:
        md = Path(sys.argv[1])
    else:
        # Most recent audit
        pattern = str(Path(__file__).parent.parent.parent / "outputs" / "client-audits" / "*.md")
        candidates = sorted(glob.glob(pattern), reverse=True)
        if not candidates:
            print("No audit markdown found.")
            sys.exit(1)
        md = Path(candidates[0])

    print(f"  Generating PDF from {md.name}...")
    try:
        out = export_pdf(md)
        print(f"  Saved: {out}")
    except Exception as e:
        import traceback
        traceback.print_exc()
