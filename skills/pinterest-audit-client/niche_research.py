"""
niche_research.py — Pinterest niche overview: market stats + why Pinterest framing.
Uses keyword data + web research + Claude synthesis.
"""

from __future__ import annotations
import os
import re
import requests
import anthropic


def _fetch(url: str, timeout: int = 15) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        text = re.sub(r"<script[^>]*>.*?</script>", "", resp.text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s{3,}", "\n", text)
        return text[:6000]
    except Exception:
        return ""


def research_niche_overview(niche: str, products: str, keywords: list[dict]) -> dict:
    """
    Generate Pinterest niche overview stats and a why-Pinterest framing.
    Returns a dict with keys: stats_table, why_pinterest.
    """
    print("\n[0/9] Niche Overview Research")

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Fetch some Pinterest market context
    print("  Fetching Pinterest market data...")
    sources = {
        "Pinterest business stats": _fetch("https://business.pinterest.com/en/pinterest-facts/"),
        "Pinterest advertiser stats": _fetch("https://newsroom.pinterest.com/en/"),
    }

    # Top keyword for niche context
    top_keyword = keywords[0]["keyword"] if keywords else niche
    total_volume = sum(k.get("volume", 0) or 0 for k in keywords)

    kw_summary = [
        {"keyword": k["keyword"], "volume": k.get("volume", 0)}
        for k in keywords[:10]
    ]

    sources_text = "\n\n".join(f"SOURCE: {k}\n{v}" for k, v in sources.items() if v)

    prompt = f"""You are a Pinterest marketing consultant writing the opening section of a paid client audit.

Client niche: {niche}
Client products: {products}
Primary keyword: {top_keyword}
Combined monthly search volume across top keywords: {total_volume:,}

Web context about Pinterest (use specific stats where available):
{sources_text}

Write TWO things:

---
PART 1: KEY STATS (4–5 stats as JSON)

Return a JSON array of 4–5 impactful stats specific to this niche on Pinterest. Mix platform-level stats (e.g. monthly active users, purchase intent %) with niche-specific estimates. Use real Pinterest published figures where available. Each stat should be a punchy number with a short label.

Format EXACTLY as:
[
  {{"value": "875M", "label": "Monthly active Pinterest users"}},
  {{"value": "97%", "label": "Top searches are unbranded (no specific brand)"}},
  {{"value": "X,XXX", "label": "Estimated accounts targeting this niche"}},
  {{"value": "XXK+", "label": "Monthly Pinterest searches for {top_keyword}"}},
  {{"value": "$XX–$XXM", "label": "Est. annual revenue in niche (digital products)"}}
]

Be specific. Use real numbers where possible, estimates with ranges otherwise. Return ONLY the JSON array for PART 1.

---
PART 2: WHY PINTEREST (1–2 sentences only)

One sharp sentence on why Pinterest is the right platform for this exact client — reference a specific user behaviour or stat that matches this niche. Then one sentence on the specific opportunity this creates for the client's products.

Format: Return PART 1 JSON then PART 2 text, separated by "---PART2---". No other formatting."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    text = msg.content[0].text
    if "---PART2---" in text:
        part1, part2 = text.split("---PART2---", 1)
    else:
        part1 = text
        part2 = ""

    print("  Niche overview complete")
    return {
        "stats_table": part1.strip(),
        "why_pinterest": part2.strip(),
    }
