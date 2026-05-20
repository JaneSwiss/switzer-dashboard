"""
Converts a competitor analysis report dict into a styled HTML file.
Called automatically by run_analyze() after a full analysis run.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from collections import Counter


# ── Brand palette ─────────────────────────────────────────────────────────

CSS = """
:root {
  --cream:      #f8f5f2;
  --taupe:      #bbb0aa;
  --sand:       #a5988e;
  --brown:      #8d6e63;
  --charcoal:   #383838;
  --white:      #ffffff;
  --badge-bs:   #c17c3a;
  --badge-pn:   #5a8a5e;
  --badge-bg-bs:#fdf0e0;
  --badge-bg-pn:#e6f2e7;
  --row-alt:    #faf8f6;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--cream);
  color: var(--charcoal);
  font-size: 14px;
  line-height: 1.6;
}

.page-header {
  background: var(--charcoal);
  color: var(--cream);
  padding: 32px 40px 24px;
}
.page-header h1 { font-size: 1.5rem; font-weight: 600; margin-bottom: 4px; }
.page-header .meta { color: var(--taupe); font-size: 0.85rem; }

.stats-bar {
  display: flex;
  gap: 16px;
  padding: 20px 40px;
  background: var(--white);
  border-bottom: 1px solid var(--taupe);
  flex-wrap: wrap;
}
.stat-card {
  background: var(--cream);
  border: 1px solid var(--taupe);
  border-radius: 8px;
  padding: 12px 20px;
  min-width: 120px;
  text-align: center;
}
.stat-card .num { font-size: 1.6rem; font-weight: 700; color: var(--brown); }
.stat-card .label { font-size: 0.75rem; color: var(--sand); text-transform: uppercase;
                    letter-spacing: 0.05em; margin-top: 2px; }

.container { max-width: 1200px; margin: 0 auto; padding: 32px 40px; }

h2 {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--brown);
  border-left: 4px solid var(--brown);
  padding-left: 12px;
  margin: 36px 0 16px;
}
h3 { font-size: 0.95rem; font-weight: 600; color: var(--charcoal); margin-bottom: 6px; }

