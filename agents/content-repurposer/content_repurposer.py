#!/usr/bin/env python3
"""
Content Repurposer — Switzertemplates
Takes a published blog post and turns it into:
  a) 1 email hook (subject line + preview text + body paragraph)
  b) 1 Instagram carousel (cover title + 6 slides + caption)

(Pin copy used to be generated here too, but it was never connected to the real
pin pipeline — agents/general-manager/pin_pipeline.py generates pins from the
keyword directly and is what actually reaches Tailwind. Keeping a second,
disconnected set of pin copy here just meant two different texts existed for
the same post with no way to tell which one was real. Dropped.)

Run:
  python3 agents/content-repurposer/content_repurposer.py --post <slug>
  python3 agents/content-repurposer/content_repurposer.py --all
"""

import argparse
import os
import re
import sys
from pathlib import Path

import anthropic
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
POSTS_DIR = ROOT / "posts"
OUTPUT_DIR = ROOT / "outputs" / "repurposed"
BRAND_VOICE_FILE = ROOT / "context" / "brand-voice.md"
PRODUCT_CATALOG_FILE = ROOT / "context" / "product-catalog.md"

load_dotenv(ROOT / ".env")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BLOG_BASE_URL = os.getenv("BLOG_BASE_URL", "https://www.switzertemplates.com/post")


# ── helpers ───────────────────────────────────────────────────────────────────

def extract_post_content(html_path: Path) -> dict:
    """Parse a blog post HTML file and return title + clean body text."""
    raw = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")

    # Remove image-prompts block and closing note
    for el in soup.find_all("div", class_="image-prompts"):
        el.decompose()
    for el in soup.find_all("p", class_="closing-note"):
        el.decompose()

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else html_path.stem.replace("-", " ").title()
    if h1:
        h1.decompose()

    body_text = soup.get_text(separator="\n").strip()
    # Collapse excessive blank lines
    body_text = re.sub(r"\n{3,}", "\n\n", body_text)

    return {"title": title, "body": body_text[:4000]}


def read_context() -> tuple[str, str]:
    brand_voice = BRAND_VOICE_FILE.read_text(encoding="utf-8") if BRAND_VOICE_FILE.exists() else ""
    product_catalog = PRODUCT_CATALOG_FILE.read_text(encoding="utf-8") if PRODUCT_CATALOG_FILE.exists() else ""
    return brand_voice, product_catalog


def build_prompt(post: dict, slug: str, brand_voice: str, product_catalog: str) -> str:
    post_url = f"{BLOG_BASE_URL}/{slug}"
    return f"""You are the Content Repurposer for Switzertemplates.

Your job: take one blog post and generate three types of content from it.
All content must match Switzertemplates' brand voice: practical, human, benefit-led,
short sentences, active voice, never robotic. Target audience: female small business
owners, coaches, consultants, and service providers.

BLOG POST TITLE: {post['title']}
BLOG POST URL: {post_url}
BLOG POST CONTENT:
{post['body']}

---

BRAND VOICE RULES:
{brand_voice[:1500]}

---

PRODUCT CONTEXT (reference naturally where relevant — never force it):
{product_catalog[:1000]}

---

GENERATE BOTH OUTPUTS NOW:

=== OUTPUT B: EMAIL HOOK ===
Write a complete email section to promote this blog post to the email list.
The list is 21,000 warm past buyers. Open rate is 15% — subject lines must earn the open.

Rules:
- Subject line: under 50 characters, curiosity-driven or benefit-led, never generic
- A/B subject line: a second option with a different angle
- Preview text: under 90 characters, adds to the subject — never repeats it
- Body: 150-200 words. Opens with a specific relatable situation or frustration,
  not a greeting. Gets into the content fast. One clear CTA linking to the post.
- Sign off: Xo Jane
- CTA links to: {post_url}
- Never use: "I hope you're well", "exciting news", "just wanted to share"

Format EXACTLY like this:
SUBJECT LINE: [text]
SUBJECT LINE B: [text]
PREVIEW TEXT: [text]
BODY:
[full email body]

=== OUTPUT C: INSTAGRAM CAROUSEL ===
Write a complete Instagram carousel post based on this blog post topic.
The carousel should educate and stop the scroll — not sell directly.

Rules:
- Cover slide: one punchy hook line (max 8 words), stops the scroll immediately.
  No announcing what the carousel is about — just the hook.
- Slides 1-6: one clear idea per slide, 2-3 short sentences max per slide.
  Each slide must be self-contained — a reader who only sees that slide gets value.
- Caption: 100-150 words. Opens with a one-line hook (different from the cover).
  Educates or resonates, ends with a soft CTA. No hashtag stuffing — max 5 hashtags
  at the end on a separate line.
- Brand voice: warm, direct, practical. Never preachy or motivational-poster-style.
- CAPITALISATION throughout: sentence case only. Only the first word of each sentence
  and proper nouns (Canva, Wix, Instagram, Pinterest, Etsy, etc.) are capitalised.
  Never use title case.

Format EXACTLY like this:
COVER: [hook text]
SLIDE 1: [text]
SLIDE 2: [text]
SLIDE 3: [text]
SLIDE 4: [text]
SLIDE 5: [text]
SLIDE 6: [text]
CAPTION:
[full caption text]
HASHTAGS: [5 hashtags]"""


