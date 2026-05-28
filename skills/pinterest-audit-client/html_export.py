"""
html_export.py — Converts audit markdown to styled HTML.
Design matches pinterest.switzertemplates.com/onboarding dashboard.
"""

from __future__ import annotations
import re
from pathlib import Path


CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #faf7f3;
  --surface: #fff;
  --surface2: #f0ebe2;
  --border: #e4dbd0;
  --border2: #d6ccc0;
  --text: #2b2520;
  --text2: #7a6458;
  --text3: #c9b8a8;
  --accent: #b09478;
  --gold: #c9a87c;
  --dark-banner: #2b2520;
  --serif: 'Instrument Serif', Georgia, serif;
  --sans: 'DM Sans', -apple-system, sans-serif;
  --radius: 10px;
  --radius-sm: 6px;
}
body {
  font-family: var(--sans);
  font-weight: 300;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  font-size: 14px;
  line-height: 1.6;
}
.wrapper {
  max-width: 900px;
  margin: 0 auto;
  padding: 2rem 1.25rem 5rem;
}
/* body has no top padding — header is full-width above wrapper */
body > .wrapper { padding-top: 2rem; }

/* ── Header (full-width, matches onboarding page exactly) ───────── */
.header {
  text-align: center;
  padding: 3.5rem 1.5rem 2rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 0;
  background: var(--bg);
}
.header-label {
  font-size: 11px;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: var(--text2);
  margin: 0 auto 14px;
  font-family: var(--sans);
  font-weight: 300;
  text-align: center;
  max-width: none;
}
.header h1 {
  font-family: var(--serif);
  font-size: clamp(28px, 5vw, 42px);
  font-weight: normal;
  color: var(--text);
  line-height: 1.2;
  margin-bottom: 12px;
  text-align: center;
}
.header-date {
  font-size: 13px;
  color: var(--text3);
  font-family: var(--sans);
  font-weight: 300;
  text-align: center;
  max-width: none;
  margin: 0 auto;
}

/* ── Cards ──────────────────────────────────────────────────────── */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem 1.5rem;
  margin-bottom: 1rem;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.card-title {
  font-family: var(--serif);
  font-size: 24px;
  font-weight: normal;
  color: var(--text);
}
.section-num {
  font-size: 10px;
  color: #fff;
  letter-spacing: .08em;
  background: #5c3d2e;
  padding: 3px 10px;
  border-radius: 20px;
  font-weight: 400;
  white-space: nowrap;
}

/* ── Stat grid ──────────────────────────────────────────────────── */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin: 1rem 0 0.5rem;
}
.stat-card {
  background: var(--surface2);
  border-radius: var(--radius-sm);
  padding: 14px 12px;
}
.stat-label {
  font-size: 12px;
  color: var(--text);
  letter-spacing: 0;
  text-transform: none;
  margin-top: 6px;
  font-weight: 300;
  line-height: 1.4;
}
.stat-val {
  font-family: var(--serif);
  font-size: 32px;
  color: var(--text);
  margin-bottom: 0;
  line-height: 1.1;
}
.stat-sub {
  font-size: 11px;
  color: var(--text3);
  line-height: 1.4;
}

/* ── Keyword pills ──────────────────────────────────────────────── */
.pill-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 4px 0;
}
.pill {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 5px 14px;
  font-size: 13px;
  color: var(--text2);
  white-space: nowrap;
  font-weight: 400;
}

/* ── Tables ─────────────────────────────────────────────────────── */
.table-wrap { overflow-x: auto; margin: 0.75rem 0; }
table { width: 100%; border-collapse: collapse; }
th {
  font-size: 10px;
  font-weight: 500;
  color: var(--text3);
  letter-spacing: .1em;
  text-transform: uppercase;
  padding: 0 10px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border2);
  white-space: nowrap;
  font-family: var(--sans);
}
td {
  padding: 10px;
  font-size: 15px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
  color: var(--text);
  line-height: 1.5;
  font-weight: 300;
}
tr:last-child td { border-bottom: none; }
tbody tr:hover { background: var(--surface2); }

