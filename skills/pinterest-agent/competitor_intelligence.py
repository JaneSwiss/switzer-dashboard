"""
Pinterest Agent — Competitor Intelligence
Pulls public pins from four competitor Pinterest accounts via RSS feeds,
analyses patterns with Claude, and writes findings to context files.

Data sources:
  - Pinterest RSS feeds (public, no auth required)
    https://www.pinterest.com/{username}/feed.rss
    Returns the most recent ~25 pins per account with title, description, URL.

Outputs:
  data/pinterest-agent/competitor-intelligence-raw.json
  context/competitor-intelligence.md
  Appends Competitor Intelligence section to context/pinterest-expert.md
"""
from __future__ import annotations

import os
import re
import json
import time
import requests
import anthropic
from pathlib import Path
from datetime import datetime
from xml.etree import ElementTree as ET
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR     = PROJECT_ROOT / "data" / "pinterest-agent"
CONTEXT_DIR  = PROJECT_ROOT / "context"

COMPETITORS = [
    "designpixiestore",
    "macaronsmimosas",
    "keikoya",
    "aluncreative",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/rss+xml,application/xml,text/xml,*/*",
}


# ── RSS fetching ──────────────────────────────────────────────────────────────

def _fetch_rss(username: str, max_pins: int = 25) -> list[dict]:
    """Fetch pins from a Pinterest account's public RSS feed."""
    url = f"https://www.pinterest.com/{username}/feed.rss"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  [{username}] RSS fetch failed: {e}")
        return []

    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as e:
        print(f"  [{username}] RSS parse failed: {e}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    channel = root.find("channel")
    if channel is None:
        return []

    account_title = (channel.findtext("title") or username).strip()

    pins = []
    for item in channel.findall("item")[:max_pins]:
        title_raw = (item.findtext("title") or "").strip()
        link      = (item.findtext("link")  or "").strip()
        pub_date  = (item.findtext("pubDate") or "").strip()

        # Description contains HTML: <img ...><p>description text</p>
        desc_html = item.findtext("description") or ""
        # Extract image URL
        img_match = re.search(r'<img[^>]+src="([^"]+)"', desc_html)
        img_url   = img_match.group(1) if img_match else ""
        # Extract text from <p> tags
        desc_text = " ".join(re.findall(r"<p>(.*?)</p>", desc_html, re.DOTALL))
        desc_text = re.sub(r"<[^>]+>", "", desc_text).strip()

        # Extract pin ID from URL
        pin_id_match = re.search(r"/pin/(\d+)", link)
        pin_id = pin_id_match.group(1) if pin_id_match else ""

        pins.append({
            "account":      username,
            "account_title": account_title,
            "pin_id":       pin_id,
            "title":        title_raw,
            "description":  desc_text,
            "url":          link,
            "image_url":    img_url,
            "pub_date":     pub_date,
            # These will be inferred by Claude
            "inferred_keyword":      None,
            "inferred_pin_type":     None,   # "product" or "educational"
            "inferred_visual_approach": None, # "mockup", "lifestyle", "text-overlay"
            "save_count":            None,   # not available via RSS
        })

    print(f"  [{username}] {len(pins)} pins fetched from RSS.")
    return pins


# ── Claude inference ──────────────────────────────────────────────────────────

def _infer_pin_metadata(pins: list[dict]) -> list[dict]:
    """
    Use Claude to infer: target keyword, pin type, visual approach
    for a batch of competitor pins.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  ANTHROPIC_API_KEY not set — skipping inference.")
        return pins

    client = anthropic.Anthropic(api_key=api_key)

    # Batch all pins into one prompt to minimise API calls
    pin_lines = []
    for i, p in enumerate(pins):
        pin_lines.append(
            f'[{i}] account="{p["account"]}" '
            f'title="{p["title"][:100]}" '
            f'description="{p["description"][:150]}"'
        )

    prompt = f"""You are analysing Pinterest competitor pins for a digital product business (branding kits, Wix website templates, Instagram templates, business bundles).

For each pin below, infer:
1. inferred_keyword: the single Pinterest search keyword this pin is targeting (2-5 words, lowercase)
2. inferred_pin_type: "product" (shows/promotes a specific product) or "educational" (teaches something)
3. inferred_visual_approach: one of:
   - "mockup" — shows the product on a device or in a branded scene
   - "lifestyle" — editorial photo, person at desk, workspace, not product-focused
   - "text-overlay" — clean background with bold text as the main visual element
   - "product-flat" — direct product flat lay / graphic showing the template itself
   - "unknown" — cannot determine from text alone

Return ONLY a JSON array of objects with these exact keys:
  index, inferred_keyword, inferred_pin_type, inferred_visual_approach

No markdown. Start with [ end with ].

PINS:
{chr(10).join(pin_lines)}"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        inferences = json.loads(raw)

        for inf in inferences:
            i = inf.get("index")
            if isinstance(i, int) and 0 <= i < len(pins):
                pins[i]["inferred_keyword"]        = inf.get("inferred_keyword", "")
                pins[i]["inferred_pin_type"]        = inf.get("inferred_pin_type", "unknown")
                pins[i]["inferred_visual_approach"] = inf.get("inferred_visual_approach", "unknown")

    except Exception as e:
        print(f"  Inference error: {e}")

    return pins


# ── Pattern analysis ──────────────────────────────────────────────────────────

def _extract_title_structure(title: str) -> str:
    t = title.lower().strip()
    if not t:
        return "unknown"
    if re.match(r"^how to ", t):
        return "how_to"
    if " that " in t:
        return "keyword_that_outcome"
    if re.match(r"^(a |the )", t) and " ready" in t:
        return "a_product_ready"
    if ":" in t:
        return "audience_colon"
    if re.match(r"^\d+", t):
        return "numbered_list"
    if re.match(r"^(for |your )", t):
        return "for_audience"
    if re.match(r"^(get |shop |browse |grab )", t):
        return "cta_led"
    return "statement"


def _analyse_patterns(all_pins: list[dict]) -> dict:
    """Extract aggregate patterns across all competitor pins."""

    # Title structures
    structures: dict[str, int] = {}
    for p in all_pins:
        s = _extract_title_structure(p["title"])
        structures[s] = structures.get(s, 0) + 1
    top_structures = sorted(structures.items(), key=lambda x: x[1], reverse=True)[:5]

    # Keywords
    kw_counts: dict[str, int] = {}
    for p in all_pins:
        kw = (p.get("inferred_keyword") or "").strip().lower()
        if kw and kw != "unknown":
            kw_counts[kw] = kw_counts.get(kw, 0) + 1
    top_keywords = sorted(kw_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    # Visual approach
    visual_counts: dict[str, int] = {}
    for p in all_pins:
        v = p.get("inferred_visual_approach") or "unknown"
        visual_counts[v] = visual_counts.get(v, 0) + 1

    # Pin type ratio
    type_counts: dict[str, int] = {}
    for p in all_pins:
        t = p.get("inferred_pin_type") or "unknown"
        type_counts[t] = type_counts.get(t, 0) + 1

    # Per-account breakdown
    by_account: dict[str, dict] = {}
    for p in all_pins:
        acc = p["account"]
        if acc not in by_account:
            by_account[acc] = {"total": 0, "product": 0, "educational": 0,
                               "visual": {}, "keywords": []}
        by_account[acc]["total"] += 1
        pt = p.get("inferred_pin_type", "unknown")
        if pt in ("product", "educational"):
            by_account[acc][pt] += 1
        va = p.get("inferred_visual_approach", "unknown")
        by_account[acc]["visual"][va] = by_account[acc]["visual"].get(va, 0) + 1
        kw = p.get("inferred_keyword", "")
        if kw:
            by_account[acc]["keywords"].append(kw)

    # Dominant visual approach among all pins
    dominant_visual = max(visual_counts, key=lambda k: visual_counts[k]) if visual_counts else "unknown"

    return {
        "total_pins_analysed":      len(all_pins),
        "top_title_structures":     top_structures,
        "top_10_targeted_keywords": top_keywords,
        "visual_approach_counts":   visual_counts,
        "dominant_visual_approach": dominant_visual,
        "pin_type_ratio":           type_counts,
        "by_account":               by_account,
    }


# ── Claude narrative analysis ─────────────────────────────────────────────────

def _write_narrative(all_pins: list[dict], patterns: dict) -> str:
    """
    Ask Claude to write a narrative analysis of competitor patterns
    suitable for context/competitor-intelligence.md.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "Claude analysis not available — ANTHROPIC_API_KEY not set."

    client = anthropic.Anthropic(api_key=api_key)

    # Sample pins for context (top 30 by account variety)
    sample = []
    seen_accounts: dict[str, int] = {}
    for p in all_pins:
        acc = p["account"]
        if seen_accounts.get(acc, 0) < 8:
            sample.append(p)
            seen_accounts[acc] = seen_accounts.get(acc, 0) + 1
        if len(sample) >= 32:
            break

    sample_lines = "\n".join(
        f'  [{p["account"]}] "{p["title"][:80]}" | kw={p.get("inferred_keyword","")} '
        f'| type={p.get("inferred_pin_type","")} | visual={p.get("inferred_visual_approach","")}'
        for p in sample
    )

    prompt = f"""You are a Pinterest strategy analyst for Switzertemplates, a digital product business
selling branding kits, Wix website templates, Instagram templates, and business bundles.

You have analysed {patterns["total_pins_analysed"]} pins from four competitor accounts:
designpixiestore, macaronsmimosas, keikoya, aluncreative.
These are all successful digital product sellers targeting a similar audience.

AGGREGATE PATTERNS:
Top title structures: {patterns["top_title_structures"]}
Top targeted keywords: {patterns["top_10_targeted_keywords"]}
Visual approach counts: {patterns["visual_approach_counts"]}
Dominant visual: {patterns["dominant_visual_approach"]}
Pin type ratio: {patterns["pin_type_ratio"]}

SAMPLE PIN DATA:
{sample_lines}

Write a competitor intelligence report in markdown for context/competitor-intelligence.md.
Structure it as:
1. Overview (2-3 sentences on what these accounts have in common)
2. Title Structure Analysis (what patterns dominate and what makes them work)
3. Keyword Targeting (what keywords they are fighting for and any gaps we can exploit)
4. Visual Approach Analysis (what visual styles dominate and why)
5. Product vs Educational Mix (what ratio they use and what it tells us)
6. Per-Account Notes (one paragraph per account: designpixiestore, macaronsmimosas, keikoya, aluncreative)
7. Strategic Opportunities for Switzertemplates (where we can win — gaps, underserved angles, weaknesses)

Write in plain markdown. No excessive headers. Be specific and actionable.
Focus on what Switzertemplates should DO differently or the same based on these patterns."""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def _write_expert_section(patterns: dict, narrative: str) -> str:
    """
    Ask Claude to write the Competitor Intelligence section
    to append to context/pinterest-expert.md.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Based on the following competitor analysis, write a new section called
"## Competitor Intelligence" to be appended to a Pinterest strategy guide.

This section will be read by an AI Pinterest agent before it generates pin copy.
Write it as direct instructions the agent must follow, not as a report.

KEY FINDINGS:
{narrative[:2000]}

PATTERNS:
Top title structures: {patterns["top_title_structures"]}
Dominant visual: {patterns["dominant_visual_approach"]}
Top keywords: {patterns["top_10_targeted_keywords"]}
Pin type ratio: {patterns["pin_type_ratio"]}

The section must cover:
1. Which title structures competitors use most (and which to adopt vs avoid)
2. Which keywords competitors target heavily (crowded) vs gaps we can exploit
3. What visual approach dominates and whether to match or differentiate
4. What the product/educational ratio tells us about what converts for this niche
5. 3-5 specific tactical rules the agent must follow based on competitor patterns

Format: markdown, under 600 words, direct rules not observations.
Start with: ## Competitor Intelligence"""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    load_dotenv(PROJECT_ROOT / ".env")
    print(f"\nCompetitor Intelligence — {datetime.now().strftime('%d %b %Y %H:%M')}")
    print("=" * 60)

    # Step 1 — Fetch RSS feeds
    print("\n[1/5] Fetching pins from competitor RSS feeds...")
    all_pins: list[dict] = []
    for username in COMPETITORS:
        pins = _fetch_rss(username, max_pins=25)
        all_pins.extend(pins)
        time.sleep(1.0)  # polite delay

    print(f"  Total pins collected: {len(all_pins)}")

    if not all_pins:
        print("No pins collected. Exiting.")
        return

    # Step 2 — Infer metadata with Claude
    print("\n[2/5] Inferring keyword, pin type, visual approach via Claude...")
    all_pins = _infer_pin_metadata(all_pins)
    print(f"  Inference complete for {len(all_pins)} pins.")

    # Step 3 — Save raw data
    print("\n[3/5] Saving raw data...")
    raw_path = DATA_DIR / "competitor-intelligence-raw.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_output = {
        "collected_at": datetime.now().isoformat(),
        "accounts":     COMPETITORS,
        "total_pins":   len(all_pins),
        "note":         "Sourced from Pinterest public RSS feeds. Save counts not available via RSS. "
                        "Pins are most recent, not sorted by saves.",
        "pins":         all_pins,
    }
    raw_path.write_text(json.dumps(raw_output, indent=2, ensure_ascii=False))
    print(f"  Saved → {raw_path}")

    # Step 4 — Pattern analysis
    print("\n[4/5] Analysing patterns across all accounts...")
    patterns = _analyse_patterns(all_pins)

    print(f"  Title structures: {dict(patterns['top_title_structures'][:3])}")
    print(f"  Top keywords:     {[k for k, _ in patterns['top_10_targeted_keywords'][:5]]}")
    print(f"  Dominant visual:  {patterns['dominant_visual_approach']}")
    print(f"  Pin type ratio:   {patterns['pin_type_ratio']}")

    # Step 5 — Write outputs
    print("\n[5/5] Writing analysis to context files...")

    # Narrative report
    narrative = _write_narrative(all_pins, patterns)

    # context/competitor-intelligence.md
    ci_path = CONTEXT_DIR / "competitor-intelligence.md"
    header = f"""# competitor-intelligence.md — Switzertemplates Pinterest Competitor Analysis

*Generated: {datetime.now().strftime('%d %B %Y')}*
*Accounts analysed: {', '.join(COMPETITORS)}*
*Total pins: {len(all_pins)} (sourced from public Pinterest RSS feeds)*
*Note: Pins are most recent activity, not ranked by saves. Save counts not available via RSS.*

---

"""
    ci_path.write_text(header + narrative)
    print(f"  Written → {ci_path}")

    # Append to pinterest-expert.md
    expert_path = CONTEXT_DIR / "pinterest-expert.md"
    expert_section = _write_expert_section(patterns, narrative)
    if expert_section:
        existing = expert_path.read_text()
        # Remove any existing competitor intelligence section
        existing = re.sub(
            r"\n## Competitor Intelligence.*$", "", existing,
            flags=re.DOTALL
        ).rstrip()
        updated = existing + "\n\n---\n\n" + expert_section + "\n\n---\n\n" + \
                  f"*Competitor intelligence last updated: {datetime.now().strftime('%d %B %Y')}*\n"
        expert_path.write_text(updated)
        print(f"  Appended Competitor Intelligence section → {expert_path}")

    print(f"\n{'='*60}")
    print(f"Done. {len(all_pins)} pins analysed across {len(COMPETITORS)} accounts.")
    print(f"Raw data:   {raw_path}")
    print(f"Analysis:   {ci_path}")
    print(f"Expert doc: {expert_path}")


if __name__ == "__main__":
    run()
