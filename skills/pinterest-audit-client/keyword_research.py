"""
keyword_research.py — Pinterest keyword research via Keywords Everywhere API
"""

from __future__ import annotations
import os
import requests
import json
import anthropic

KE_API = "https://api.keywordseverywhere.com/v1/get_keyword_data"


def get_keyword_volumes(keywords: list[str], api_key: str) -> dict:
    """Fetch monthly search volume + competition + CPC for a list of keywords."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    data = {
        "dataSource": "gkp",
        "country": "us",
        "currency": "USD",
        "kw[]": keywords,
    }
    try:
        resp = requests.post(KE_API, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return {item["keyword"]: item for item in result.get("data", [])}
    except Exception as e:
        print(f"  [warn] Keywords Everywhere error: {e}")
        return {}


def generate_seed_keywords(niche: str, products: str, client: anthropic.Anthropic) -> list[str]:
    """Use Claude to generate 30 seed keywords from niche description."""
    prompt = f"""You are a Pinterest SEO specialist. Generate 30 Pinterest search keywords for this client niche.

Niche: {niche}
Products/services: {products}

Requirements:
- Mix of broad (1-2 words) and specific (3-4 words) keywords
- Focus on buyer intent — people looking to purchase, not just browse
- Include keywords their target customers would actually search on Pinterest
- Vary the angle: product keywords, problem keywords, style/aesthetic keywords, tutorial keywords

Return ONLY a JSON array of 30 keyword strings. No explanation."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception:
        return []


def score_keywords(keyword_data: dict, client: anthropic.Anthropic) -> list[dict]:
    """Claude scores each keyword for commercial intent, returns top 15."""
    if not keyword_data:
        return []

    kw_list = []
    for kw, data in keyword_data.items():
        vol = data.get("vol", 0)
        comp = data.get("competition", 0)
        cpc = data.get("cpc", {}).get("value", 0) if isinstance(data.get("cpc"), dict) else 0
        kw_list.append({"keyword": kw, "volume": vol, "competition": comp, "cpc": cpc})

    prompt = f"""You are a Pinterest SEO specialist scoring keywords for a client audit.

Score each keyword on COMMERCIAL INTENT (1-10):
- 10 = someone ready to buy (e.g. "buy branding kit", "premade wix website")
- 5 = researching before buying (e.g. "branding tips for small business")
- 1 = just browsing/learning (e.g. "what is branding")

Also score PINTEREST FIT (1-10):
- 10 = visually searchable, strong save motivation (e.g. "aesthetic branding kit")
- 5 = moderate visual appeal
- 1 = text/theory topic, weak visual interest

Keywords to score:
{json.dumps(kw_list, indent=2)}

Return a JSON array of objects with: keyword, volume, competition, cpc, commercial_intent, pinterest_fit, composite_score (volume * commercial_intent * pinterest_fit / 100), recommendation (keep/skip).
Return ONLY valid JSON. No explanation."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        scored = json.loads(text)
        # Keep all non-zero volume keywords — sorted by composite score
        kept = [k for k in scored if (k.get("volume") or 0) > 0]
        kept.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
        return kept[:15]
    except Exception as e:
        print(f"  [warn] Keyword scoring error: {e}")
        return kw_list[:15]


def run_keyword_research(niche: str, products: str, seed_keywords: list[str] | None = None) -> list[dict]:
    """Full keyword research pipeline. Returns top 15 scored keywords."""
    api_key = os.getenv("KEYWORDS_EVERYWHERE_API_KEY", "")
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    print("\n[1/9] Keyword Research")

    if not seed_keywords:
        print("  Generating seed keywords with Claude...")
        seed_keywords = generate_seed_keywords(niche, products, client)
        print(f"  Generated {len(seed_keywords)} seed keywords")
    else:
        print(f"  Using {len(seed_keywords)} provided seed keywords")

    if api_key:
        print("  Fetching volumes from Keywords Everywhere...")
        kw_data = get_keyword_volumes(seed_keywords, api_key)
        print(f"  Got data for {len(kw_data)} keywords")
    else:
        print("  [warn] No Keywords Everywhere key — using seed keywords without volume data")
        kw_data = {kw: {"keyword": kw, "vol": 0, "competition": 0, "cpc": 0} for kw in seed_keywords}

    print("  Scoring keywords for commercial intent + Pinterest fit...")
    top_keywords = score_keywords(kw_data, client)
    print(f"  Selected top {len(top_keywords)} keywords")

    return top_keywords