/* ── Sub-section (h3) ───────────────────────────────────────────── */
.subsection {
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--border);
}
.card-header + .subsection,
.card-header + .strategy-step { border-top: none; }
.subsection-title {
  font-family: var(--serif);
  font-size: 19px;
  font-weight: normal;
  color: var(--text);
  margin-bottom: 0.75rem;
}

/* ── H4 / bold labels ───────────────────────────────────────────── */
.field-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text2);
  letter-spacing: .1em;
  text-transform: uppercase;
  margin: 1rem 0 4px;
  font-family: var(--sans);
}

/* ── Body text ──────────────────────────────────────────────────── */
p {
  font-size: 15px;
  color: var(--text2);
  line-height: 1.65;
  margin-bottom: 0.75rem;
  max-width: 720px;
  font-weight: 300;
}
p:last-child { margin-bottom: 0; }
ul, ol { padding-left: 20px; margin-bottom: 0.75rem; }
li {
  font-size: 15px;
  color: var(--text2);
  line-height: 1.6;
  margin-bottom: 4px;
  font-weight: 300;
}
a { color: var(--accent); }
strong { color: var(--text); font-weight: 500; }
em { color: var(--text2); }

/* ── Italic meta / source note ──────────────────────────────────── */
.meta-note {
  font-size: 11px;
  color: var(--text3);
  font-style: italic;
  margin-bottom: 0.75rem;
}

/* ── Trend cards (Design Style Trends) ─────────────────────────── */
.trend-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px;
  margin: 0.75rem 0;
}
.trend-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 16px 14px;
}
.trend-card-num {
  font-size: 10px;
  color: var(--text3);
  letter-spacing: .12em;
  text-transform: uppercase;
  font-family: var(--sans);
  font-weight: 400;
  margin-bottom: 6px;
}
.trend-card-name {
  font-family: var(--serif);
  font-size: 16px;
  font-weight: normal;
  color: var(--text);
  margin-bottom: 8px;
  line-height: 1.3;
}
.trend-card-desc {
  font-size: 12px;
  color: var(--text2);
  line-height: 1.6;
  font-weight: 300;
}
.trend-card-desc em {
  color: var(--accent);
  font-style: italic;
  display: block;
  margin-top: 6px;
}

