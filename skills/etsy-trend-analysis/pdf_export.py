"""
PDF export for Switzertemplates Etsy Trend Report.
Converts the markdown report to a branded PDF with clickable links.

Usage:
    python3 skills/etsy-trend-analysis/pdf_export.py
    python3 skills/etsy-trend-analysis/pdf_export.py outputs/etsy-sales/etsy-trend-report-2026-04-21.md
"""

import re
import sys
from pathlib import Path
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Paragraph, Spacer, Table, TableStyle, HRFlowable,
    KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.colors import HexColor

# ── Brand colours ─────────────────────────────────────────────────────────────
CREAM        = HexColor("#f8f5f2")
TAUPE        = HexColor("#bbb0aa")
SAND         = HexColor("#a5988e")
CHOCOLATE    = HexColor("#8d6e63")
CHARCOAL     = HexColor("#383838")
WHITE        = HexColor("#ffffff")
LIGHT_TAUPE  = HexColor("#e8e3de")   # table row alternating
ALERT_RED    = HexColor("#c0392b")   # zero-sales / critical flags
PRIORITY_AMBER = HexColor("#b5651d") # high priority labels

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs" / "etsy-sales"


# ── Styles ────────────────────────────────────────────────────────────────────

def build_styles():
    base = getSampleStyleSheet()

    def S(name, parent="Normal", **kw):
        return ParagraphStyle(name, parent=base[parent], **kw)

    return {
        "h1": S("h1", fontSize=22, textColor=CHARCOAL, spaceAfter=6,
                fontName="Helvetica-Bold", leading=28),
        "h2": S("h2", fontSize=14, textColor=CHOCOLATE, spaceBefore=14,
                spaceAfter=4, fontName="Helvetica-Bold", leading=18,
                borderPad=0),
        "h3": S("h3", fontSize=11, textColor=CHARCOAL, spaceBefore=8,
                spaceAfter=3, fontName="Helvetica-Bold", leading=15),
        "body": S("body", fontSize=9, textColor=CHARCOAL, spaceAfter=4,
                  leading=14, fontName="Helvetica"),
        "body_small": S("body_small", fontSize=8, textColor=CHARCOAL,
                        leading=12, fontName="Helvetica"),
        "bold": S("bold", fontSize=9, textColor=CHARCOAL, spaceAfter=4,
                  leading=14, fontName="Helvetica-Bold"),
        "bullet": S("bullet", fontSize=9, textColor=CHARCOAL, spaceAfter=2,
                    leading=13, leftIndent=12, firstLineIndent=-8,
                    fontName="Helvetica"),
        "meta": S("meta", fontSize=8, textColor=SAND, spaceAfter=2,
                  leading=12, fontName="Helvetica"),
        "footer": S("footer", fontSize=7.5, textColor=TAUPE, alignment=TA_CENTER,
                    fontName="Helvetica"),
        "kw_highlight": S("kw_highlight", fontSize=9, textColor=CHOCOLATE,
                          fontName="Helvetica-Bold", leading=14),
        "action_title": S("action_title", fontSize=10, textColor=WHITE,
                          fontName="Helvetica-Bold", leading=14),
        "priority": S("priority", fontSize=8.5, textColor=PRIORITY_AMBER,
                      fontName="Helvetica-Bold", leading=12),
    }


# ── Page template (header/footer) ─────────────────────────────────────────────

