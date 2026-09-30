#!/usr/bin/env python3
"""
Find all unscheduled Tailwind pin drafts and assign them real send times.

Uses 4 daily slots in Sydney time (9am / 1pm / 5pm / 8pm), starting after
the latest already-scheduled post. Pins go live automatically once Tailwind
SmartSchedule is turned on — no manual scheduling needed.

Usage:
    python3 agents/blog-seo-agent/reschedule_tailwind_drafts.py
    python3 agents/blog-seo-agent/reschedule_tailwind_drafts.py --dry-run
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT / "skills" / "creative-designer"))
from tailwind_client import (
    BASE_URL, _headers, _get_account_id,
    _schedule_start, _slot_sequence,
)


def get_draft_posts(account_id: str) -> list[dict]:
    """Return all unscheduled/draft pins (no sendAt)."""
    drafts = []
    page = 1
    while True:
        resp = requests.get(
            f"{BASE_URL}/accounts/{account_id}/posts",
            headers=_headers(),
            params={"status": "draft", "limit": 100, "page": page},
            timeout=15,
        )
        if not resp.ok:
            # Some Tailwind plans use different status names — try 'unscheduled'
            if page == 1:
                resp2 = requests.get(
                    f"{BASE_URL}/accounts/{account_id}/posts",
                    headers=_headers(),
                    params={"status": "unscheduled", "limit": 100},
                    timeout=15,
                )
                if resp2.ok:
                    return resp2.json().get("data", {}).get("posts", [])
            print(f"  Warning: could not list draft posts ({resp.status_code})")
            break
        data = resp.json().get("data", {}).get("posts", [])
        if not data:
            break
        drafts.extend(data)
        page += 1
    return drafts


def reschedule_post(account_id: str, post_id: str, send_at: str) -> bool:
    """PATCH a single Tailwind post to set its sendAt."""
    resp = requests.patch(
        f"{BASE_URL}/accounts/{account_id}/posts/{post_id}",
        headers=_headers(),
        json={"sendAt": send_at},
        timeout=15,
    )
    return resp.status_code in (200, 201, 204)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("TAILWIND_API_KEY", "")
    if not api_key:
        print("ERROR: TAILWIND_API_KEY not set in .env")
        sys.exit(1)

    print("Getting Tailwind account...")
    try:
        account_id = _get_account_id()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print("Fetching unscheduled draft pins...")
    drafts = get_draft_posts(account_id)
    print(f"Found {len(drafts)} unscheduled drafts\n")

    if not drafts:
        print("Nothing to reschedule.")
        return

    start_utc = _schedule_start(account_id)
    slots = _slot_sequence(start_utc)

    success = 0
    failed = 0

    for i, post in enumerate(drafts, 1):
        post_id = post.get("id") or post.get("postId", "")
        title = post.get("title", "")[:60] or f"pin-{post_id}"
        slot_utc = next(slots)
        send_at = slot_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        sydney_str = slot_utc.astimezone(
            __import__("zoneinfo").ZoneInfo("Australia/Sydney")
        ).strftime("%d %b %Y, %I:%M %p AEST")

        if args.dry_run:
            print(f"  [{i}/{len(drafts)}] DRY-RUN  {title!r}  → {sydney_str}")
            continue

        print(f"  [{i}/{len(drafts)}] {title!r}  → {sydney_str} ...", end=" ", flush=True)
        ok = reschedule_post(account_id, post_id, send_at)
        if ok:
            print("✓")
            success += 1
        else:
            print("FAILED")
            failed += 1

        if i < len(drafts):
            time.sleep(0.5)

    if not args.dry_run:
        print(f"\nScheduled: {success}  Failed: {failed}")
        if success > 0:
            days_needed = -(-success // 4)  # ceil(success / 4 slots per day)
            print(f"{success} pins will post over the next ~{days_needed} days at 10/day.")
            print("\nIMPORTANT: Make sure Tailwind SmartSchedule is ON:")
            print("  Tailwind → Publisher → SmartSchedule → enable 4 time slots")


if __name__ == "__main__":
    main()