def parse_email(raw: str) -> str:
    """Extract the email hook section."""
    match = re.search(r"=== OUTPUT B: EMAIL HOOK ===(.*?)(?:=== OUTPUT C|$)", raw, re.DOTALL)
    return match.group(1).strip() if match else raw


def parse_carousel(raw: str) -> str:
    """Extract the Instagram carousel section."""
    match = re.search(r"=== OUTPUT C: INSTAGRAM CAROUSEL ===(.*?)$", raw, re.DOTALL)
    return match.group(1).strip() if match else ""


def save_outputs(slug: str, email_hook: str, carousel: str) -> None:
    out = OUTPUT_DIR / slug
    out.mkdir(parents=True, exist_ok=True)

    # email_hook.md
    (out / "email_hook.md").write_text(email_hook, encoding="utf-8")

    # instagram_carousel.md
    (out / "instagram_carousel.md").write_text(carousel, encoding="utf-8")

    print(f"  Saved: {out}/")
    print(f"    email_hook.md")
    print(f"    instagram_carousel.md")


# ── main logic ─────────────────────────────────────────────────────────────────

def repurpose(slug: str) -> bool:
    """Repurpose a single post. Returns True on success."""
    html_path = POSTS_DIR / f"{slug}.html"
    if not html_path.exists():
        print(f"  Post not found: {html_path}")
        return False

    print(f"\n  Post: {slug}")
    post = extract_post_content(html_path)
    brand_voice, product_catalog = read_context()
    post_url = f"{BLOG_BASE_URL}/{slug}"

    prompt = build_prompt(post, slug, brand_voice, product_catalog)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print("  Calling Claude...")
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()

    email_hook = parse_email(raw)
    carousel = parse_carousel(raw)

    save_outputs(slug, email_hook, carousel)
    return True


def get_all_slugs() -> list[str]:
    return sorted(p.stem for p in POSTS_DIR.glob("*.html"))


def main():
    parser = argparse.ArgumentParser(description="Content Repurposer — Switzertemplates")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--post", metavar="SLUG", help="Repurpose a single post by slug")
    group.add_argument("--all", action="store_true", help="Repurpose all posts in posts/")
    args = parser.parse_args()

    print("=" * 50)
    print("  Content Repurposer — Switzertemplates")
    print("=" * 50)

    if args.post:
        success = repurpose(args.post)
        sys.exit(0 if success else 1)

    # --all mode
    slugs = get_all_slugs()
    print(f"\n  Found {len(slugs)} posts to repurpose.")

    done, failed = 0, 0
    for i, slug in enumerate(slugs, 1):
        # Skip if already repurposed (both files exist)
        out = OUTPUT_DIR / slug
        if (out / "email_hook.md").exists() and (out / "instagram_carousel.md").exists():
            print(f"  [{i}/{len(slugs)}] Skipping {slug} (already done)")
            done += 1
            continue

        print(f"\n  [{i}/{len(slugs)}] Processing: {slug}")
        try:
            if repurpose(slug):
                done += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  Error on {slug}: {e}")
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"  Done. {done} repurposed, {failed} failed.")
    print(f"  Output: outputs/repurposed/")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