class BrandedDoc(BaseDocTemplate):
    def __init__(self, filename, report_date, **kw):
        super().__init__(filename, pagesize=A4, **kw)
        self.report_date = report_date
        self._add_page_templates()

    def _add_page_templates(self):
        frame = Frame(
            MARGIN, MARGIN + 12 * mm,
            PAGE_W - 2 * MARGIN, PAGE_H - 2 * MARGIN - 20 * mm,
            id="main",
        )
        self.addPageTemplates([
            PageTemplate(id="main", frames=[frame], onPage=self._draw_chrome)
        ])

    def _draw_chrome(self, canvas, doc):
        canvas.saveState()

        # Top bar
        canvas.setFillColor(CHOCOLATE)
        canvas.rect(0, PAGE_H - 14 * mm, PAGE_W, 14 * mm, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(MARGIN, PAGE_H - 9 * mm, "SWITZERTEMPLATES")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(
            PAGE_W - MARGIN, PAGE_H - 9 * mm,
            f"Etsy Trend Report  •  {self.report_date}"
        )

        # Bottom bar
        canvas.setFillColor(LIGHT_TAUPE)
        canvas.rect(0, 0, PAGE_W, 12 * mm, fill=1, stroke=0)
        canvas.setFillColor(SAND)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawCentredString(
            PAGE_W / 2, 4.5 * mm,
            f"Confidential  •  switzertemplates.com  •  Page {doc.page}"
        )

        canvas.restoreState()


# ── Markdown parser → flowables ───────────────────────────────────────────────

def _escape(text: str) -> str:
    """Escape XML special chars for ReportLab Paragraph."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _inline(text: str, styles) -> str:
    """Convert inline markdown (**bold**, `code`, links) to ReportLab XML."""
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Code/keyword spans
    text = re.sub(r"`([^`]+)`",
                  r'<font color="#8d6e63"><b>\1</b></font>', text)
    # Links [text](url)
    def link_sub(m):
        label = m.group(1)
        url   = m.group(2)
        return f'<link href="{url}" color="#8d6e63"><u>{label}</u></link>'
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_sub, text)
    # ⚡ icon colour
    text = text.replace("⚡", '<font color="#b5651d">⚡</font>')
    return text


def _table_from_md(rows: list[list[str]], styles) -> Table:
    """Build a styled ReportLab table from a list of row lists."""
    if not rows:
        return None

    header = rows[0]
    data   = rows[1:]  # skip separator row (---)

    def cell(text, is_header=False):
        text = _inline(_escape(text.strip()), styles)
        style = styles["bold"] if is_header else styles["body_small"]
        return Paragraph(text, style)

    table_data = [[cell(h, True) for h in header]]
    for row in data:
        # Pad or trim to match header width
        while len(row) < len(header):
            row.append("")
        row = row[:len(header)]
        table_data.append([cell(c) for c in row])

    col_count  = len(header)
    avail_w    = PAGE_W - 2 * MARGIN
    col_widths = [avail_w / col_count] * col_count

    # Give title column more space if it exists
    title_idx = next(
        (i for i, h in enumerate(header) if h.lower() in ("title", "keyword", "action")),
        None,
    )
    if title_idx is not None and col_count > 3:
        extra = avail_w * 0.20
        col_widths[title_idx] += extra
        reduction = extra / (col_count - 1)
        col_widths = [
            w - reduction if i != title_idx else w
            for i, w in enumerate(col_widths)
        ]

    ts = TableStyle([
        # Header row
        ("BACKGROUND",   (0, 0), (-1, 0),  CHOCOLATE),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0),  8.5),
        ("BOTTOMPADDING",(0, 0), (-1, 0),  6),
        ("TOPPADDING",   (0, 0), (-1, 0),  6),
        # Data rows
        ("FONTSIZE",     (0, 1), (-1, -1), 8),
        ("TOPPADDING",   (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("GRID",         (0, 0), (-1, -1), 0.4, TAUPE),
        ("ROWBACKGROUNDS",(0, 1),(-1, -1), [WHITE, LIGHT_TAUPE]),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
    ])

    return Table(table_data, colWidths=col_widths, style=ts, repeatRows=1,
                 hAlign="LEFT")


def parse_markdown(md_text: str, styles) -> list:
    """
    Convert markdown text to a list of ReportLab flowables.
    Handles: # headings, tables, bullet lists, bold paragraphs, --- dividers.
    """
    flowables = []
    lines      = md_text.splitlines()
    i          = 0

    while i < len(lines):
        line = lines[i]

        # --- HR
        if re.match(r"^---+$", line.strip()):
            flowables.append(HRFlowable(
                width="100%", thickness=0.5, color=TAUPE,
                spaceBefore=4, spaceAfter=4,
            ))
            i += 1
            continue

        # H1
        if line.startswith("# ") and not line.startswith("## "):
            text = _inline(_escape(line[2:].strip()), styles)
            flowables.append(Paragraph(text, styles["h1"]))
            i += 1
            continue

        # H2
        if line.startswith("## "):
            text = _inline(_escape(line[3:].strip()), styles)
            flowables.append(Spacer(1, 3 * mm))
            flowables.append(Paragraph(text, styles["h2"]))
            flowables.append(HRFlowable(
                width="100%", thickness=1, color=CHOCOLATE,
                spaceBefore=1, spaceAfter=4,
            ))
            i += 1
            continue

        # H3
        if line.startswith("### "):
            text = _inline(_escape(line[4:].strip()), styles)
            flowables.append(Paragraph(text, styles["h3"]))
            i += 1
            continue

        # Table (starts with |)
        if line.startswith("|"):
            raw_rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip("|").split("|")]
                raw_rows.append(cells)
                i += 1
            # Remove separator row (contains ---)
            filtered = [r for r in raw_rows if not all(re.match(r"^-+$", c.strip("-: ")) for c in r if c)]
            tbl = _table_from_md(filtered, styles)
            if tbl:
                flowables.append(tbl)
                flowables.append(Spacer(1, 3 * mm))
            continue

        # Bullet list
        if re.match(r"^[-*] ", line):
            while i < len(lines) and re.match(r"^[-*] ", lines[i]):
                text = _inline(_escape(lines[i][2:].strip()), styles)
                flowables.append(Paragraph(f"•  {text}", styles["bullet"]))
                i += 1
            continue

        # Numbered list (e.g. "1. ")
        if re.match(r"^\d+\. ", line):
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                m    = re.match(r"^(\d+)\. (.+)", lines[i])
                num  = m.group(1)
                text = _inline(_escape(m.group(2).strip()), styles)
                flowables.append(Paragraph(
                    f'<font color="#8d6e63"><b>{num}.</b></font>  {text}',
                    styles["bullet"],
                ))
                i += 1
            continue

        # Indented list (2+ spaces + -)
        if re.match(r"^  [-*] ", line):
            while i < len(lines) and re.match(r"^  [-*] ", lines[i]):
                text = _inline(_escape(lines[i][4:].strip()), styles)
                flowables.append(Paragraph(f"    –  {text}", styles["body_small"]))
                i += 1
            continue

        # **bold line** (key insight, pattern, etc.)
        if line.strip().startswith("**") and line.strip().endswith("**"):
            text = _inline(_escape(line.strip()), styles)
            flowables.append(Paragraph(text, styles["bold"]))
            i += 1
            continue

        # Metadata lines (starts with **)
        if line.strip().startswith("**"):
            text = _inline(_escape(line.strip()), styles)
            flowables.append(Paragraph(text, styles["body"]))
            i += 1
            continue

        # Italic metadata (*text*)
        if line.strip().startswith("*") and line.strip().endswith("*"):
            text = line.strip().strip("*")
            flowables.append(Paragraph(_escape(text), styles["meta"]))
            i += 1
            continue

        # Empty line → small spacer
        if not line.strip():
            flowables.append(Spacer(1, 2 * mm))
            i += 1
            continue

        # Default paragraph
        text = _inline(_escape(line.strip()), styles)
        if text:
            flowables.append(Paragraph(text, styles["body"]))
        i += 1

    return flowables


# ── Cover page ────────────────────────────────────────────────────────────────

def cover_page(report_date: str, styles, shop_stats_line: str = "") -> list:
    items = []
    items.append(Spacer(1, 30 * mm))

    # Big title block
    items.append(Paragraph("ETSY TREND REPORT", ParagraphStyle(
        "cover_title", fontSize=32, textColor=CHOCOLATE,
        fontName="Helvetica-Bold", alignment=TA_CENTER, leading=38,
    )))
    items.append(Spacer(1, 4 * mm))
    items.append(Paragraph("Switzertemplates", ParagraphStyle(
        "cover_sub", fontSize=16, textColor=SAND,
        fontName="Helvetica", alignment=TA_CENTER, leading=20,
    )))
    items.append(Spacer(1, 8 * mm))

    # Decorative rule
    items.append(HRFlowable(
        width="60%", thickness=2, color=TAUPE,
        spaceAfter=8, hAlign="CENTER",
    ))

    items.append(Paragraph(f"Generated {report_date}", ParagraphStyle(
        "cover_date", fontSize=11, textColor=TAUPE,
        fontName="Helvetica", alignment=TA_CENTER,
    )))
    items.append(Spacer(1, 6 * mm))

    if shop_stats_line:
        items.append(Paragraph(shop_stats_line, ParagraphStyle(
            "cover_stats", fontSize=10, textColor=CHARCOAL,
            fontName="Helvetica", alignment=TA_CENTER, leading=16,
        )))

    items.append(Spacer(1, 16 * mm))

    # Section index
    sections = [
        "1.  Shop Health Overview",
        "2.  Your Top-Earning Listings",
        "3.  Listings Wasting Traffic",
        "4.  Underperforming Active Listings",
        "5.  Top Trending Keywords",
        "6.  Product Gap Opportunities",
        "7.  Competitor Market Intelligence",
        "7b. Structural Product Opportunities",
        "8.  Action Plan: Getting to 30 Sales/Day",
    ]
    toc_style = ParagraphStyle(
        "toc", fontSize=9.5, textColor=CHARCOAL,
        fontName="Helvetica", leading=18, leftIndent=60,
    )
    for s in sections:
        items.append(Paragraph(s, toc_style))

    return items


# ── Main export function ───────────────────────────────────────────────────────

def export_pdf(md_path: Path = None) -> str:
    # Find the report
    if md_path is None:
        candidates = sorted(OUTPUT_DIR.glob("etsy-trend-report-*.md"), reverse=True)
        if not candidates:
            raise FileNotFoundError(f"No report found in {OUTPUT_DIR}")
        md_path = candidates[0]

    md_text     = md_path.read_text(encoding="utf-8")
    report_date = md_path.stem.replace("etsy-trend-report-", "")
    pdf_path    = md_path.with_suffix(".pdf")

    styles = build_styles()
    doc    = BrandedDoc(str(pdf_path), report_date,
                        leftMargin=MARGIN, rightMargin=MARGIN,
                        topMargin=MARGIN + 14 * mm, bottomMargin=MARGIN + 12 * mm)

    # Extract a summary line for the cover from the markdown
    sales_match = re.search(r"Est\. sales per day.*?\*\*([\d.]+)\*\*", md_text)
    rev_match   = re.search(r"Est\. monthly revenue.*?\$([\d,]+)", md_text)
    stats_line  = ""
    if sales_match and rev_match:
        stats_line = (
            f"Current pace: {sales_match.group(1)} sales/day  •  "
            f"${rev_match.group(1)}/month estimated revenue  •  Target: 30 sales/day"
        )

    story = []

    # Cover
    story += cover_page(report_date, styles, stats_line)

    # Page break after cover (add enough spacers to push to next page)
    from reportlab.platypus import PageBreak
    story.append(PageBreak())

    # Report body
    story += parse_markdown(md_text, styles)

    doc.build(story)
    return str(pdf_path)


if __name__ == "__main__":
    md_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print("\n Generating PDF report...")
    try:
        out = export_pdf(md_arg)
        print(f" Saved: {out}\n")
    except Exception as e:
        import traceback
        print(f" Error: {e}")
        traceback.print_exc()
