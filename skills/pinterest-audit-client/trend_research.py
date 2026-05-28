"""
trend_research.py — Pinterest Predicts 2026, design trends, 2026 strategy best practices.
"""

from __future__ import annotations
import os
import re
import requests
import anthropic

TREND_SOURCES = [
    {"name": "Pinterest Predicts 2026", "url": "https://business.pinterest.com/en/pinterest-predicts/"},
    {"name": "Pinterest 2026 Newsroom", "url": "https://newsroom.pinterest.com/en/post/pinterest-predicts-2026"},
    {"name": "Pinterest Trends", "url": "https://trends.pinterest.com"},
    {"name": "MadPin 2026 Design Trends", "url": "https://www.madpinmedia.com/pinterest-design-trends/"},
]

STRATEGY_SOURCES = [
    {"name": "Later Pinterest Strategy 2025/2026", "url": "https://later.com/blog/pinterest-marketing/"},
    {"name": "Tailwind Pinterest Best Practices", "url": "https://www.tailwindapp.com/blog/pinterest-best-practices"},
    {"name": "Pinterest Business Creator Hub", "url": "https://business.pinterest.com/en/creator-hub/"},
    {"name": "Hootsuite Pinterest Strategy", "url": "https://blog.hootsuite.com/how-to-use-pinterest-for-business/"},
]


def fetch_page(url: str, timeout: int = 15) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        text = re.sub(r"<script[^>]*>.*?</script>", "", resp.text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s{3,}", "\n", text)
        return text[:7000]
    except Exception as e:
        return f"[fetch failed: {e}]"


def synthesise_trends(raw_content: dict, niche: str, products: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    content_str = "\n\n---\n\n".join(f"SOURCE: {k}\n{v}" for k, v in raw_content.items() if v and not v.startswith("[fetch"))

    prompt = f"""You are a Pinterest strategy specialist writing a trend section for a paid client audit.

Client niche: {niche}
Client products: {products}

Raw source content from Pinterest Predicts and design trend sources for 2026:
{content_str}

IMPORTANT: Do NOT use the term "Idea Pins" anywhere — Pinterest discontinued this format.

Produce TWO sections in clean markdown. Extract only what is relevant to this client's niche.

### 2026 Colour Palette

A table with 5-6 trend colours:
| Colour Name | Hex (estimate) | Mood/Feeling | Use in Pins |

Then 1-2 sentences on how this client should apply these colours to their pin designs.

### 2026 Design Style Trends

Describe 4 distinct visual/aesthetic trends relevant to this niche. For each:
**Trend Name**
What it looks like in 1-2 sentences. Then: *Apply to [specific product type]: specific instruction.*

Keep each trend block tight — under 60 words. Be visual and specific, not generic.

Return ONLY the two sections. No preamble or explanation."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def synthesise_strategy(raw_content: dict, niche: str, products: str, keywords: list[dict]) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    content_str = "\n\n---\n\n".join(f"SOURCE: {k}\n{v}" for k, v in raw_content.items() if v and not v.startswith("[fetch"))

    top_kws = [k["keyword"] for k in keywords[:8]]

    prompt = f"""You are a Pinterest growth strategist writing the strategy section of a paid client audit.

Client niche: {niche}
Client products: {products}
Target keywords: {top_kws}

Web-researched 2026 Pinterest strategy sources:
{content_str}

Write an actionable Pinterest strategy guide for this client. Be concise — 2-3 short paragraphs per section maximum. No filler, no generic advice. Every sentence should be something the client can act on.

IMPORTANT: Do NOT use the term "Idea Pins" anywhere — Pinterest discontinued this format. Use "video pins", "standard pins", or "carousel pins" instead.

### Pinning frequency & timing
Specific numbers: daily pin count, best days/times. Why consistency beats volume. Keep to 2 paragraphs.

### Pin format mix
What formats perform in 2026 for this niche specifically: static, video, carousels. Rough % split. 2 paragraphs max.

### What makes pins get clicks
3-4 concrete rules for this niche: title structure, text overlay, image composition, hooks. Short and specific.

### Keyword strategy
Where keywords go (title, description, alt text, board name). Character limits. One example using this client's keywords.

### What actually drives growth
The honest 90-day focus vs. 3-6 month focus. What moves the needle for a new account in this niche. 2 paragraphs.

Keep it tight. Expert tone. Paid deliverable, not a blog post."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def run_trend_research(niche: str, products: str, keywords: list[dict] | None = None) -> dict:
    print("\n[5/9] Visual Trends, Colour & 2026 Strategy Research")

    trend_raw = {}
    for s in TREND_SOURCES:
        print(f"  Fetching {s['name']}...")
        trend_raw[s["name"]] = fetch_page(s["url"])

    print("  Synthesising trend + colour data...")
    trends_text = synthesise_trends(trend_raw, niche, products)

    strategy_raw = {}
    for s in STRATEGY_SOURCES:
        print(f"  Fetching {s['name']}...")
        strategy_raw[s["name"]] = fetch_page(s["url"])

    print("  Synthesising 2026 Pinterest strategy...")
    strategy_text = synthesise_strategy(strategy_raw, niche, products, keywords or [])

    print("  Trend + strategy research complete")
    return {
        "colour_palette": trends_text,
        "strategy": strategy_text,
    }