/* Tables */
.table-wrap { overflow-x: auto; margin-bottom: 24px; }
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--white);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.07);
}
thead th {
  background: var(--charcoal);
  color: var(--cream);
  padding: 10px 14px;
  text-align: left;
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  cursor: pointer;
  white-space: nowrap;
  user-select: none;
}
thead th:hover { background: var(--brown); }
thead th.sorted-asc::after  { content: " ▲"; font-size: 0.7rem; }
thead th.sorted-desc::after { content: " ▼"; font-size: 0.7rem; }
tbody td {
  padding: 10px 14px;
  border-bottom: 1px solid #ede8e4;
  vertical-align: top;
}
tbody tr:last-child td { border-bottom: none; }
tbody tr:nth-child(even) td { background: var(--row-alt); }
tbody tr:hover td { background: #f0ebe6; }

/* Badges */
.badge {
  display: inline-block;
  padding: 2px 9px;
  border-radius: 20px;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  white-space: nowrap;
}
.badge-bs { background: var(--badge-bg-bs); color: var(--badge-bs); border: 1px solid var(--badge-bs); }
.badge-pn { background: var(--badge-bg-pn); color: var(--badge-pn); border: 1px solid var(--badge-pn); }
.badge-none { color: #ccc; font-size: 0.7rem; }

/* Listing cards */
.listing-card {
  background: var(--white);
  border: 1px solid #e0d9d4;
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 12px;
}
.listing-card.has-badge { border-left: 4px solid var(--badge-bs); }
.listing-card.has-pn    { border-left: 4px solid var(--badge-pn); }
.listing-title { font-size: 0.95rem; font-weight: 600; margin-bottom: 6px; }
.listing-meta  { font-size: 0.82rem; color: var(--sand); display: flex; gap: 16px; flex-wrap: wrap; }
.listing-meta span strong { color: var(--charcoal); }
.listing-link  {
  display: inline-block;
  margin-top: 8px;
  font-size: 0.8rem;
  color: var(--brown);
  text-decoration: none;
  border-bottom: 1px solid var(--taupe);
}
.listing-link:hover { color: var(--charcoal); border-color: var(--charcoal); }

/* Bar chart */
.bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 5px; }
.bar-label { width: 200px; font-size: 0.8rem; color: var(--charcoal); text-align: right;
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-track { flex: 1; background: #ede8e4; border-radius: 4px; height: 18px; }
.bar-fill  { background: var(--brown); border-radius: 4px; height: 18px;
             display: flex; align-items: center; justify-content: flex-end;
             padding-right: 6px; }
.bar-fill span { font-size: 0.7rem; color: var(--cream); font-weight: 600; white-space: nowrap; }
.bar-fill.bar-phrase { background: var(--sand); }

/* Nav */
.nav {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}
.nav a {
  padding: 5px 14px;
  border-radius: 20px;
  font-size: 0.8rem;
  text-decoration: none;
  background: var(--white);
  color: var(--brown);
  border: 1px solid var(--taupe);
}
.nav a:hover { background: var(--brown); color: var(--cream); }

/* Price chip */
.price { font-weight: 700; color: var(--brown); }

/* Keyword section grid */
.kw-section { margin-bottom: 8px; }

footer {
  text-align: center;
  padding: 24px;
  font-size: 0.78rem;
  color: var(--sand);
  border-top: 1px solid var(--taupe);
  margin-top: 48px;
}
"""

SORT_JS = """
function sortTable(table, col, asc) {
  const tbody = table.querySelector('tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  rows.sort((a, b) => {
    const av = a.cells[col].dataset.val || a.cells[col].textContent.trim();
    const bv = b.cells[col].dataset.val || b.cells[col].textContent.trim();
    const an = parseFloat(av.replace(/[^0-9.\-]/g, ''));
    const bn = parseFloat(bv.replace(/[^0-9.\-]/g, ''));
    if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
  });
  rows.forEach(r => tbody.appendChild(r));
  table.querySelectorAll('thead th').forEach((th, i) => {
    th.classList.remove('sorted-asc', 'sorted-desc');
    if (i === col) th.classList.add(asc ? 'sorted-asc' : 'sorted-desc');
  });
}
document.querySelectorAll('table.sortable').forEach(table => {
  table.querySelectorAll('thead th').forEach((th, i) => {
    let asc = true;
    th.addEventListener('click', () => { sortTable(table, i, asc); asc = !asc; });
  });
});
"""


# ── HTML builder ───────────────────────────────────────────────────────────

def _badge_html(listing):
    parts = []
    if listing.get("bestseller_badge"):
        parts.append('<span class="badge badge-bs">Bestseller</span>')
    if listing.get("popular_now_badge"):
        parts.append('<span class="badge badge-pn">Popular Now</span>')
    return " ".join(parts) if parts else ""


def _price_num(listing):
    m = re.search(r"[\d.]+", str(listing.get("price", "")).replace(",", ""))
    return float(m.group()) if m else 0.0


def _card_class(listing):
    if listing.get("bestseller_badge"):
        return "listing-card has-badge"
    if listing.get("popular_now_badge"):
        return "listing-card has-pn"
    return "listing-card"


def _listing_card(listing):
    badge_html = _badge_html(listing)
    title = listing.get("title", "Unknown")
    shop  = listing.get("shop", "Unknown")
    price = listing.get("price", "N/A")
    rev   = listing.get("review_count", "?")
    sales = listing.get("sales", "Unknown")
    url   = listing.get("url", "#")
    desc  = listing.get("description_preview", "")

    desc_html = (
        f'<p style="font-size:0.82rem;color:#666;margin-top:8px;">'
        f'{desc[:300]}{"…" if len(desc) > 300 else ""}</p>'
        if desc else ""
    )

    return f"""
<div class="{_card_class(listing)}">
  <div class="listing-title">{title} {badge_html}</div>
  <div class="listing-meta">
    <span><strong>Shop:</strong> {shop}</span>
    <span><strong>Price:</strong> <span class="price">${_price_num(listing):.2f}</span></span>
    <span><strong>Reviews:</strong> {rev}</span>
    <span><strong>Sales:</strong> {sales}</span>
  </div>
  {desc_html}
  <a class="listing-link" href="{url}" target="_blank" rel="noopener">
    Open on Etsy &rarr;
  </a>
</div>"""


def _bar_chart(items, max_val, css_class="bar-fill"):
    rows = []
    for label, count in items:
        pct = min(100, int(count / max_val * 100)) if max_val else 0
        rows.append(f"""
<div class="bar-row">
  <div class="bar-label" title="{label}">{label}</div>
  <div class="bar-track">
    <div class="{css_class}" style="width:{pct}%">
      <span>{count}</span>
    </div>
  </div>
</div>""")
    return "\n".join(rows)


def _summary_table(results_by_keyword):
    rows = []
    for kw, listings in results_by_keyword.items():
        n  = len(listings)
        bs = sum(1 for l in listings if l.get("bestseller_badge"))
        pn = sum(1 for l in listings if l.get("popular_now_badge"))
        prices = [_price_num(l) for l in listings if _price_num(l) > 0]
        avg = f"${sum(prices)/len(prices):.2f}" if prices else "N/A"
        lo  = f"${min(prices):.2f}" if prices else "N/A"
        hi  = f"${max(prices):.2f}" if prices else "N/A"
        bs_cell = f'<span class="badge badge-bs">{bs}</span>' if bs else "0"
        pn_cell = f'<span class="badge badge-pn">{pn}</span>' if pn else "0"
        kw_anchor = kw.replace(" ", "-").replace("(", "").replace(")", "")
        rows.append(f"""<tr>
  <td><a href="#{kw_anchor}" style="color:var(--brown);text-decoration:none;">{kw}</a></td>
  <td data-val="{n}">{n}</td>
  <td data-val="{bs}">{bs_cell}</td>
  <td data-val="{pn}">{pn_cell}</td>
  <td data-val="{sum(prices)/len(prices) if prices else 0}">{avg}</td>
  <td>{lo}</td>
  <td>{hi}</td>
</tr>""")

    return f"""
<div class="table-wrap">
<table class="sortable">
  <thead>
    <tr>
      <th>Keyword</th>
      <th>Listings</th>
      <th>Bestseller</th>
      <th>Popular Now</th>
      <th>Avg Price</th>
      <th>Min Price</th>
      <th>Max Price</th>
    </tr>
  </thead>
  <tbody>{"".join(rows)}</tbody>
</table>
</div>"""


def _listings_table(listings):
    rows = []
    for l in sorted(listings, key=_price_num, reverse=True):
        badge_html = _badge_html(l) or '<span class="badge-none">—</span>'
        url = l.get("url", "#")
        title = l.get("title", "")[:70]
        rows.append(f"""<tr>
  <td><a href="{url}" target="_blank" rel="noopener" style="color:var(--brown);">{title}</a></td>
  <td>{l.get('shop','')}</td>
  <td data-val="{_price_num(l)}" class="price">${_price_num(l):.2f}</td>
  <td data-val="{str(l.get('review_count','0')).replace(',','')}">{l.get('review_count','?')}</td>
  <td data-val="{str(l.get('sales','0')).replace(',','') if l.get('sales','Unknown') != 'Unknown' else '0'}">{l.get('sales','Unknown')}</td>
  <td>{badge_html}</td>
</tr>""")

    return f"""
<div class="table-wrap">
<table class="sortable">
  <thead>
    <tr>
      <th>Title</th>
      <th>Shop</th>
      <th>Price</th>
      <th>Reviews</th>
      <th>Sales</th>
      <th>Badge</th>
    </tr>
  </thead>
  <tbody>{"".join(rows)}</tbody>
</table>
</div>"""


# ── Stop words for title keyword extraction ────────────────────────────────

_STOP_WORDS = {
    "a","an","and","are","as","at","be","but","by","for","from","has","have",
    "i","in","is","it","its","of","on","or","that","the","this","to","was",
    "with","your","you","my","our","their","will","can","get","all","new",
    "any","more","how","do","if","so","we","not","no","up","use","used",
    "make","made","one","two","set","full","easy","great","best","amp",
    "about","also","amp","www","http","https","com","co",
}


def _extract_keywords(listings):
    words, phrases = [], []
    for l in listings:
        title = l.get("title", "")
        clean = re.sub(r"[^a-z0-9 ]", " ", title.lower())
        tokens = [t for t in clean.split() if len(t) > 2 and t not in _STOP_WORDS]
        words.extend(tokens)
        for i in range(len(tokens) - 1):
            phrases.append(f"{tokens[i]} {tokens[i+1]}")
    return Counter(words), Counter(phrases)


# ── Main generator ─────────────────────────────────────────────────────────

def generate(results_by_keyword, out_path, expanded_keywords=None):
    """
    Build the full HTML report.

    results_by_keyword: dict {keyword: [listing_dict, ...]}
    out_path: Path object for the output .html file
    expanded_keywords: [(phrase, count), ...] optional
    """
    now = datetime.now().strftime("%d %b %Y %H:%M")
    all_listings = [l for ls in results_by_keyword.values() for l in ls]

    total_kw       = len(results_by_keyword)
    total_listings = len(all_listings)
    total_bs       = sum(1 for l in all_listings if l.get("bestseller_badge"))
    total_pn       = sum(1 for l in all_listings if l.get("popular_now_badge"))
    prices         = [_price_num(l) for l in all_listings if _price_num(l) > 0]
    avg_price      = f"${sum(prices)/len(prices):.2f}" if prices else "N/A"

    # ── Nav links ──────────────────────────────────────────────────────
    nav_links = []
    nav_links.append('<a href="#summary">Summary</a>')
    if total_bs: nav_links.append('<a href="#bestsellers">Bestsellers</a>')
    if total_pn: nav_links.append('<a href="#popular-now">Popular Now</a>')
    nav_links.append('<a href="#by-keyword">By Keyword</a>')
    nav_links.append('<a href="#keywords">Title Keywords</a>')
    if expanded_keywords: nav_links.append('<a href="#expand">Next Searches</a>')
    nav_html = '<div class="nav">' + "".join(nav_links) + '</div>'

    # ── Stats bar ──────────────────────────────────────────────────────
    stats_html = f"""
<div class="stats-bar">
  <div class="stat-card"><div class="num">{total_kw}</div><div class="label">Keywords</div></div>
  <div class="stat-card"><div class="num">{total_listings}</div><div class="label">Listings</div></div>
  <div class="stat-card"><div class="num">{total_bs}</div><div class="label">Bestsellers</div></div>
  <div class="stat-card"><div class="num">{total_pn}</div><div class="label">Popular Now</div></div>
  <div class="stat-card"><div class="num">{avg_price}</div><div class="label">Avg Price</div></div>
  <div class="stat-card"><div class="num">{len(prices)}</div><div class="label">With Price</div></div>
</div>"""

    # ── Summary table ──────────────────────────────────────────────────
    summary_html = f'<h2 id="summary">Summary by Keyword</h2>{_summary_table(results_by_keyword)}'

    # ── Bestseller section ─────────────────────────────────────────────
    bestsellers = [l for l in all_listings if l.get("bestseller_badge")]
    if bestsellers:
        bs_cards = "".join(_listing_card(l) for l in bestsellers)
        bs_html = f'<h2 id="bestsellers">Bestseller Listings ({len(bestsellers)})</h2>{bs_cards}'
    else:
        bs_html = '<h2 id="bestsellers">Bestseller Listings</h2><p style="color:var(--sand);">None found in this run.</p>'

    # ── Popular Now section ────────────────────────────────────────────
    popular = [l for l in all_listings if l.get("popular_now_badge")]
    if popular:
        pn_cards = "".join(_listing_card(l) for l in popular)
        pn_html = f'<h2 id="popular-now">Popular Now Listings ({len(popular)})</h2>{pn_cards}'
    else:
        pn_html = '<h2 id="popular-now">Popular Now Listings</h2><p style="color:var(--sand);">None found in this run.</p>'

    # ── Per-keyword sections ───────────────────────────────────────────
    kw_sections = []
    for kw, listings in results_by_keyword.items():
        anchor = kw.replace(" ", "-").replace("(", "").replace(")", "")
        kw_sections.append(
            f'<h2 id="{anchor}">{kw} — {len(listings)} listings</h2>'
        )
        if listings:
            kw_sections.append(_listings_table(listings))
        else:
            kw_sections.append("<p style='color:var(--sand);'>No digital listings captured.</p>")
    kw_html = '<h2 id="by-keyword">Full Listings by Keyword</h2>' + "".join(kw_sections)

    # ── Title keyword charts ───────────────────────────────────────────
    word_counts, phrase_counts = _extract_keywords(all_listings)
    top_words   = word_counts.most_common(30)
    top_phrases = [(p, c) for p, c in phrase_counts.most_common(40) if c >= 2][:25]

    max_w = top_words[0][1]   if top_words   else 1
    max_p = top_phrases[0][1] if top_phrases else 1

    kw_chart_html = f"""
<h2 id="keywords">Title Keyword Analysis</h2>
<p style="color:var(--sand);margin-bottom:16px;font-size:0.85rem;">
  Keywords that appear most in competitor listing titles — Etsy&rsquo;s #1 ranking factor.
  Cross-reference these against your own listing titles.
</p>
<h3>Single Words</h3>
<div style="margin:12px 0 24px;">{_bar_chart(top_words, max_w)}</div>
<h3>2-Word Phrases</h3>
<div style="margin:12px 0 24px;">{_bar_chart(top_phrases, max_p, css_class="bar-fill bar-phrase")}</div>
"""

    # Also render as sortable table
    def _valid_cell(term):
        return "yes" if len(term) <= 20 else "<span style='color:#b55;'>no — too long</span>"

    word_rows = "".join(
        f'<tr><td>{w}</td><td data-val="{c}">{c}</td><td>{_valid_cell(w)}</td></tr>'
        for w, c in top_words
    )
    phrase_rows = "".join(
        f'<tr><td>{p}</td><td data-val="{c}">{c}</td><td>{_valid_cell(p)}</td></tr>'
        for p, c in top_phrases
    )
    kw_chart_html += f"""
<h3 style="margin-top:24px;">Full Word Table</h3>
<div class="table-wrap">
<table class="sortable" style="margin-top:8px;">
  <thead><tr><th>Word</th><th>Count</th><th>Valid Etsy tag (≤20 chars)</th></tr></thead>
  <tbody>{word_rows}</tbody>
</table>
</div>
<h3 style="margin-top:24px;">Full Phrase Table</h3>
<div class="table-wrap">
<table class="sortable" style="margin-top:8px;">
  <thead><tr><th>Phrase</th><th>Count</th><th>Valid Etsy tag (≤20 chars)</th></tr></thead>
  <tbody>{phrase_rows}</tbody>
</table>
</div>
"""

    # ── Keyword expansion ──────────────────────────────────────────────
    if expanded_keywords:
        exp_items = "".join(
            f'<li><code style="background:#ede8e4;padding:2px 6px;border-radius:4px;">'
            f'{phrase}</code> — {count} titles</li>'
            for phrase, count in expanded_keywords[:20]
        )
        expand_html = f"""
<h2 id="expand">Keyword Expansion — Suggested Next Searches</h2>
<p style="color:var(--sand);margin-bottom:12px;font-size:0.85rem;">
  These 2-word phrases appeared frequently in competitor titles.
  Use them as additional Etsy search queries to find more competitors.
</p>
<ul style="list-style:none;display:flex;flex-wrap:wrap;gap:8px;">{exp_items}</ul>
"""
    else:
        expand_html = ""

    # ── Assemble ───────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Etsy Competitor Intelligence — Switzertemplates</title>
<style>{CSS}</style>
</head>
<body>

<div class="page-header">
  <h1>Etsy Competitor Intelligence Report</h1>
  <div class="meta">Switzertemplates &nbsp;·&nbsp; Generated {now} &nbsp;·&nbsp;
    {total_listings} digital listings &nbsp;·&nbsp;
    {total_kw} keywords</div>
</div>

{stats_html}

<div class="container">
  {nav_html}
  {summary_html}
  {bs_html}
  {pn_html}
  {kw_html}
  {kw_chart_html}
  {expand_html}
</div>

<footer>
  Switzertemplates Etsy Intelligence &nbsp;·&nbsp; {now} &nbsp;·&nbsp;
  Data sourced from public Etsy search results
</footer>

<script>{SORT_JS}</script>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")
    return out_path
