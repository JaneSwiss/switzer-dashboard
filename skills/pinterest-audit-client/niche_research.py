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

    prompt = f"""You are a Pinterest marketing consultant writing the opening section of a paid client audit. The audit is written TO the client directly — always address them as "you", never as "the client", "she", or "her".

Client niche: {niche}
Client products: {products}
Primary keyword: {top_keyword}
Combined monthly search volume across top keywords: {total_volume:,}

Known current platform fact (use this, do not use an older/outdated MAU figure): Pinterest had roughly 619 million global monthly active users as of late 2025/early 2026 — use this as the basis for any "monthly active users" stat, not an older figure like 2024's ~500M.

Web context about Pinterest (use specific stats where available, but prefer the platform fact above for MAU):
{sources_text}

CRITICAL RULE — DO NOT VIOLATE: Every number you produce in this entire response must be real and verifiable — either the platform fact given above, the real combined search volume given above, or a real published stat that actually appears in the web context below. NEVER invent a plausible-sounding estimate (e.g. "estimated accounts in this niche", "estimated revenue potential") and present it as a stat. If you don't have a real number for something, leave it out entirely — do not fill the gap with a guess.

ALSO CRITICAL: Do not compare Pinterest to Instagram, TikTok, Facebook, Amazon, or any other named platform anywhere in this response. Describe what Pinterest does on its own terms only.

Write TWO things:

---
PART 1: KEY STATS (2–3 stats as JSON)

Return a JSON array of 2–3 stats, using ONLY real numbers: the MAU fact above, the real combined search volume above, and (only if it is genuinely present in the web context, not invented) one additional real published Pinterest platform stat. It is better to return 2 honest stats than to pad to 4 with an invented one.

Format EXACTLY as:
[
  {{"value": "619M+", "label": "Monthly active Pinterest users"}},
  {{"value": "XXK+", "label": "Monthly Pinterest searches for {top_keyword}"}}
]

Return ONLY the JSON array for PART 1.

---
PART 2: WHY PINTEREST (2–3 short paragraphs)

Write directly to the client in second person. The very first word must be "You". This needs to be a real, fact-grounded case for why Pinterest specifically suits this niche. Cover:

1. Women can search Pinterest privately — without comments, likes, or followers attached to what they search for. Explain why that matters for this specific niche.
2. The real combined search volume number given above as proof the demand already exists, naming 2-3 of the actual highest-volume keywords from this niche.
3. If you can confidently name a REAL, currently active account or creator who has built a genuine audience/business on Pinterest in this niche or an adjacent one, use them as a concrete proof point. Only use a real name you are confident about — never invent one.

Write in simple, conversational, human language — not robotic or corporate. No jargon, no buzzwords like "leverage" or "synergy". Talk like a sharp friend explaining a real opportunity, using specifics, not generic marketing language.

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
