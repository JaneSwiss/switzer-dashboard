#!/usr/bin/env python3
"""
Push all unpublished posts to Wix as drafts.

Checks existing Wix drafts first (by title) — updates rather than creates
when a match is found, so no duplicates appear in the Wix dashboard.

Usage:
    python3 agents/blog-seo-agent/batch_publish_drafts.py
    python3 agents/blog-seo-agent/batch_publish_drafts.py --dry-run
    python3 agents/blog-seo-agent/batch_publish_drafts.py --slug coaching-business
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = Path(__file__).resolve().parent
POSTS_DIR = ROOT / "posts"
DASHBOARD = ROOT / "dashboard_data.json"
DRAFT_MAP_PATH = AGENT_DIR / "wix_draft_id_map.json"

load_dotenv(ROOT / ".env")

WIX_API_KEY = os.getenv("WIX_API_KEY", "")
WIX_SITE_ID = os.getenv("WIX_SITE_ID", "")
WIX_MEMBER_ID = os.getenv("WIX_MEMBER_ID", "")
WIX_API_BASE = "https://www.wixapis.com"

sys.path.insert(0, str(AGENT_DIR))
from publish_to_wix import extract_post_content, convert_html_to_ricos, create_draft_post, update_draft_post


def _headers() -> dict:
    return {
        "Authorization": WIX_API_KEY,
        "wix-site-id": WIX_SITE_ID,
        "Content-Type": "application/json",
    }


def _keyword_to_slug(keyword: str) -> str:
    return keyword.strip().lower().replace(" ", "-")


def get_existing_wix_drafts() -> dict[str, str]:
    """Return {title_lower: draft_id} for all current Wix drafts."""
    drafts = {}
    cursor = None
    while True:
        params: dict = {"limit": 100}
        if cursor:
            params["paging.cursor"] = cursor
        resp = requests.get(
            f"{WIX_API_BASE}/blog/v3/draft-posts",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        if not resp.ok:
            print(f"  Warning: could not list Wix drafts ({resp.status_code}) — will create new drafts.")
            break
        data = resp.json()
        for d in data.get("draftPosts", []):
            title = d.get("title", "").strip().lower()
            if title:
                drafts[title] = d["id"]
        meta = data.get("metaData", {})
        cursor = meta.get("cursor")
        if not cursor or not data.get("draftPosts"):
            break
    return drafts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--slug", help="Push a single post by slug instead of all unpublished")
    args = parser.parse_args()

    if not all([WIX_API_KEY, WIX_SITE_ID, WIX_MEMBER_ID]):
        print("ERROR: WIX_API_KEY, WIX_SITE_ID, WIX_MEMBER_ID must all be set in .env")
        sys.exit(1)

    with open(DASHBOARD) as f:
        dashboard = json.load(f)
    posts = dashboard.get("blog_seo_agent", {}).get("posts", [])

    if args.slug:
        targets = [args.slug]
    else:
        targets = [
            _keyword_to_slug(p["keyword"])
            for p in posts
            if p.get("keyword") and not p.get("published")
        ]

    print(f"{len(targets)} unpublished posts to push\n")

    if args.dry_run:
        for slug in targets:
            exists = (POSTS_DIR / f"{slug}.html").exists()
            print(f"  {'OK ' if exists else 'MISS'} {slug}")
        print("\n(dry run — nothing pushed)")
        return

    print("Fetching existing Wix drafts to avoid duplicates...")
    existing = get_existing_wix_drafts()
    print(f"Found {len(existing)} existing Wix drafts\n")

    # Load or init local draft_id map
    draft_map: dict[str, str] = {}
    if DRAFT_MAP_PATH.exists():
        with open(DRAFT_MAP_PATH) as f:
            draft_map = json.load(f)

    results: dict[str, list[str]] = {"created": [], "updated": [], "skipped": [], "failed": []}

    for i, slug in enumerate(targets, 1):
        html_path = POSTS_DIR / f"{slug}.html"
        if not html_path.exists():
            print(f"[{i}/{len(targets)}] SKIP  {slug}  (no HTML file)")
            results["skipped"].append(slug)
            continue

        print(f"[{i}/{len(targets)}] {slug} ...", end=" ", flush=True)

        try:
            title, body_html = extract_post_content(html_path)
            rich_content = convert_html_to_ricos(body_html)

            # Check for existing draft by title or previously-saved draft_id
            existing_id = existing.get(title.strip().lower()) or draft_map.get(slug)

            if existing_id:
                update_draft_post(existing_id, title, rich_content)
                draft_map[slug] = existing_id
                print(f"updated  id={existing_id[:8]}…")
                results["updated"].append(slug)
            else:
                result = create_draft_post(title, rich_content)
                new_id = result.get("draftPost", {}).get("id", "unknown")
                draft_map[slug] = new_id
                print(f"created  id={new_id[:8]}…")
                results["created"].append(slug)

        except Exception as e:
            print(f"FAILED — {e}")
            results["failed"].append(slug)

        # Persist draft_id map after every post (safe against interruption)
        with open(DRAFT_MAP_PATH, "w") as f:
            json.dump(draft_map, f, indent=2)

        if i < len(targets):
            time.sleep(2)

    print("\n" + "=" * 56)
    print(f"Created: {len(results['created'])}  Updated: {len(results['updated'])}  "
          f"Skipped: {len(results['skipped'])}  Failed: {len(results['failed'])}")
    if results["failed"]:
        print(f"Failed: {', '.join(results['failed'])}")
    print(f"\nDraft IDs saved → {DRAFT_MAP_PATH}")
    print("Next step: Wix Blog dashboard → Drafts → publish all.")


if __name__ == "__main__":
    main()
