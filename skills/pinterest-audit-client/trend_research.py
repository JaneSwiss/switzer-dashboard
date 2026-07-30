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

IMPORTANT: Whenever you give an example of a board name, pin title, or keyword phrase, write it in sentence case — capitalise ONLY the first word and genuine proper nouns (Pinterest, Etsy, etc). Example: write "Mother wound healing" not "Mother Wound Healing". Never capitalise every word.

MANDATORY FACTS — these are confirmed rules from Pinterest strategy guides. Use them exactly, do not contradict them, work them into the relevant sections below:
- New accounts: post 1 to 3 fresh pins daily. Do not over-post — this can trigger spam filters and restrict reach. At this stage, pin mostly repins from other accounts, not original content — only post your own pins if they are purely educational/informational or link to your own website or another outside resource.
- Growing & established accounts: scale to 3 to 10 pins daily, more if you have a large library of unique links and blog posts to share.
- Absolute hard limit: never save or post more than 50 pins in a single day on any account — this risks the account being flagged for spam.
- A consistent realistic target for an established account is 10-15 pins per day, not 40+.
- TOBI pins (text-overlay image pins — a clear headline/text overlaid on a photo or graphic) are currently the best-performing pin format.
- Pins using red, purple, or pink tones tend to outperform other colour palettes.
- The two ranking factors that matter most: Saves and Keywords (in title, description, board name).
- Every pin description should follow a 3-sentence structure: (1) hook/benefit, (2) what's inside or how it helps, (3) clear call to action.
- Recommended keyword research tools: Pinterest Trends, Pinterest Search (autocomplete/guided search), Pinterest Ads Manager keyword targeting. Do not mention PinClicks or any other third-party tool.
- Recommend following at least 10+ relevant accounts in the niche to build signal and discovery.

### Pinning frequency & timing
Specific numbers: daily pin count by account stage (new vs. growing/established), the 50-pin hard limit. Why consistency beats volume. Keep to 2 paragraphs.

### Pin format mix
What formats perform in 2026 for this niche specifically: static, video, carousels, TOBI pins. Rough % split. 2 paragraphs max.

### What makes pins get clicks
3-4 concrete rules for this niche: title structure, text overlay, image composition, hooks, colour palette. Short and specific.

### Keyword strategy
Where keywords go (title, description, alt text, board name). Character limits. The 3-sentence description structure. One example using this client's keywords. Mention the recommended keyword research tools.

### What actually drives growth
The honest 90-day focus vs. 3-6 month focus. What moves the needle for a new account in this niche. Mention following 10+ relevant accounts. 2 paragraphs.

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
