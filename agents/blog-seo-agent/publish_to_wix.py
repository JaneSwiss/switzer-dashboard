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
    # POSTS_DIR (the current, actively-written location) is checked first — OUTPUT_DIR
    # is a legacy folder that, for a handful of older slugs, still holds a stale copy.
    for directory in (POSTS_DIR, OUTPUT_DIR):
        candidate = directory / f"{slug}.html"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No HTML file found for slug '{slug}' in {POSTS_DIR} or {OUTPUT_DIR}"
    )


def extract_post_content(html_path: Path) -> "tuple[str, str]":
    """Returns (title, body_html), Wix-ready:
    - the debug image-prompts block and the closing comment-prompt note are dropped
    - the 3 cover-image candidates are dropped entirely — Jane sets the actual Wix
      cover image herself from the folder linked in the completion email
    - each inline section image gets replaced with a short, clean placeholder naming
      the exact file to drop in, since local image paths mean nothing to Wix's servers
    """
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

    _strip_images_for_wix(post_div, soup)

    _insert_spacer_paragraphs(post_div, soup)

    body_html = "".join(str(child) for child in post_div.children).strip()
    return title, body_html


def _strip_images_for_wix(post_div, soup: BeautifulSoup) -> None:
    """Local image paths (images/{slug}/cover-N.jpg, inline-N.jpg) mean nothing on
    Wix's servers — there's no local filesystem for them to resolve against. Cover
    images are dropped outright (Jane picks + sets one herself, from the folder
    linked in the completion email). Inline images become a short placeholder
    naming the exact file, so the manual drop-in is fast and unambiguous."""
    # Cover images share one wrapper div — collect the unique parents first and
    # decompose each once, rather than decomposing mid-iteration (which would leave
    # later img tags in that same now-destroyed div dangling).
    cover_parents = []
    for img in post_div.find_all("img"):
        if "/cover-" in img.get("src", ""):
            parent = img.find_parent("div")
            target = parent if parent is not None else img
            if target not in cover_parents:
                cover_parents.append(target)
    for parent in cover_parents:
        parent.decompose()

    # Remaining images (inline section illustrations) each become a short placeholder.
    for img in post_div.find_all("img"):
        src = img.get("src", "")
        if "/inline-" not in src:
            continue
        filename = src.rsplit("/", 1)[-1]
        placeholder = soup.new_tag(
            "p",
            attrs={"style": "background:#f7f5f2;border-radius:4px;padding:0.75rem 1rem;"
                            "color:#8d6e63;font-style:italic;"},
        )
        placeholder.string = f"[Insert {filename} here — folder linked in this week's completion email]"
        img.replace_with(placeholder)


def _insert_spacer_paragraphs(post_div, soup: BeautifulSoup) -> None:
    """Wix's blog editor applies no built-in margin between consecutive
    paragraph/list/heading blocks (confirmed: converted paragraphData is always
    empty — Wix relies on default theme spacing, which is much tighter than the
    local HTML preview's CSS). Without this, short label-style paragraphs
    (e.g. "<p><strong>Her Pinterest setup:</strong></p>") stack directly against
    the next block with no visual gap, which is exactly what was showing up
    squished in the Wix drafts. A blank paragraph between every block-level
    child reproduces what manually pressing Enter in the Wix editor does."""
    children = [c for c in post_div.find_all(recursive=False)]
    for child in reversed(children[:-1]):
        spacer = soup.new_tag("p")
        spacer.append(" ")
        child.insert_after(spacer)


RICOS_MAX_CHARS = 29000  # Wix's hard limit is 30,000 — leave a safety margin


def _chunk_html_blocks(body_html: str, max_chars: int = RICOS_MAX_CHARS) -> "list[str]":
    """Splits body HTML into chunks under Wix's per-request character limit,
    breaking only at top-level block boundaries (never mid-tag) so each chunk
    is valid, self-contained HTML."""
    soup = BeautifulSoup(body_html, "html.parser")
    blocks = [str(c) for c in soup.find_all(recursive=False)]

    chunks, current = [], ""
    for block in blocks:
        if current and len(current) + len(block) > max_chars:
            chunks.append(current)
            current = block
        else:
            current += block
    if current:
        chunks.append(current)
    return chunks


def convert_html_to_ricos(body_html: str) -> dict:
    """Calls Wix's Convert-to-Ricos-Document endpoint to turn plain HTML
    into the rich-content format the Draft Posts API requires. Chunks the
    request when the post is long enough to exceed Wix's 30,000-character
    per-request limit, then merges the resulting node lists into one document."""
    chunks = _chunk_html_blocks(body_html) if len(body_html) > RICOS_MAX_CHARS else [body_html]

    merged_nodes = []
    document_meta = None
    for i, chunk in enumerate(chunks):
        resp = requests.post(
            f"{WIX_API_BASE}/ricos/v1/ricos-document/convert/to-ricos",
            headers=_headers(),
            json={"html": chunk},
            timeout=30,
        )
        if not resp.ok:
            print(f"Ricos conversion error (chunk {i+1}/{len(chunks)}) {resp.status_code}: {resp.text}")
            resp.raise_for_status()
        doc = resp.json()["document"]
        merged_nodes.extend(doc.get("nodes", []))
        if document_meta is None:
            document_meta = {k: v for k, v in doc.items() if k != "nodes"}

    if len(chunks) > 1:
        print(f"  Converted in {len(chunks)} chunks ({len(body_html):,} chars total) — merged into one document.")
    return {**(document_meta or {}), "nodes": merged_nodes}


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


def update_draft_post(draft_id: str, title: str, rich_content: dict) -> dict:
    resp = requests.patch(
        f"{WIX_API_BASE}/blog/v3/draft-posts/{draft_id}",
        headers=_headers(),
        json={"draftPost": {"id": draft_id, "title": title, "richContent": rich_content}},
        timeout=30,
    )
    if not resp.ok:
        print(f"Wix API error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    return resp.json()


def publish(slug: str, draft_id: str = None) -> None:
    if not (WIX_API_KEY and WIX_SITE_ID and WIX_MEMBER_ID):
        print("Missing WIX_API_KEY, WIX_SITE_ID, or WIX_MEMBER_ID in .env — see setup steps in this file's docstring.")
        sys.exit(1)

    html_path = find_html_file(slug)
    print(f"Reading {html_path}")

    title, body_html = extract_post_content(html_path)
    print(f"Title: {title}")

    print("Converting content to Wix rich-content format...")
    rich_content = convert_html_to_ricos(body_html)

    if draft_id:
        print(f"Updating existing draft {draft_id} in Wix...")
        update_draft_post(draft_id, title, rich_content)
        print(f"\nDraft updated: {draft_id}")
    else:
        print("Creating draft post in Wix...")
        result = create_draft_post(title, rich_content)
        draft_id = result.get("draftPost", {}).get("id", "unknown")
        print(f"\nDraft created: {draft_id}")
    print(f"Open your Wix Blog dashboard > Drafts to review and publish '{title}'.")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("Usage: python3 publish_to_wix.py <slug> [existing_draft_id]")
        sys.exit(1)
    publish(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None)
