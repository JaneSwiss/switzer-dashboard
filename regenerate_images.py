#!/usr/bin/env python3
"""
One-off script to regenerate images for existing posts using the updated prompt system.
Run from project root: python3 regenerate_images.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "agents" / "blog-seo-agent"))

from blog_seo_agent import (
    generate_image_prompts,
    generate_images_from_prompts,
    _assemble_html,
    log_error,
)
from bs4 import BeautifulSoup

POSTS_DIR = Path(__file__).parent / "posts"

SLUGS_TO_REGENERATE = [
    "pinterest-affiliate-marketing",
    "coaching-business",
]


def regenerate(slug: str) -> None:
    html_path = POSTS_DIR / f"{slug}.html"
    if not html_path.exists():
        print(f"  Not found: {html_path}")
        return

    print(f"\n{'='*50}")
    print(f"  Regenerating images for: {slug}")
    print(f"{'='*50}")

    raw = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")

    # Extract title
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else slug.replace("-", " ")

    # Extract existing image prompts block (keep it)
    prompts_div = soup.find("div", class_="image-prompts")
    old_prompts_text = prompts_div.get_text() if prompts_div else ""

    # Extract post body text for new prompt generation
    if prompts_div:
        prompts_div.decompose()
    for p in soup.find_all("p", class_="closing-note"):
        p.decompose()
    if h1:
        h1.decompose()
    # Remove existing images block
    for div in soup.find_all("div", style=lambda s: s and "margin:0 0 2rem" in s):
        div.decompose()

    body_html = str(soup.find("body") or soup)

    keyword = slug.replace("-", " ")

    # Generate fresh image prompts with the updated system
    print("  Generating new image prompts...")
    try:
        image_prompts = generate_image_prompts(keyword, body_html)
    except Exception as e:
        print(f"  Image prompt generation failed: {e}")
        return

    # Generate new images
    print("  Generating new images via Gemini...")
    try:
        image_paths = generate_images_from_prompts(image_prompts, slug)
        print(f"  {len(image_paths)} image(s) generated.")
    except Exception as e:
        print(f"  Image generation failed: {e}")
        log_error("regenerate_images", slug, str(e))
        image_paths = []

    # Reassemble the HTML with new images
    full_html = _assemble_html(title, body_html, image_prompts, image_paths)
    html_path.write_text(full_html, encoding="utf-8")
    print(f"  Saved: {html_path}")


if __name__ == "__main__":
    for slug in SLUGS_TO_REGENERATE:
        regenerate(slug)
    print("\nDone. Push to GitHub to update the live posts.")
