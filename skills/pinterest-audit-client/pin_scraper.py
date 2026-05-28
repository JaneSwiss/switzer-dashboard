"""
pin_scraper.py — Apify wrapper for Pinterest search and profile scraping.
Uses authenticated Pinterest session cookie to get real search results.
"""

from __future__ import annotations
import os
import time
import json
import requests

APIFY_BASE = "https://api.apify.com/v2"

# Highest-rated Pinterest actors by run count
SEARCH_ACTOR = "NagEuvONHQtmNhnle"   # Pinterest search
PROFILE_ACTOR = "aHEQvMMnwyRWtDBnb"  # Pinterest profile scraper


def _start_actor(actor_id: str, input_data: dict, api_key: str) -> str | None:
    """Start an Apify actor run and return the run ID."""
    url = f"{APIFY_BASE}/acts/{actor_id}/runs"
    headers = {"Content-Type": "application/json"}
    params = {"token": api_key}
    try:
        resp = requests.post(url, headers=headers, params=params, json=input_data, timeout=30)
        resp.raise_for_status()
        return resp.json()["data"]["id"]
    except Exception as e:
        print(f"  [warn] Failed to start actor {actor_id}: {e}")
        return None


def _poll_run(run_id: str, api_key: str, timeout: int = 120) -> dict | None:
    """Poll until actor run completes. Returns dataset items or None on timeout/failure."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(
                f"{APIFY_BASE}/actor-runs/{run_id}",
                params={"token": api_key},
                timeout=15,
            )
            status = resp.json()["data"]["status"]
            if status == "SUCCEEDED":
                dataset_id = resp.json()["data"]["defaultDatasetId"]
                items_resp = requests.get(
                    f"{APIFY_BASE}/datasets/{dataset_id}/items",
                    params={"token": api_key, "format": "json"},
                    timeout=30,
                )
                return items_resp.json()
            elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                print(f"  [warn] Actor run {run_id} ended with status: {status}")
                return None
        except Exception as e:
            print(f"  [warn] Poll error: {e}")
        time.sleep(5)
    print(f"  [warn] Actor run {run_id} timed out after {timeout}s")
    return None


def _build_cookies() -> list[dict]:
    """Build cookie array for Apify actors from env Pinterest session."""
    session = os.getenv("PINTEREST_SESSION_COOKIE", "")
    if not session:
        return []
    return [
        {"name": "_pinterest_sess", "value": session, "domain": ".pinterest.com", "path": "/"},
    ]


def search_pins(keyword: str, max_items: int = 5) -> list[dict]:
    """Search Pinterest for pins matching keyword. Returns structured pin list."""
    api_key = os.getenv("APIFY_API_KEY", "")
    if not api_key:
        print("  [warn] No APIFY_API_KEY — skipping pin search")
        return []

    cookies = _build_cookies()
    input_data = {
        "searchQuery": keyword,
        "maxItems": max_items,
        "type": "pins",
    }
    if cookies:
        input_data["cookies"] = cookies

    run_id = _start_actor(SEARCH_ACTOR, input_data, api_key)
    if not run_id:
        return []

    items = _poll_run(run_id, api_key, timeout=120)
    if not items:
        return []

    pins = []
    for item in items[:max_items]:
        pin = {
            "title": item.get("title") or item.get("grid_title") or "",
            "description": item.get("description") or "",
            "url": item.get("link") or item.get("url") or "",
            "pin_url": f"https://www.pinterest.com/pin/{item.get('id', '')}/",
            "domain": item.get("domain") or "",
            "created_at": item.get("created_at") or item.get("createdAt") or "",
            "saves": item.get("save_count") or item.get("saveCount") or 0,
            "image_url": (item.get("images") or {}).get("orig", {}).get("url", ""),
        }
        pins.append(pin)
    return pins


def scrape_profile(username: str) -> dict | None:
    """
    Scrape a Pinterest profile using ScraperAPI with the session cookie.
    Renders the page as a logged-in user so monthly views are visible.
    """
    scraperapi_key = os.getenv("SCRAPERAPI_KEY", "")
    session = os.getenv("PINTEREST_SESSION_COOKIE", "")

    if not scraperapi_key:
        print("  [warn] No SCRAPERAPI_KEY — skipping profile scrape")
        return None

    import re

    profile_url = f"https://www.pinterest.com/{username}/"
    created_url = f"https://www.pinterest.com/{username}/_created/"

    def render(url: str) -> str:
        # Pass session cookie via ScraperAPI's cookies param (keep_headers causes 500)
        params = {
            "api_key": scraperapi_key,
            "url": url,
            "render": "true",
            "wait": "4000",
        }
        if session:
            params["cookies"] = f"_pinterest_sess={session}"
        try:
            resp = requests.get("https://api.scraperapi.com/", params=params, timeout=90)
            return resp.text if resp.status_code == 200 else ""
        except Exception as e:
            print(f"  [warn] ScraperAPI render failed for {url}: {e}")
            return ""

    print(f"    Rendering profile page...")
    html = render(profile_url)

    if not html or len(html) < 1000:
        print(f"  [warn] Empty response for @{username}")
        return None

    # --- Monthly views ---
    # Pinterest only renders monthly views in fully interactive browser sessions.
    # ScraperAPI headless rendering does not capture it — use follower_count as proxy.
    monthly_views = -1  # sentinel: not captured (distinct from 0)
    monthly_views_raw = "not captured"

    # --- Followers ---
    followers = 0
    for pattern in [
        r'"follower_count"\s*:\s*(\d+)',
        r'([\d.,]+[MKmk]?)\s*[Ff]ollower',
        r'"followers?"\s*:\s*(\d+)',
    ]:
        m = re.search(pattern, html)
        if m:
            followers = _parse_count(m.group(1).strip())
            break

    # --- Bio ---
    bio = ""
    for pattern in [
        r'"about"\s*:\s*"([^"]{5,200})"',
        r'"biography"\s*:\s*"([^"]{5,200})"',
        r'"description"\s*:\s*"([^"]{5,200})"',
    ]:
        m = re.search(pattern, html)
        if m:
            bio = m.group(1)
            break

    # --- Boards (extract board slugs from profile page links) ---
    SKIP = {"_created", "_saved", "pins", "following", "followers", "shop", "_videos"}
    board_slugs = re.findall(
        rf'href="/{re.escape(username)}/([^/"]+)/"',
        html,
        re.IGNORECASE,
    )
    boards = []
    seen = set()
    for slug in board_slugs:
        slug_clean = slug.split("?")[0]  # strip query strings
        if slug_clean in SKIP or slug_clean in seen or slug_clean.startswith("_"):
            continue
        seen.add(slug_clean)
        boards.append({
            "name": slug_clean.replace("-", " ").replace("%2b", "+").title(),
            "description": "",
            "pin_count": 0,
        })
    boards = boards[:12]

    # --- Recent pin dates (from created tab) ---
    print(f"    Rendering created-pins tab...")
    created_html = render(created_url)
    pin_dates = []
    if created_html:
        # Confirmed working: ISO datetime strings in the rendered page
        dates_found = re.findall(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", created_html)
        if not dates_found:
            dates_found = re.findall(r"(\d{4}-\d{2}-\d{2})", created_html)
        # Sort descending (most recent first), deduplicate
        pin_dates = sorted(dict.fromkeys(dates_found), reverse=True)[:5]

    return {
        "username": username,
        "followers": followers,
        "monthly_views": monthly_views,
        "monthly_views_raw": monthly_views_raw,
        "bio": bio,
        "boards": boards,
        "recent_pins": [],
        "recent_pin_dates": pin_dates,
    }


def _parse_count(value) -> int:
    """Parse Pinterest display counts like '2.2M', '14.3K', or raw ints."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    s = str(value).strip().upper().replace(",", "")
    try:
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        if s.endswith("K"):
            return int(float(s[:-1]) * 1_000)
        return int(float(s))
    except (ValueError, AttributeError):
        return 0
