"""
report_builder.py — Assemble the Pinterest client audit report.

Section order:
  1. Niche Overview (stat cards + why Pinterest)
  2. Trending Keywords in Your Niche (simple list)
  3. Keyword Cluster Groupings
  4. Reddit & Quora questions
  5. Pinterest Trends in Your Niche (colour palette + design trends)
  6. Competitor Analysis
  7. Content Gap Opportunities (action table)
  8. Pinterest Strategy & Growth Plan
  9. Board Structure Recommendations
"""

from __future__ import annotations
import os
import json
import re
import anthropic
from datetime import datetime, timezone


def _fmt_followers(v: int) -> str:
    if v < 0:
        return "—"
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.0f}K"
    return str(v)


# ── Section 1: Niche Overview ──────────────────────────────────────────────────

def build_niche_overview(niche_data: dict) -> str:
    lines = ["## Pinterest Niche Overview\n"]

    why = niche_data.get("why_pinterest", "").strip()
    if why:
        lines.append(why)
        lines.append("")

    stats_raw = niche_data.get("stats_table", "").strip()
    if stats_raw:
        # Try to parse as JSON stat cards (from updated niche_research prompt)
        try:
            match = re.search(r"\[[\s\S]*?\]", stats_raw)
            if match:
                stats = json.loads(match.group(0))
                lines.append('<div class="stat-grid">')
                for s in stats:
                    val = str(s.get("value", "")).replace('"', "&quot;")
                    label = str(s.get("label", "")).replace('"', "&quot;")
                    lines.append(f'<div class="stat-card"><span class="stat-value">{val}</span><span class="stat-label">{label}</span></div>')
                lines.append('</div>')
            else:
                lines.append(stats_raw)
        except Exception:
            lines.append(stats_raw)

    return "\n".join(lines)


# ── Section 2: Keywords ────────────────────────────────────────────────────────

def build_keywords(keywords: list[dict]) -> str:
    # Filter zero-volume rows, keep all that pass (up to 15)
    kws = [k for k in keywords if (k.get("volume") or 0) > 0]

    lines = ["## Trending Keywords in Your Niche\n"]
    lines.append("*Based on Google monthly search volume + Pinterest commercial intent scoring*\n")

    for i, kw in enumerate(kws, 1):
        lines.append(f"{i}. {kw.get('keyword', '—')}")

    return "\n".join(lines)


# ── Section 3: Keyword Clusters ────────────────────────────────────────────────

