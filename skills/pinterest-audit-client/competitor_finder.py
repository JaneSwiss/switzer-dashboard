"""
competitor_finder.py — Discover and filter Pinterest competitors.
Filter: active within last 30 days + 5,000+ followers.
Auto-discovery via ScraperAPI Pinterest search rendering.
"""

from __future__ import annotations
import os
import re
import requests
import email.utils
from datetime import datetime, timedelta, timezone
from pin_scraper import scrape_profile

EXCLUDED_HANDLES = {"pin", "search", "ideas", "explore", "today", "login", "signup",
                    "shop", "trending", "following", "homefeed", "interests"}


def discover_via_search(keywords: list[str], niche: str) -> list[str]:
    """
    Use ScraperAPI to render Pinterest search results for niche keywords
    and extract creator handles from pin URLs.
    """
    scraperapi_key = os.getenv("SCRAPERAPI_KEY", "")
    session = os.getenv("PINTEREST_SESSION_COOKIE", "")
    if not scraperapi_key:
        return []

    freq: dict[str, int] = {}
    search_terms = keywords[:4]  # limit API calls

    for term in search_terms:
        encoded = requests.utils.quote(term)
        url = f"https://www.pinterest.com/search/pins/?q={encoded}"
        params = {
            "api_key": scraperapi_key,
            "url": url,
            "render": "true",
            "wait": "3000",
        }
        if session:
            params["cookies"] = f"_pinterest_sess={session}"

        try:
            resp = requests.get("https://api.scraperapi.com/", params=params, timeout=90)
            html = resp.text
            # Extract handles from pin URL patterns in the rendered HTML
            handles = re.findall(r'"([a-z0-9_.-]{3,30})/[a-z0-9_-]+/\d+"', html, re.IGNORECASE)
            handles += re.findall(r'pinterest\.com/([a-z0-9_.-]{3,30})/[^"]+/\d+', html, re.IGNORECASE)
            for h in handles:
                h = h.lower()
                if h not in EXCLUDED_HANDLES and not h.isdigit() and len(h) >= 3:
                    freq[h] = freq.get(h, 0) + 1
        except Exception as e:
            print(f"  [warn] Search discovery failed for '{term}': {e}")

    # Return handles sorted by frequency (appearing in more searches = stronger competitor)
    return [h for h, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)][:15]


def is_active(profile: dict, days: int = 30) -> bool:
    """Return True if account has at least one pin within `days` days."""
    dates = profile.get("recent_pin_dates", [])
    if not dates:
        return False

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for d in dates:
        try:
            if isinstance(d, (int, float)):
                pin_dt = datetime.fromtimestamp(d, tz=timezone.utc)
            else:
                try:
                    pin_dt = datetime.fromisoformat(str(d).replace("Z", "+00:00"))
                except ValueError:
                    pin_dt = email.utils.parsedate_to_datetime(str(d))
            if pin_dt.tzinfo is None:
                pin_dt = pin_dt.replace(tzinfo=timezone.utc)
            if pin_dt >= cutoff:
                return True
        except Exception:
            continue
    return False


def has_reach(profile: dict, min_followers: int = 5_000) -> tuple[bool, str]:
    """Return (passes, reason). Uses follower count (monthly views not scrapeable)."""
    followers = profile.get("followers", 0)
    if followers > 0:
        passes = followers >= min_followers
        label = f"{followers:,} followers"
        if not passes:
            label += f" (below {min_followers:,} threshold)"
        return passes, label
    return False, "follower count unavailable"


def discover_and_filter(
    manual_handles: list[str],
    keywords: list[str],
    niche: str,
    top_n: int = 5,
) -> list[dict]:
    """
    Discover competitors from manual list + auto-search, apply filters, return top_n.
    Tries to find at least top_n passing accounts by scanning up to 20 candidates.
    """
    print("\n[6/9] Competitor Discovery & Filtering")

    # Auto-discover from keyword searches
    print(f"  Auto-discovering competitors from Pinterest search...")
    auto_handles = discover_via_search(keywords, niche)
    print(f"  Found {len(auto_handles)} auto-discovered candidates")

    # Manual first, then auto-discovered (deduped)
    candidate_handles = list(dict.fromkeys(manual_handles + auto_handles))
    print(f"  Total candidates to check: {len(candidate_handles)} ({len(manual_handles)} manual + {len(auto_handles)} auto)")

    passing = []
    failed_active = []
    failed_reach = []
    checked = 0
    max_check = max(20, top_n * 4)  # check up to 20 to find 5

    for handle in candidate_handles:
        if len(passing) >= top_n or checked >= max_check:
            break
        checked += 1
        print(f"  [{checked}] Scraping @{handle}...")
        profile = scrape_profile(handle)
        if not profile:
            print(f"    → Could not scrape")
            continue

        active = is_active(profile)
        reach_ok, reach_reason = has_reach(profile)
        last_pin = profile["recent_pin_dates"][0][:10] if profile.get("recent_pin_dates") else "unknown"

        if active and reach_ok:
            print(f"    ✓ PASS — {reach_reason}, last pin: {last_pin}")
            passing.append(profile)
        else:
            reasons = []
            if not active:
                reasons.append(f"inactive (last pin: {last_pin})")
                failed_active.append(handle)
            if not reach_ok:
                reasons.append(reach_reason)
                failed_reach.append(handle)
            print(f"    ✗ FAIL — {', '.join(reasons)}")

    # Sort by follower count descending
    passing.sort(key=lambda p: p.get("followers", 0), reverse=True)
    result = passing[:top_n]

    print(f"\n  Competitors passing filters: {len(result)}/{checked} checked")
    if result:
        for r in result:
            print(f"    @{r['username']} — {r.get('followers', 0):,} followers")

    return result
