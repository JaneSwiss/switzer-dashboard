"""
reddit_research.py — Discover Reddit questions buyers ask in a niche.
Primary: Reddit public JSON API (free, no key needed).
Fallback: ValueSERP → Bing (paid, used only if Reddit returns too little).
"""

from __future__ import annotations
import os
import re
import time
import requests
import json
import anthropic

REDDIT_HEADERS = {"User-Agent": "pinterest-audit-research/1.0 (non-commercial research)"}

# Subreddits that contain high buying-intent discussions
BUYING_SUBREDDITS = [
    "giftideas",
    "gifts",
    "GiftsForWomen",
    "Buyingformygirlfriend",
    "weddingplanning",
    "Etsy",
    "smallbusiness",
    "femalefashionadvice",
    "AskWomen",
]


def search_reddit_free(query: str, subreddit: str = "", limit: int = 10) -> list[dict]:
    """Search Reddit using the free public JSON API — no key required."""
    if subreddit:
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {"q": query, "sort": "top", "t": "year", "limit": limit, "restrict_sr": 1}
    else:
        url = "https://www.reddit.com/search.json"
        params = {"q": query, "sort": "top", "t": "year", "limit": limit}

    try:
        resp = requests.get(url, params=params, headers=REDDIT_HEADERS, timeout=15)
        if resp.status_code == 429:
            time.sleep(3)
            resp = requests.get(url, params=params, headers=REDDIT_HEADERS, timeout=15)
        resp.raise_for_status()
        posts = resp.json().get("data", {}).get("children", [])
        results = []
        for p in posts:
            d = p["data"]
            if d.get("score", 0) < 5:
                continue
            results.append({
                "title": d.get("title", ""),
                "snippet": d.get("selftext", "")[:300] or d.get("title", ""),
                "url": f"https://reddit.com{d.get('permalink', '')}",
                "score": d.get("score", 0),
                "comments": d.get("num_comments", 0),
                "subreddit": d.get("subreddit", ""),
            })
        return results
    except Exception as e:
        print(f"  [warn] Reddit search error ({subreddit or 'all'}/{query[:30]}): {e}")
        return []


def search_valueserp(query: str, api_key: str, num: int = 10) -> list[dict]:
    params = {"api_key": api_key, "q": query, "num": num, "gl": "us", "hl": "en", "tbs": "qdr:y"}
    try:
        resp = requests.get("https://api.valueserp.com/search", params=params, timeout=20)
        resp.raise_for_status()
        return [
            {"title": r.get("title", ""), "snippet": r.get("snippet", ""), "url": r.get("link", "")}
            for r in resp.json().get("organic_results", [])
        ]
    except Exception as e:
        print(f"  [warn] ValueSERP error: {e}")
        return []


def search_bing(query: str, api_key: str, count: int = 10) -> list[dict]:
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    try:
        resp = requests.get(
            "https://api.bing.microsoft.com/v7.0/search",
            headers=headers, params={"q": query, "count": count, "freshness": "Month"}, timeout=20,
        )
        resp.raise_for_status()
        return [
            {"title": r.get("name", ""), "snippet": r.get("snippet", ""), "url": r.get("url", "")}
            for r in resp.json().get("webPages", {}).get("value", [])
        ]
    except Exception as e:
        print(f"  [warn] Bing search error: {e}")
        return []


def collect_questions(niche: str, products: str, subreddits: list[str] | None = None) -> list[dict]:
    """Collect buying-intent questions via Reddit free API, with paid API fallback."""
    all_results = []
    subreddits = subreddits or BUYING_SUBREDDITS

    # Step 1 — Reddit free API across targeted subreddits
    # Extract 2-3 short keyword phrases from the niche
    keywords = niche.split()[:4]
    short_query = " ".join(keywords[:3])

    print("  Searching Reddit (free API)...")
    for sub in subreddits:
        results = search_reddit_free(short_query, subreddit=sub, limit=5)
        all_results.extend(results)
        time.sleep(0.5)   # polite delay — Reddit rate limit is generous but respect it

    # Also do a general Reddit search for "recommendation" + niche
    general = search_reddit_free(f"{short_query} recommendation OR suggest OR buy", limit=10)
    all_results.extend(general)

    # Step 2 — Paid fallback whenever Reddit's free API didn't return enough to work with
    if len(all_results) < 15:
        valueserp_key = os.getenv("VALUESERP_API_KEY", "")
        bing_key = os.getenv("BING_API_KEY", "")
        queries = [
            f'site:reddit.com "{short_query}" buy recommend',
            f'site:reddit.com "{short_query}" advice OR help OR struggling',
            f'site:reddit.com "{short_query}" how to',
            f'site:quora.com "{short_query}"',
            f'site:quora.com "{short_query}" how do I',
        ]
        for query in queries:
            if valueserp_key:
                all_results.extend(search_valueserp(query, valueserp_key, num=10))
            elif bing_key:
                all_results.extend(search_bing(query, bing_key, count=10))

    # Deduplicate by URL
    seen: set = set()
    unique = []
    for r in all_results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    return unique


def filter_buying_questions(raw_results: list[dict], niche: str, products: str) -> list[dict]:
    if not raw_results:
        return []

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = f"""You are a Pinterest content strategist. Review these Reddit threads from the "{niche}" niche.

Client sells: {products}

For each thread, decide: does this thread represent a question where the answer naturally leads to buying a product or service? Keep only those where someone could be led toward purchasing.

Threads:
{json.dumps([{"title": r["title"], "snippet": r["snippet"][:200], "url": r["url"]} for r in raw_results[:30]], indent=2)}

Return a JSON array for threads to KEEP (maximum 10). Each object:
{{
  "title": "thread title",
  "url": "thread url",
  "buyer_question": "reframe as a specific question a buyer would ask",
  "suggestions": "1-2 sentences: what the discussion revealed about buyer needs, then how to turn this into a Pinterest content angle for this client"
}}

Return ONLY valid JSON."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        text = msg.content[0].text.strip()
        if "```" in text:
            text = re.sub(r"```(?:json)?", "", text).strip()
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            text = match.group(0)
        return json.loads(text)
    except Exception as e:
        print(f"  [warn] Question filtering error: {e}")
        return []


def run_reddit_research(niche: str, products: str, subreddits: list[str] | None = None) -> list[dict]:
    print("\n[4/9] Reddit & Quora Question Research")

    raw = collect_questions(niche, products, subreddits)
    print(f"  Found {len(raw)} raw threads")

    if not raw:
        print("  [warn] No threads found")
        return []

    filtered = filter_buying_questions(raw, niche, products)
    print(f"  Filtered to {len(filtered)} buying-intent questions")
    return filtered