/* ── Strategy card (section 7) ───────────────────────────────────── */
.strategy-card {
  border: 1px solid var(--border2);
  overflow: hidden;
  padding: 0;
}
.strategy-card .card-header {
  background: var(--dark-banner);
  margin: 0;
  padding: 1.5rem 1.75rem 1.25rem;
  border-bottom: none;
  border-radius: 0;
  flex-wrap: wrap;
  align-items: flex-start;
}
.strategy-card .card-header::after {
  flex: 0 0 100%;
  content: '';
  display: block;
  width: 36px;
  height: 3px;
  background: var(--gold);
  border-radius: 2px;
  margin-top: 10px;
  opacity: 0.8;
}
.strategy-card .card-title { color: #f8f5f2; font-size: 24px; }
.strategy-card .section-num { background: var(--gold); color: #2b2520; }

/* ── Personal recommendations ────────────────────────────────────── */
.rec-list { display: flex; flex-direction: column; gap: 6px; margin-top: 0.5rem; }
.rec-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 15px;
  color: var(--text2);
  line-height: 1.6;
  font-weight: 300;
  font-style: italic;
}
.rec-pin { flex-shrink: 0; font-size: 16px; line-height: 1.45; }
.strategy-step {
  display: grid;
  grid-template-columns: 26px 1fr;
  gap: 1rem;
  padding: 1.25rem 1.75rem;
  border-top: 1px solid var(--border);
  align-items: start;
}
.strategy-step-num {
  font-size: 15px;
  color: var(--accent);
  line-height: 1.3;
  padding-top: 1px;
  text-align: center;
}
.strategy-step-title {
  font-family: var(--serif);
  font-size: 19px;
  color: var(--text);
  font-weight: normal;
  margin-bottom: 0.6rem;
}
.strategy-step-body { font-size: 15px; color: var(--text2); line-height: 1.7; font-weight: 300; }
.strategy-step-body p { margin-bottom: 0.5rem; max-width: none; color: var(--text2); font-size: 15px; font-weight: 300; }
.strategy-step-body p:last-child { margin-bottom: 0; }
.strategy-step-body ul, .strategy-step-body ol { padding-left: 18px; margin: 0.25rem 0; }
.strategy-step-body li { color: var(--text2); font-size: 15px; line-height: 1.6; margin-bottom: 3px; font-weight: 300; }
.strategy-step-body strong { color: var(--text); font-weight: 500; }
.strategy-step-body .table-wrap { margin: 0.5rem 0; }

/* ── Colour swatch ──────────────────────────────────────────────── */
.swatch {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  border: 1px solid var(--border2);
  vertical-align: middle;
  margin-right: 5px;
}

/* ── HR ─────────────────────────────────────────────────────────── */
hr { display: none; }

/* ── CSV download buttons ────────────────────────────────────────── */
.csv-download-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 0.75rem;
}
.csv-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  background: #5c3d2e;
  border: 1px solid #5c3d2e;
  border-radius: 6px;
  padding: 7px 14px;
  font-size: 12px;
  font-family: var(--sans);
  font-weight: 400;
  color: #fff;
  text-decoration: none;
  letter-spacing: .01em;
  transition: background 0.12s, border-color 0.12s;
}
.csv-btn:hover { background: #4a3025; border-color: #4a3025; color: #fff; }
.csv-btn svg { flex-shrink: 0; stroke: #fff; }

/* ── Actionable Spreadsheet section ─────────────────────────────── */
.spreadsheet-card {
  border: 1.5px solid #34a853;
  background: #fff;
  text-align: center;
  padding: 2.5rem 1.5rem 2rem;
  margin-top: 1.5rem;
}
.canva-card { border-color: #29ABE2; margin-top: 0.75rem; }
.canva-btn {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  background: #29ABE2;
  color: #fff;
  font-family: var(--sans);
  font-size: 14px;
  font-weight: 500;
  padding: 14px 28px;
  border-radius: 8px;
  text-decoration: none;
  letter-spacing: .01em;
  transition: background 0.15s, box-shadow 0.15s;
  box-shadow: 0 2px 8px rgba(41,171,226,0.3);
}
.canva-btn:hover { background: #1e96cf; box-shadow: 0 4px 14px rgba(41,171,226,0.4); }
.canva-btn svg { flex-shrink: 0; }
.spreadsheet-card .card-header { display: none; }
.spreadsheet-eyebrow {
  font-size: 11px;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: var(--text2);
  font-weight: 300;
  margin-bottom: 14px;
}
.spreadsheet-title {
  font-family: var(--serif);
  font-size: clamp(22px, 4vw, 32px);
  font-weight: normal;
  color: var(--text);
  margin-bottom: 10px;
  line-height: 1.2;
}
.spreadsheet-desc {
  font-size: 13px;
  color: var(--text2);
  font-weight: 300;
  max-width: 480px;
  margin: 0 auto 2rem;
  line-height: 1.65;
}
.sheets-btn {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  background: #34a853;
  color: #fff;
  font-family: var(--sans);
  font-size: 14px;
  font-weight: 500;
  padding: 14px 28px;
  border-radius: 8px;
  text-decoration: none;
  letter-spacing: .01em;
  transition: background 0.15s, box-shadow 0.15s;
  box-shadow: 0 2px 8px rgba(52,168,83,0.25);
}
.sheets-btn:hover { background: #2d9248; box-shadow: 0 4px 14px rgba(52,168,83,0.35); }
.sheets-btn svg { flex-shrink: 0; }
.spreadsheet-note {
  font-size: 13px;
  color: var(--text3);
  margin-top: 1rem;
  font-weight: 300;
  max-width: none;
}
"""


# ── Sentence case ──────────────────────────────────────────────────────────────

_PROPER_NOUNS = {"pinterest", "google", "reddit", "quora", "wix", "canva", "instagram", "etsy", "switzertemplates"}

def _sentence_case(text: str) -> str:
    """Capitalize only the first word; preserve known proper nouns."""
    if not text:
        return text
    words = text.split()
    result = []
    for i, word in enumerate(words):
        clean = re.sub(r"[^a-zA-Z]", "", word).lower()
        if clean in _PROPER_NOUNS:
            result.append(word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper())
        elif i == 0:
            result.append(word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper())
        else:
            result.append(word.lower())
    return " ".join(result)


# ── Inline markdown ────────────────────────────────────────────────────────────

def _inline(text: str) -> str:
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
    return text


# ── Table parser ───────────────────────────────────────────────────────────────

def _parse_table(lines: list[str]) -> str:
    rows = [l.strip() for l in lines if l.strip()]
    if len(rows) < 2:
        return ""

    headers = [c.strip() for c in rows[0].split("|") if c.strip()]
    html = ['<div class="table-wrap"><table><thead><tr>']
    for h in headers:
        html.append(f"<th>{h}</th>")
    html.append("</tr></thead><tbody>")

    for row_line in rows[2:]:
        cells = [c.strip() for c in row_line.split("|")]
        cells = [c for c in cells if c or row_line.count("|") > 1]
        cells = [c for c in cells if c]
        if not cells:
            continue

        # Detect colour swatch from hex code in a cell
        row_html = ["<tr>"]
        for i, cell in enumerate(cells):
            cell_html = _inline(cell)
            # If this cell looks like a hex colour, prepend a swatch
            hex_m = re.search(r'#([0-9A-Fa-f]{3,6})\b', cell)
            if hex_m and i > 0:
                hex_val = hex_m.group(0)
                cell_html = f'<span class="swatch" style="background:{hex_val};"></span>{cell_html}'
            row_html.append(f"<td>{cell_html}</td>")
        row_html.append("</tr>")
        html.append("".join(row_html))

    html.append("</tbody></table></div>")
    return "\n".join(html)


# ── Stat card HTML passthrough ─────────────────────────────────────────────────

def _convert_stat_card_line(line: str) -> str:
    """
    Convert report_builder stat card HTML to dashboard-style HTML.
    Input:  <div class="stat-card"><span class="stat-value">875M</span><span class="stat-label">Monthly active users</span></div>
    Output: <div class="stat-card"><div class="stat-val">875M</div><div class="stat-label">MONTHLY ACTIVE USERS</div></div>
    """
    val_m = re.search(r'class="stat-value">([^<]+)<', line)
    lbl_m = re.search(r'class="stat-label">([^<]+)<', line)
    if val_m and lbl_m:
        val = val_m.group(1)
        lbl = lbl_m.group(1)
        return (
            f'<div class="stat-card">'
            f'<div class="stat-val">{val}</div>'
            f'<div class="stat-label">{lbl}</div>'
            f'</div>'
        )
    return line


# ── Main converter ─────────────────────────────────────────────────────────────

_SHEETS_ICON = """<svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="4" y="1" width="16" height="22" rx="2" fill="white" opacity="0.15"/>
  <path d="M14 1H4C2.9 1 2 1.9 2 3V21C2 22.1 2.9 23 4 23H20C21.1 23 22 22.1 22 21V9L14 1Z" fill="white"/>
  <path d="M14 1V9H22L14 1Z" fill="rgba(255,255,255,0.6)"/>
  <rect x="6" y="13" width="12" height="1.5" rx="0.75" fill="#34a853"/>
  <rect x="6" y="16" width="8" height="1.5" rx="0.75" fill="#34a853"/>
  <rect x="6" y="10" width="12" height="1.5" rx="0.75" fill="#34a853"/>
</svg>"""

_CANVA_ICON = """<svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="12" cy="12" r="10" fill="white" opacity="0.9"/>
  <path d="M15.5 8.5C15.5 8.5 14.5 7 12 7C9 7 7 9.5 7 12C7 14.5 9 17 12 17C14.5 17 15.5 15.5 15.5 15.5" stroke="rgba(123,97,255,0.9)" stroke-width="2" stroke-linecap="round"/>
  <circle cx="12" cy="12" r="2.5" fill="rgba(123,97,255,0.9)"/>
</svg>"""


def md_to_html(md: str, title: str, run_date: str, products: str, client_name: str = "", spreadsheet_url: str = "") -> str:
    lines = md.splitlines()
    parts = []

    # header is rendered separately — skip it here

    section_count = 0
    in_card = False
    card_buf = []      # buffered HTML inside current card
    in_stat_grid = False
    stat_grid_buf = []
    keyword_section = False
    keyword_items = []

    def flush_keywords():
        nonlocal keyword_items
        if keyword_items:
            pills = "".join(f'<span class="pill">{_inline(k)}</span>' for k in keyword_items)
            card_buf.append(f'<div class="pill-grid">{pills}</div>')
            keyword_items = []

    current_card_class = ["card"]
    strategy_step_count = [0]

    def open_card(heading: str):
        nonlocal in_card, section_count, keyword_section
        close_card()
        section_count += 1
        num = f"{section_count:02d}"
        keyword_section = any(kw in heading.lower() for kw in ["trending keywords", "keywords in your niche", "keyword groups"])
        is_strategy = "strategy" in heading.lower() and "growth" in heading.lower()
        current_card_class[0] = "card strategy-card" if is_strategy else "card"
        strategy_step_count[0] = 0
        card_buf.clear()
        in_card = True
        card_buf.append(
            f'<div class="card-header">'
            f'<div class="card-title">{_sentence_case(heading)}</div>'
            f'<span class="section-num">{num}</span>'
            f'</div>'
        )

    def close_card():
        nonlocal in_card
        if in_card:
            flush_keywords()
            parts.append(f'<div class="{current_card_class[0]}">')
            parts.extend(card_buf)
            parts.append('</div>')
            in_card = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # ── Stat grid ────────────────────────────────────────────────
        if '<div class="stat-grid">' in line:
            in_stat_grid = True
            stat_grid_buf = ['<div class="stat-grid">']
            i += 1
            continue

        if in_stat_grid:
            if '</div>' in line and 'stat-card' not in line:
                stat_grid_buf.append('</div>')
                card_buf.extend(stat_grid_buf)
                in_stat_grid = False
            elif 'stat-card' in line:
                stat_grid_buf.append(_convert_stat_card_line(line.strip()))
            i += 1
            continue

        # ── Raw HTML div passthrough (non-stat-grid) ─────────────────
        if line.strip().startswith('<div') or line.strip().startswith('</div'):
            target = card_buf if in_card else parts
            target.append(line)
            i += 1
            continue

        # ── Skip H1 (in banner) ──────────────────────────────────────
        if line.startswith("# ") and not line.startswith("## "):
            i += 1
            continue

        # ── Skip report metadata lines ───────────────────────────────
        if line.startswith("**Generated:**") or line.startswith("**Products/Services:**"):
            i += 1
            continue

        # ── H2 → new card ────────────────────────────────────────────
        if line.startswith("## "):
            heading = line[3:].strip()
            open_card(heading)
            i += 1
            continue

        # ── H3 → subsection within card ─────────────────────────────
        if line.startswith("### "):
            flush_keywords()
            raw_title = line[4:].strip()
            is_trend_section = "design" in raw_title.lower() and "trend" in raw_title.lower()
            is_strategy_card = "strategy-card" in current_card_class[0]
            display_title = _sentence_case(raw_title)
            i += 1
            # Collect content until next ###, ## or end
            subsection_content = []
            while i < len(lines):
                peek = lines[i]
                if peek.startswith("## ") or peek.startswith("### "):
                    break
                subsection_content.append(peek)
                i += 1

            def _render_content_block(content_lines: list, buf: list) -> None:
                """Shared content renderer for normal subsections and strategy steps."""
                j = 0
                while j < len(content_lines):
                    sl = content_lines[j]
                    if sl.strip() in ("---", "***", "___"):
                        j += 1
                    elif sl.strip().startswith("<div") or sl.strip().startswith("</div"):
                        buf.append(sl)
                        j += 1
                    elif sl.startswith("|") and j + 1 < len(content_lines) and content_lines[j + 1].startswith("|---"):
                        tbl_lines = []
                        while j < len(content_lines) and content_lines[j].startswith("|"):
                            tbl_lines.append(content_lines[j])
                            j += 1
                        buf.append(_parse_table(tbl_lines))
                    elif re.match(r"^[-*] ", sl):
                        items = []
                        while j < len(content_lines) and re.match(r"^[-*] ", content_lines[j]):
                            items.append(f"<li>{_inline(content_lines[j][2:].strip())}</li>")
                            j += 1
                        buf.append(f"<ul>{''.join(items)}</ul>")
                    elif re.match(r"^\d+\. ", sl):
                        items = []
                        while j < len(content_lines) and re.match(r"^\d+\. ", content_lines[j]):
                            text_ = re.sub(r"^\d+\. ", "", content_lines[j])
                            items.append(f"<li>{_inline(text_.strip())}</li>")
                            j += 1
                        buf.append(f"<ol>{''.join(items)}</ol>")
                    elif re.match(r'^\*\*[^*]+\*\*$', sl.strip()):
                        buf.append(f'<div class="field-label">{sl.strip()[2:-2]}</div>')
                        j += 1
                    elif re.match(r"^\*[^*].+[^*]\*$", sl.strip()):
                        buf.append(f'<p class="meta-note">{sl.strip().strip("*")}</p>')
                        j += 1
                    elif not sl.strip():
                        j += 1
                    else:
                        buf.append(f"<p>{_inline(sl.strip())}</p>")
                        j += 1

            if is_trend_section:
                # Render as visual trend cards grid
                card_buf.append(f'<div class="subsection"><div class="subsection-title">{_inline(display_title)}</div>')
                trend_cards = []
                j = 0
                while j < len(subsection_content):
                    sl = subsection_content[j]
                    bold_match = re.match(r'^\*\*([^*]+)\*\*\s*$', sl.strip())
                    if bold_match:
                        name = bold_match.group(1)
                        j += 1
                        desc_lines = []
                        while j < len(subsection_content):
                            nxt = subsection_content[j].strip()
                            if not nxt:
                                j += 1
                                if desc_lines:
                                    break
                                continue
                            if re.match(r'^\*\*[^*]+\*\*\s*$', nxt):
                                break
                            desc_lines.append(nxt)
                            j += 1
                        trend_cards.append((name, " ".join(desc_lines)))
                    else:
                        j += 1
                if trend_cards:
                    card_buf.append('<div class="trend-grid">')
                    for idx, (name, desc) in enumerate(trend_cards, 1):
                        card_buf.append(
                            f'<div class="trend-card">'
                            f'<div class="trend-card-num">Trend {idx:02d}</div>'
                            f'<div class="trend-card-name">{name}</div>'
                            f'<div class="trend-card-desc">{_inline(desc)}</div>'
                            f'</div>'
                        )
                    card_buf.append('</div>')
                card_buf.append('</div>')

            elif is_strategy_card:
                # Render as a strategy step with checkmark
                body_buf: list = []
                _render_content_block(subsection_content, body_buf)
                card_buf.append(
                    f'<div class="strategy-step">'
                    f'<div class="strategy-step-num">✓</div>'
                    f'<div class="strategy-step-content">'
                    f'<div class="strategy-step-title">{display_title}</div>'
                    f'<div class="strategy-step-body">{"".join(body_buf)}</div>'
                    f'</div>'
                    f'</div>'
                )

            else:
                # Normal subsection
                card_buf.append(f'<div class="subsection"><div class="subsection-title">{_inline(display_title)}</div>')
                _render_content_block(subsection_content, card_buf)
                card_buf.append('</div>')

            continue

        # ── H4 ───────────────────────────────────────────────────────
        if line.startswith("#### "):
            text = _inline(line[5:].strip())
            card_buf.append(f'<div class="field-label">{text}</div>')
            i += 1
            continue

        # ── HR ───────────────────────────────────────────────────────
        if line.strip() in ("---", "***", "___"):
            i += 1
            continue

        # ── Table ────────────────────────────────────────────────────
        if line.startswith("|") and i + 1 < len(lines) and lines[i + 1].startswith("|---"):
            tbl_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                tbl_lines.append(lines[i])
                i += 1
            target = card_buf if in_card else parts
            target.append(_parse_table(tbl_lines))
            continue

        # ── Keyword pills (numbered list in keyword section) ─────────
        if keyword_section and re.match(r"^\d+\. ", line):
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                m = re.match(r"^\d+\. (.+)", lines[i])
                if m:
                    keyword_items.append(m.group(1).strip())
                i += 1
            continue

        # ── Numbered list (non-keyword) ──────────────────────────────
        if re.match(r"^\d+\. ", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                text = re.sub(r"^\d+\. ", "", lines[i])
                items.append(f"<li>{_inline(text.strip())}</li>")
                i += 1
            target = card_buf if in_card else parts
            target.append(f"<ol>{''.join(items)}</ol>")
            continue

        # ── Bullet list ──────────────────────────────────────────────
        if re.match(r"^[-*] ", line):
            items = []
            while i < len(lines) and re.match(r"^[-*] ", lines[i]):
                items.append(f"<li>{_inline(lines[i][2:].strip())}</li>")
                i += 1
            target = card_buf if in_card else parts
            target.append(f"<ul>{''.join(items)}</ul>")
            continue

        # ── Bold-only line → field label ─────────────────────────────
        if re.match(r'^\*\*[^*]+\*\*$', line.strip()):
            text = line.strip()[2:-2]
            target = card_buf if in_card else parts
            target.append(f'<div class="field-label">{text}</div>')
            i += 1
            continue

        # ── Italic-only → meta note ──────────────────────────────────
        if re.match(r"^\*[^*].+\*$", line.strip()):
            text = line.strip().strip("*")
            target = card_buf if in_card else parts
            target.append(f'<p class="meta-note">{text}</p>')
            i += 1
            continue

        # ── Empty line ───────────────────────────────────────────────
        if not line.strip():
            i += 1
            continue

        # ── Default paragraph ────────────────────────────────────────
        if line.strip() and line.strip() not in ("---", "***", "___"):
            target = card_buf if in_card else parts
            target.append(f"<p>{_inline(line.strip())}</p>")

        i += 1

    close_card()

    if spreadsheet_url:
        parts.append(f"""<div class="card spreadsheet-card">
  <div class="spreadsheet-title">Your actionable GoogleSheet</div>
  <p class="spreadsheet-desc"><strong>Make sure you make your own copy. Go to File → Make a copy</strong></p>
  <a href="{spreadsheet_url}" target="_blank" class="sheets-btn">
    {_SHEETS_ICON}
    Open the file
  </a>
</div>
<div class="card spreadsheet-card canva-card">
  <div class="spreadsheet-title">50 pin templates for Canva</div>
  <p class="spreadsheet-desc">Ready-to-edit pin templates built for Pinterest. Customise with your photos and texts.</p>
  <a href="https://canva.link/5mazrd595nv86lj" target="_blank" class="canva-btn">
    {_CANVA_ICON}
    50 pin templates for Canva
  </a>
</div>""")

    h1_text = f"{client_name} Audit" if client_name else title
    header = f"""<div class="header">
  <p class="header-label">Switzertemplates Pinterest Services</p>
  <h1>{h1_text}</h1>
  <p class="header-date">{run_date}</p>
</div>"""

    body = "\n".join(parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>Pinterest audit — {title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet" />
<style>
{CSS}
</style>
</head>
<body>
{header}
<div class="wrapper">
{body}
</div>
</body>
</html>"""


def save_html(md_path: str, client_name: str = "", spreadsheet_url: str = "") -> str:
    md_path = Path(md_path)
    content = md_path.read_text(encoding="utf-8")

    title_match = re.search(r"^# Pinterest Niche Audit — (.+)$", content, re.MULTILINE)
    title = title_match.group(1) if title_match else "Pinterest Audit"

    date_match = re.search(r"\*\*Generated:\*\* (\S+)", content)
    run_date = date_match.group(1) if date_match else ""

    products_match = re.search(r"\*\*Products/Services:\*\* (.+)$", content, re.MULTILINE)
    products = products_match.group(1).strip() if products_match else ""

    html = md_to_html(content, title, run_date, products, client_name=client_name, spreadsheet_url=spreadsheet_url)

    html_path = md_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    return str(html_path)
