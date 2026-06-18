#!/usr/bin/env python3
"""
Publish a blog-seo-agent HTML output to Wix as a DRAFT post.

Replaces the manual "duplicate old post, paste new text, reformat" workflow.
The post lands in your Wix Blog dashboard as a draft, fully formatted and
ready to review. Nothing is auto-published — you still click Publish in Wix.

Run with:
    python3 agents/blog-seo-agent/publish_to_wix.py <slug>

Examples:
    python3 agents/blog-seo-agent/publish_to_wix.py branding-for-business

One-time setup (add to .env):
    WIX_API_KEY    — generated from Wix dashboard > Settings > API Keys
    WIX_SITE_ID    — from the dashboard URL: manage.wix.com/dashboard/<SITE_ID>/home
    WIX_MEMBER_ID  — your member ID as site owner (run find_wix_member_id.py once to get this)
"""

import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = AGENT_DIR / "output"
POSTS_DIR = ROOT / "posts"

load_dotenv(ROOT / ".env")

WIX_API_KEY = os.getenv("WIX_API_KEY", "")
WIX_SITE_ID = os.getenv("WIX_SITE_ID", "")
WIX_MEMBER_ID = os.getenv("WIX_MEMBER_ID", "")

WIX_API_BASE = "https://www.wixapis.com"


def _headers() -> dict:
    return {
        "Authorization": WIX_API_KEY,
        "wix-site-id": WIX_SITE_ID,
        "Content-Type": "application/json",
    }


def find_html_file(slug: str) -> Path:
    for directory in (OUTPUT_DIR, POSTS_DIR):
        candidate = directory / f"{slug}.html"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No HTML file found for slug '{slug}' in {OUTPUT_DIR} or {POSTS_DIR}"
    )


def extract_post_content(html_path: Path) -> "tuple[str, str]":
    """Returns (title, body_html) — body_html excludes the debug image-prompts
    block and the closing comment-prompt note, which aren't real post content."""
    raw = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else html_path.stem

    post_div = soup.find("div", class_="post")
    if post_div is None:
        raise ValueError(f"Could not find <div class='post'> in {html_path}")

    # Drop the debug-only image-prompt block and the closing "leave a comment" note —
    # neither belongs in the published post.
    for unwanted_class in ("image-prompts", "closing-note"):
        for el in post_div.find_all(class_=unwanted_class):
            el.decompose()

    # Drop the H1 — Wix uses the draft post's `title` field for this, so leaving
    # it in the body would duplicate the heading on the live page.
    h1 = post_div.find("h1")
    if h1:
        h1.decompose()

    body_html = "".join(str(child) for child in post_div.children).strip()
    return title, body_html


def convert_html_to_ricos(body_html: str) -> dict:
    """Calls Wix's Convert-to-Ricos-Document endpoint to turn plain HTML
    into the rich-content format the Draft Posts API requires."""
    resp = requests.post(
        f"{WIX_API_BASE}/ricos/v1/ricos-document/convert/to-ricos",
        headers=_headers(),
        json={"html": body_html},
        timeout=30,
    )
    if not resp.ok:
        print(f"Ricos conversion error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    return resp.json()["document"]


def create_draft_post(title: str, rich_content: dict) -> dict:
    payload = {
        "draftPost": {
            "title": title,
            "richContent": rich_content,
            "memberId": WIX_MEMBER_ID,
        },
        "publish": False,  # always create as draft — Jane reviews and publishes manually
    }
    resp = requests.post(
        f"{WIX_API_BASE}/blog/v3/draft-posts",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    if not resp.ok:
        print(f"Wix API error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    return resp.json()


def publish(slug: str) -> None:
    if not (WIX_API_KEY and WIX_SITE_ID and WIX_MEMBER_ID):
        print("Missing WIX_API_KEY, WIX_SITE_ID, or WIX_MEMBER_ID in .env — see setup steps in this file's docstring.")
        sys.exit(1)

    html_path = find_html_file(slug)
    print(f"Reading {html_path}")

    title, body_html = extract_post_content(html_path)
    print(f"Title: {title}")

    print("Converting content to Wix rich-content format...")
    rich_content = convert_html_to_ricos(body_html)

    print("Creating draft post in Wix...")
    result = create_draft_post(title, rich_content)

    draft = result.get("draftPost", {})
    draft_id = draft.get("id", "unknown")
    print(f"\nDraft created: {draft_id}")
    print(f"Open your Wix Blog dashboard > Drafts to review and publish '{title}'.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 publish_to_wix.py <slug>")
        sys.exit(1)
    publish(sys.argv[1])
