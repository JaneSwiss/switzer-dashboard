#!/usr/bin/env python3
"""
Analyze and Recommend — General Manager, Step 1

Runs weekly (launchd). Pulls Search Console + GA4 + Wix Analytics + Pinterest performance,
picks this week's candidate keywords (trending first, falling back to the static Priority
Tier order), and opens a GitHub issue with the full recommendation for Jane to respond to.
Does NOT write anything — that only happens in Step 2, after she's replied.

Run:
    python3 agents/general-manager/analyze_and_recommend.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent
ROOT = AGENT_DIR.parents[1]
LOGS_DIR = AGENT_DIR / "logs"
PENDING_FILE = LOGS_DIR / "pending_recommendation.json"
KEYWORDS_FILE = ROOT / "agents" / "blog-seo-agent" / "keywords" / "switzertemplates_keyword_masterlist.csv"
DASHBOARD_FILE = ROOT / "dashboard_data.json"

sys.path.insert(0, str(AGENT_DIR))
sys.path.insert(0, str(ROOT / "skills" / "pinterest-agent"))

load_dotenv(ROOT / ".env")
PINTEREST_ACCESS_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "")

POSTS_PER_WEEK = int(os.getenv("POSTS_PER_WEEK", "2"))


def _slugify(text: str) -> str:
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def _static_priority_candidates(count: int, exclude: "set[str]") -> "list[str]":
    """Same tier-sort logic as blog_seo_agent.load_next_keyword(), returning the top
    `count` not-yet-written, not-already-selected keywords instead of just one."""
    if not KEYWORDS_FILE.exists():
        return []

    posts_dir = ROOT / "posts"
    written_slugs = {p.stem for p in posts_dir.glob("*.html")} if posts_dir.exists() else set()

    rows = []
    with KEYWORDS_FILE.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {k.strip(): (v or "").strip() for k, v in row.items()}
            keyword = row.get("Keyword", "")
            if not keyword or _slugify(keyword) in written_slugs or keyword.lower() in exclude:
                continue
            rows.append(row)

    tier_order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    tier_col = next((k for k in rows[0] if "tier" in k.lower() or "priority" in k.lower()), None) if rows else None
    rows.sort(key=lambda r: tier_order.get(r.get(tier_col, "P4")[:2].upper(), 9) if tier_col else 9)

    return [r["Keyword"] for r in rows[:count]]


def pick_candidates(trending: "list[str]", count: int) -> "list[dict]":
    candidates = []
    seen = set()

    for kw in trending:
        if len(candidates) >= count:
            break
        candidates.append({"keyword": kw, "reasoning": "trending — rising impressions on Search Console this week"})
        seen.add(kw.lower())

    remaining = count - len(candidates)
    if remaining > 0:
        for kw in _static_priority_candidates(remaining, exclude=seen):
            candidates.append({"keyword": kw, "reasoning": "next in your priority list"})

    return candidates


def _fetch_pin_performance() -> dict:
    try:
        from analytics_loader import fetch_pins_deep
        pins, summary = fetch_pins_deep(PINTEREST_ACCESS_TOKEN, n=10)
        return {"top_pins": pins[:5], "summary": summary}
    except Exception as e:
        print(f"  Pin performance fetch failed: {e} — continuing without it.")
        return {"top_pins": [], "summary": {"status": "error"}}


def main():
    print("=" * 50)
    print("  General Manager — Step 1: analyze and recommend")
    print("=" * 50)

    if PENDING_FILE.exists():
        try:
            pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
            if not pending.get("resolved", True):
                print("  Still waiting on last week's decision — not sending a new recommendation.")
                return
        except json.JSONDecodeError:
            pass

    import search_console_client as scc
    import ga4_client
    import wix_analytics_client
    import report_writer
    import github_issues_client

    print("\n[1/5] Pulling Search Console data...")
    try:
        gsc_data = scc.fetch_rankings()
        trending = scc.get_trending_unwritten_keywords()
    except Exception as e:
        print(f"  Search Console fetch failed: {e} — continuing without it.")
        gsc_data, trending = {}, []

    print("[2/5] Pulling GA4 data...")
    try:
        ga4_data = {
            "north_star": ga4_client.fetch_north_star_pace(),
            "per_campaign": ga4_client.fetch_sessions_by_campaign(),
        }
    except Exception as e:
        print(f"  GA4 fetch failed: {e} — continuing without it.")
        ga4_data = {}

    print("[3/5] Pulling Wix Analytics data...")
    try:
        wix_data = wix_analytics_client.fetch_sales_and_sessions()
    except Exception as e:
        print(f"  Wix Analytics fetch failed: {e} — continuing without it.")
        wix_data = {}

    print("[4/5] Pulling Pinterest pin performance...")
    pin_perf = _fetch_pin_performance()

    candidates = pick_candidates(trending, POSTS_PER_WEEK)
    if not candidates:
        print("  No candidates available (masterlist exhausted?) — nothing to recommend.")
        return

    print(f"\n  Candidates: {[c['keyword'] for c in candidates]}")

    print("\n[5/5] Writing recommendation and opening GitHub issue...")
    title, body = report_writer.write_recommendation_issue(candidates, gsc_data, ga4_data, wix_data, pin_perf)
    issue = github_issues_client.create_issue(title, body)
    print(f"  Issue created: {issue['url']}")

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_FILE.write_text(json.dumps({
        "candidates": candidates,
        "gsc_data": gsc_data,
        "ga4_data": ga4_data,
        "wix_data": wix_data,
        "issue_number": issue["number"],
        "issue_url": issue["url"],
        "sent_date": date.today().isoformat(),
        "resolved": False,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    _update_dashboard(candidates, issue["url"], ga4_data)

    print(f"\nDone. Waiting on Jane's reply at {issue['url']}")


def _update_dashboard(candidates, issue_url, ga4_data):
    try:
        data = json.loads(DASHBOARD_FILE.read_text(encoding="utf-8")) if DASHBOARD_FILE.exists() else {}
        gm = data.setdefault("general_manager", {})
        gm["status"] = "active"
        gm["last_run"] = date.today().isoformat()
        gm["awaiting_reply"] = True
        gm["candidates"] = candidates
        gm["issue_url"] = issue_url
        if ga4_data.get("north_star"):
            gm["north_star"] = ga4_data["north_star"]
        data["last_updated"] = date.today().isoformat()
        DASHBOARD_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        import subprocess
        subprocess.run(["git", "add", "dashboard_data.json"], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-m", "General Manager: weekly recommendation ready"], cwd=ROOT, check=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=ROOT, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, check=True)
        print("  Dashboard updated and pushed.")
    except Exception as e:
        print(f"  Dashboard update failed: {e} — issue is still live, just not reflected on the dashboard yet.")


if __name__ == "__main__":
    main()
