"""
Pinterest Pins — Post Sections

Extracts the real, full structure of an already-written blog post: every real
H3 section heading plus its actual body text. Ground truth for pin copy.

This replaces the old approach (content_repurposer.extract_post_content, capped
at 4000 characters) which was silently truncating posts before their own best
material — confirmed on shopify-vs-wix-for-ecommerce: the 4000-char cut landed
22% through the post, before either of its two comparison sections ("WHERE WIX
WINS" / "WHERE SHOPIFY WINS"). Pin copy was being written blind to most of what
the post actually says. No length cap here — the whole post, real section by
real section.
"""
from __future__ import annotations

from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
POSTS_DIR = ROOT / "posts"


def extract_post_sections(slug: str) -> dict:
    """
    Returns {"title": str, "url": str, "sections": [{"heading": str, "text": str}, ...]}.
    Sections split on real <h3> tags — everything between one heading and the next
    belongs to that section. Content before the first <h3> becomes "INTRODUCTION".
    """
    html_path = POSTS_DIR / f"{slug}.html"
    if not html_path.exists():
        return {"title": "", "url": "", "sections": []}

    raw = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")

    for el in soup.find_all("div", class_="image-prompts"):
        el.decompose()
    for el in soup.find_all("p", class_="closing-note"):
        el.decompose()

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else slug.replace("-", " ")

    post_div = soup.find("div", class_="post") or soup.find("body")
    if not post_div:
        return {"title": title, "url": "", "sections": []}

    sections = []
    current_heading = "INTRODUCTION"
    current_parts: list[str] = []

    for el in post_div.find_all(["h1", "h3", "p", "ul"]):
        if el.name == "h1":
            continue
        if el.name == "h3":
            if current_parts:
                sections.append({"heading": current_heading, "text": "\n".join(current_parts).strip()})
            current_heading = el.get_text(strip=True)
            current_parts = []
        else:
            text = el.get_text(separator=" ", strip=True)
            if text:
                current_parts.append(text)

    if current_parts:
        sections.append({"heading": current_heading, "text": "\n".join(current_parts).strip()})

    return {
        "title": title,
        "url": f"https://www.switzertemplates.com/post/{slug}",
        "sections": [s for s in sections if s["text"]],
    }


def sections_as_text(sections: "list[dict]") -> str:
    """Format real sections for a Claude prompt — real headings, full content, no truncation."""
    return "\n\n".join(f"### {s['heading']}\n{s['text']}" for s in sections)