def build_keyword_clusters(keywords: list[dict], niche: str, products: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    kw_list = [{"keyword": k["keyword"], "volume": k.get("volume", 0)} for k in keywords if (k.get("volume") or 0) > 0]

    prompt = f"""You are a Pinterest SEO strategist. Group these keywords into 3–4 topical groups for a client in: {niche}

Keywords:
{json.dumps(kw_list, indent=2)}

For each group output EXACTLY this format — the ### heading immediately followed by the table, no text in between:

### Group N: [Group Name]

| Keyword | Buyer Intent |
|---------|--------------|
| keyword | High/Medium/Low — one-sentence reason |

Do NOT add any intro paragraph, summary paragraph, or text between the heading and the table. Do NOT add any closing paragraph or summary after the last table. Lead with the highest-volume group. No preamble before the first group."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text
    # Strip any intro text before the first ### Group
    raw = re.sub(r'^.*?(### Group)', r'\1', raw, count=1, flags=re.DOTALL)
    return f"## Keyword groups\n\n{raw}"


def build_keyword_groups_fixed(groups: list[dict], niche: str, products: str) -> str:
    """
    Same output shape as build_keyword_clusters, but groups are predefined
    (group name + exact keyword list + optional csv filename) instead of
    left to Claude to cluster. Use when the client's keyword groups are
    already decided (e.g. matched to prepared CSV exports).

    groups: [{"name": str, "keywords": [{"keyword": str, "volume": int}], "csv": str | None}]
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    lines = ["## Keyword groups\n"]
    csv_groups = []

    for i, g in enumerate(groups, 1):
        kw_list = [{"keyword": k["keyword"], "volume": k.get("volume", 0)} for k in g["keywords"]]

        prompt = f"""You are a Pinterest SEO strategist writing buyer-intent reasoning for one keyword group in a client audit.

Client niche: {niche}
Client products/services: {products}
Group: {g['name']}

Keywords in this group:
{json.dumps(kw_list, indent=2)}

For each keyword, output one table row. Output ONLY the table, no heading, no intro, no summary:

| Keyword | Buyer Intent |
|---------|--------------|
| keyword | High/Medium/Low — one-sentence reason |

Buyer Intent = High/Medium/Low based on how close this search is to booking a coaching service or buying a product, plus a one-sentence reason specific to this niche."""

        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        table = msg.content[0].text.strip()
        table = re.sub(r'^.*?(\|\s*Keyword)', r'\1', table, count=1, flags=re.DOTALL)

        lines.append(f"### Group {i}: {g['name']}\n")
        lines.append(table)
        lines.append("")

        if g.get("csv"):
            csv_groups.append((g["name"], g["csv"]))

    if csv_groups:
        lines.append("### Download detailed spreadsheet for each keyword group:\n")
        lines.append('<div class="csv-download-row">')
        for name, csv_file in csv_groups:
            lines.append(
                f'<a href="{csv_file}" download class="csv-btn">'
                f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
                f'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/>'
                f'<line x1="12" y1="15" x2="12" y2="3"/></svg>{name}</a>'
            )
        lines.append("</div>")

    return "\n".join(lines)


# ── Section 4: Reddit & Quora ──────────────────────────────────────────────────

def build_reddit(questions: list[dict]) -> str:
    lines = ["## What Buyers Are Asking (Reddit & Quora)\n"]
    if not questions:
        lines.append("*No Reddit/Quora data retrieved — check API keys.*\n")
        return "\n".join(lines)

    lines.append("| # | Thread | Pinterest content angle |")
    lines.append("|---|--------|--------------------------|")

    for i, q in enumerate(questions[:10], 1):
        # Link text must be the real thread title — never the reframed buyer_question,
        # since that text gets shown as if it were the actual clickable thread title.
        real_title = (q.get("title") or q.get("buyer_question") or "—").replace("|", "—")
        suggestions = (q.get("suggestions") or q.get("why_it_buys") or "—").replace("|", "—")
        url = q.get("url") or ""
        q_text = f"[{real_title}]({url})" if url else real_title
        lines.append(f"| {i} | {q_text} | {suggestions} |")

    return "\n".join(lines)


def _sentence_case_phrase(text: str) -> str:
    """Capitalise only the first word of a phrase — used to normalise
    Title Case board names (real scraped data or hand-written text)."""
    if not text:
        return text
    words = text.split()
    return " ".join(w if i == 0 else w.lower() for i, w in enumerate(words))


# ── Sections 5 & 6: Trends (passed through from trend_research) ──────────────

# ── Section 7: Competitor Analysis ────────────────────────────────────────────

def build_competitors(competitors: list[dict], niche: str, products: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    lines = ["## Competitor Analysis\n"]
    lines.append("Use these accounts for general inspo, board analysis, recent pin analysis, for following their followers etc.\n")

    if not competitors:
        lines.append("*No competitors passed the activity + follower filter. Add competitor handles manually via --competitors.*\n")
        return "\n".join(lines)

    # Summary table
    lines.append("| Account | Followers | Boards | Last Active | Bio |")
    lines.append("|---------|-----------|--------|-------------|-----|")
    for c in competitors:
        followers = _fmt_followers(c.get("followers", 0))
        board_count = len(c.get("boards", []))
        dates = c.get("recent_pin_dates", [])
        last_pin = dates[0][:10] if dates else "unknown"
        bio = (c.get("bio") or "").replace("|", "—")[:60]
        lines.append(f"| [@{c['username']}](https://www.pinterest.com/{c['username']}/) | {followers} | {board_count} | {last_pin} | {bio}... |")
    lines.append("")

    # Per-competitor analysis
    for c in competitors:
        boards_sc = [{**b, "name": _sentence_case_phrase(b.get("name", ""))} for b in c.get("boards", [])[:6]]
        comp_data = {
            "username": c["username"],
            "followers": c.get("followers"),
            "bio": c.get("bio"),
            "boards": boards_sc,
        }

        prompt = f"""Write a sharp competitor snapshot for this Pinterest account. Client niche: {niche}. Client sells: {products}.

Account data:
{json.dumps(comp_data, indent=2)}

One short paragraph only: what they sell and how their board structure reflects their content strategy (reference actual board names exactly as given — sentence case, do not re-capitalise them). Write it as general inspiration/observation, not as a competitive weakness to exploit.

Under 60 words. Be specific. No filler. When you reference board names, use sentence case (only first word capitalised) — do not write them in Title Case even if you'd naturally capitalise each word."""

        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        followers_str = _fmt_followers(c.get("followers", 0))
        lines.append(f"### @{c['username']} — {followers_str} followers\n")
        lines.append(msg.content[0].text)
        lines.append("")

    return "\n".join(lines)


# ── Section 8: Content Gap Opportunities ──────────────────────────────────────

def build_content_gaps(keywords: list[dict], niche: str, products: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    kw_list = [{"keyword": k["keyword"], "volume": k.get("volume", 0), "competition": k.get("competition", 0)}
               for k in keywords if (k.get("volume") or 0) > 0]

    prompt = f"""You are a Pinterest content strategist identifying content gaps for a client in: {niche}
Client products: {products}

Keywords with volumes and competition:
{json.dumps(kw_list, indent=2)}

Identify 5 specific content gap opportunities. For each one:
- A gap that exists RIGHT NOW on Pinterest for this niche (low competition + real search demand, or content that exists but is outdated/low quality)
- What makes it a gap (not enough pins, poor quality existing content, wrong audience targeting, etc.)
- The exact action the client should take (specific pin format + title structure + product to link to)
- Estimated effort to create the content (Easy / Medium / Hard)

Format as a table:

| # | Keyword / Angle | Why It's a Gap | Action: What to Create | Link to | Effort |
|---|-----------------|----------------|------------------------|---------|--------|

Then write 2–3 sentences summarising the single biggest opportunity and why acting on it first will have the most impact.

Be specific. No vague advice like "create more content." Every action must be something the client can do this week."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    return f"## Content Gap Opportunities\n\n{msg.content[0].text}"


# ── Section 9: 2026 Strategy (passed through from trend_research) ─────────────

# ── Section 10: Board Structure ────────────────────────────────────────────────

def build_board_structure(keywords: list[dict], niche: str, products: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    kw_list = [k["keyword"] for k in keywords if (k.get("volume") or 0) > 0][:12]

    prompt = f"""You are a Pinterest SEO specialist. Create a full board structure for a client in: {niche}
Client products: {products}
Top keywords: {kw_list}

Create exactly 7 Pinterest boards.

BOARD NAMING RULE — THIS IS NON-NEGOTIABLE:
The board name must be taken DIRECTLY from the keyword list above. Copy the keyword as-is in sentence case — capitalise ONLY the first word and genuine proper nouns (Pinterest, Etsy, Wix, etc). Do NOT capitalise every word. Do NOT rephrase, do NOT add adjectives, do NOT get creative.

CORRECT: keyword is "premade Wix websites" → board name is "Premade Wix websites"
CORRECT: keyword is "branding templates for small business" → board name is "Branding templates for small business"
WRONG: keyword is "premade Wix websites" → board name is "Premade Wix Websites" (do not capitalise every word)
WRONG: keyword is "branding kits" → board name is "Branding Tips for Female Entrepreneurs" (do not invent a new phrase)

Every board name must be a verbatim keyword from the list. If you need more boards than keywords, use close variants of the keywords (e.g. plural/singular, add "ideas" or "inspiration" to the end). Never invent a name that does not start from the keyword.

For each board:
- Board name (verbatim keyword from list, sentence case as described above, under 50 characters, no hashtags)
- Board description (150–200 characters, keyword-rich, written as a helpful sentence for the viewer)
- Top 3 keywords this board targets
- Recommended number of pins before the board is considered "established"
- Pin types to add (product pins, educational, repins, etc.)

Format as a markdown table:

| Board Name | Description | Keywords | Min Pins | Pin Types |
|------------|-------------|----------|----------|-----------|

Return ONLY the table. Do not add a title, intro, closing summary, or any extra section (e.g. no "Quick-Reference Notes" or "Implementation Notes") after the table."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    return msg.content[0].text


# ── Assembly ───────────────────────────────────────────────────────────────────

def assemble_report(
    niche: str,
    products: str,
    keywords: list[dict],
    questions: list[dict],
    trend_content: dict,
    niche_overview: dict,
    run_date: str,
    competitors: list[dict] | None = None,
    keyword_groups_override: str | None = None,
) -> str:
    print("\n[9/9] Assembling Report")

    sections = []

    # Title
    sections.append(f"# Pinterest Niche Audit — {niche}\n")
    sections.append(f"**Generated:** {run_date}  \n**Products/Services:** {products}  \n")
    sections.append("---\n")

    # 1. Niche Overview
    print("  Section 1 — Niche Overview...")
    sections.append(build_niche_overview(niche_overview))
    sections.append("\n---\n")

    # 2. Keywords
    print("  Section 2 — Keywords...")
    sections.append(build_keywords(keywords))
    sections.append("\n---\n")

    # 3. Keyword Clusters
    print("  Section 3 — Keyword Clusters...")
    if keyword_groups_override:
        sections.append(keyword_groups_override)
    else:
        sections.append(build_keyword_clusters(keywords, niche, products))
    sections.append("\n---\n")

    # 4. Reddit & Quora
    print("  Section 4 — Reddit/Quora...")
    sections.append(build_reddit(questions))
    sections.append("\n---\n")

    # 5. Visual Trends (colour palette + design trends)
    print("  Sections 5 & 6 — Colour Palette + Design Trends...")
    colour_trend = trend_content.get("colour_palette", "").strip()
    if colour_trend:
        # Strip any intro text before the first ###
        colour_trend = re.sub(r'^.*?(### )', r'\1', colour_trend, count=1, flags=re.DOTALL)
        sections.append("## Visual Trends on Pinterest\n")
        sections.append(colour_trend)
    sections.append("\n---\n")

    # 6. Competitor Analysis
    if competitors:
        print("  Section 6 — Competitor Analysis...")
        sections.append(build_competitors(competitors, niche, products))
        sections.append("\n---\n")

    # 7. Pinterest Strategy & Growth Plan (includes board structure)
    print("  Section 7 — Pinterest Strategy & Growth Plan...")
    strategy = trend_content.get("strategy", "").strip()
    # Strip any leading H1 title Claude adds (redundant with the card's own "Pinterest Strategy & Growth Plan" heading)
    strategy = re.sub(r'^#\s+[^\n]*\n', '', strategy)
    # Convert any ## sub-headings inside the strategy to ### so they stay inside one card
    strategy = re.sub(r'\n## ', '\n### ', strategy)
    strategy = re.sub(r'^## ', '### ', strategy)
    # Strip any Claude-generated intro subsection (e.g. "Paid Audit Deliverable" header)
    strategy = re.sub(
        r'### [^\n]*(?:deliverable|audit)[^\n]*\n(?:(?!### ).)*',
        '', strategy, flags=re.DOTALL | re.IGNORECASE
    ).strip()
    board = build_board_structure(keywords, niche, products)
    # Strip the "board names are the keywords" closing sentence Claude sometimes adds
    board = re.sub(r'Board names[^\n]*keywords themselves[^\n]*\n?', '', board, flags=re.IGNORECASE)
    # Strip any leading H1 title Claude adds (redundant with the "Board structure recommendations" heading below)
    board = re.sub(r'^#\s+[^\n]*\n', '', board.strip())
    # Downgrade any ## or ### sub-headings inside the board section so they stay inside the strategy card
    board = re.sub(r'\n#{2,3}\s+', '\n#### ', board)
    if strategy:
        combined = f"{strategy}\n\n### Board structure recommendations\n\n{board}"
        sections.append(f"## Pinterest Strategy & Growth Plan\n\n{combined}")

    return "\n".join(sections)


def save_report(content: str, niche: str) -> str:
    from pathlib import Path

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = niche.lower().replace(" ", "-")[:40]
    slug = re.sub(r"[^a-z0-9-]", "", slug)

    output_dir = Path(__file__).parent.parent.parent / "outputs" / "client-audits"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{date_str}-{slug}-audit.md"
    path = output_dir / filename
    path.write_text(content, encoding="utf-8")
    return str(path)
