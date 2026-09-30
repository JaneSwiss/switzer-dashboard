#!/usr/bin/env python3
"""
Map local post slugs to their real Wix-assigned slugs.

Wix sometimes changes slugs at publish time (e.g. it appends a number or
shortens a title), so pins built against our internal slugs hit 404 pages.
This script queries the live Wix blog, matches posts by title, writes
posts/wix_slug_map.json, and prints every URL mismatch that needs fixing.

Usage:
    python3 agents/blog-seo-agent/reconcile_wix_slugs.py
"""
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
POSTS_DIR = ROOT / "posts"
SLUG_MAP_PATH = POSTS_DIR / "wix_slug_map.json"

load_dotenv(ROOT / ".env")

WIX_API_KEY = os.getenv("WIX_API_KEY", "")
WIX_SITE_ID = os.getenv("WIX_SITE_ID", "")
WIX_API_BASE = "https://www.wixapis.com"


def _headers() -> dict:
    return {
        "Authorization": WIX_API_KEY,
        "wix-site-id": WIX_SITE_ID,
        "Content-Type": "application/json",
    }


def _norm(text: str) -> str:
    return text.lower().strip().replace("-", " ").replace("_", " ")


def fetch_published_posts() -> list[dict]:
    posts = []
    cursor = None
    while True:
        params: dict = {"fieldsets": ["URL"], "limit": 100}
        if cursor:
            params["paging.cursor"] = cursor
        resp = requests.get(
            f"{WIX_API_BASE}/blog/v3/posts",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        if not resp.ok:
            print(f"ERROR: Wix API {resp.status_code}: {resp.text[:300]}")
            sys.exit(1)
        data = resp.json()
        batch = data.get("posts", [])
        posts.extend(batch)
        print(f"  {len(posts)} posts fetched…", end="\r")
        cursor = data.get("metaData", {}).get("cursor")
        if not cursor or not batch:
            break
    print()
    return posts


def main() -> None:
    if not all([WIX_API_KEY, WIX_SITE_ID]):
        print("ERROR: WIX_API_KEY and WIX_SITE_ID must be set in .env")
        sys.exit(1)

    print("Fetching published posts from Wix Blog API...")
    wix_posts = fetch_published_posts()
    print(f"Found {len(wix_posts)} live posts\n")

    # Index Wix posts by slug and by normalised title
    by_slug: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    for p in wix_posts:
        slug = p.get("slug", "")
        title = p.get("title", "")
        if slug:
            by_slug[slug] = p
        if title:
            by_title[_norm(title)] = p

    local_slugs = sorted(f.stem for f in POSTS_DIR.glob("*.html"))
    slug_map: dict[str, dict] = {}
    mismatches: list[dict] = []
    not_on_wix: list[str] = []

    for local_slug in local_slugs:
        # 1. Exact slug match
        if local_slug in by_slug:
            p = by_slug[local_slug]
            wix_slug = p.get("slug", "")
            url_obj = p.get("url", {})
            wix_url = (url_obj.get("base", "") + url_obj.get("path", "")).rstrip("/") or ""
            slug_map[local_slug] = {
                "wix_id": p.get("id"),
                "wix_slug": wix_slug,
                "wix_url": wix_url,
                "title": p.get("title"),
                "match": "exact",
            }
            continue

        # 2. Title match (slug-as-words vs Wix title)
        slug_words = local_slug.replace("-", " ")
        if slug_words in by_title:
            p = by_title[slug_words]
            wix_slug = p.get("slug", "")
            url_obj = p.get("url", {})
            wix_url = (url_obj.get("base", "") + url_obj.get("path", "")).rstrip("/") or ""
            slug_map[local_slug] = {
                "wix_id": p.get("id"),
                "wix_slug": wix_slug,
                "wix_url": wix_url,
                "title": p.get("title"),
                "match": "title_fuzzy",
            }
            if wix_slug and wix_slug != local_slug:
                mismatches.append({
                    "local_slug": local_slug,
                    "wix_slug": wix_slug,
                    "pins_point_to": f"https://www.switzertemplates.com/post/{local_slug}",
                    "correct_url": wix_url,
                })
            continue

        # 3. Not found on Wix (draft or never published)
        slug_map[local_slug] = {
            "wix_id": None, "wix_slug": None,
            "wix_url": None, "title": None,
            "match": "not_found",
        }
        not_on_wix.append(local_slug)

    with open(SLUG_MAP_PATH, "w") as f:
        json.dump(slug_map, f, indent=2)

    live = sum(1 for v in slug_map.values() if v["wix_id"])
    print(f"Results: {live} matched on Wix | {len(not_on_wix)} not yet live\n")
    print(f"Slug map saved → {SLUG_MAP_PATH}")

    if mismatches:
        print(f"\n{'='*56}")
        print(f"BROKEN PIN URLS — {len(mismatches)} posts where Wix changed the slug:")
        for m in mismatches:
            print(f"\n  Local slug : {m['local_slug']}")
            print(f"  Wix slug   : {m['wix_slug']}")
            print(f"  Pins use   : {m['pins_point_to']}")
            print(f"  Should be  : {m['correct_url']}")
        print(f"\nUpdate these {len(mismatches)} destination URLs in Tailwind to stop 404 traffic leaks.")
    else:
        print("\nAll pin URLs match live Wix slugs — no broken URLs found.")

    if not_on_wix:
        print(f"\nNot yet on Wix ({len(not_on_wix)} posts — run batch_publish_drafts.py):")
        for s in not_on_wix:
            print(f"  {s}")


if __name__ == "__main__":
    main()
