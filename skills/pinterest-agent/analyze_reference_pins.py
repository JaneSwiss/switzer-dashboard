#!/usr/bin/env python3
"""
Analyze Reference Pins — Switzertemplates

Reads every image in context/top-performing-pins/ (Jane's own proven-performing pins,
hers to curate), asks Claude to analyze each one's composition/color/typography/what
makes it effective, and synthesizes across all of them into one written style brief
saved to context/pin-visual-style.md.

copy_writer.py's design_brief prompt loads that file and writes every future pin brief
to match it — a described style, the same mechanism blog_seo_agent.py's IMAGE_PROMPT_SYSTEM
already uses, so it doesn't depend on whether the image-generation API itself supports
passing a reference image directly.

Standalone and occasional, NOT part of the weekly automated loop — Jane's top performers
don't change week to week. Run once after adding reference pins, and again whenever she
adds more.

Run:
    python3 skills/pinterest-agent/analyze_reference_pins.py
"""

import base64
import mimetypes
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = ROOT / "context" / "top-performing-pins"
OUTPUT_FILE = ROOT / "context" / "pin-visual-style.md"

load_dotenv(ROOT / ".env")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

PER_IMAGE_PROMPT = """This is one of Jane's own Pinterest pins for Switzertemplates that has
genuinely performed well (saves/clicks) on her account. Analyze it as a design reference —
not what it says, but what makes it work visually:

1. Composition — layout, where the eye goes first, how text and imagery are balanced
2. Color palette — the actual colors used and how they work together
3. Typography — how headline text is placed, sized, and styled against the image
4. Subject matter / scene type — what's actually depicted (person, flat lay, product, etc.)
5. Mood — the specific feeling it creates

Be specific and concrete — this analysis will directly inform prompts for generating new
pin images, so vague description like "clean and modern" is not useful. Name actual colors,
actual composition choices, actual techniques. 150-250 words."""

SYNTHESIS_PROMPT = """Below are individual analyses of {count} of Jane's own
proven-performing Pinterest pins for Switzertemplates. Synthesize these into ONE
concise, actionable style brief that a future image-generation prompt can follow directly.

Do not just summarize each one separately — find what's actually consistent across them
(if anything), and be honest about real variety if the examples differ. The goal is a
brief specific enough that someone generating a brand-new pin image could match this style
convincingly, not generic "clean and professional" language.

Structure the output as:
## Proven Pinterest Visual Style — Switzertemplates
(2-3 sentences: the throughline across these examples)

### Composition
### Color
### Typography & text placement
### Subject matter
### Mood

Individual analyses:
{analyses}"""


def _encode_image(path: Path) -> dict:
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "image/jpeg"
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": mime_type, "data": data},
    }


def _analyze_one(client: anthropic.Anthropic, path: Path) -> str:
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": [
                _encode_image(path),
                {"type": "text", "text": PER_IMAGE_PROMPT},
            ],
        }],
    )
    return response.content[0].text.strip()


def main():
    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY not set in .env")
        return

    if not REFERENCE_DIR.exists():
        print(f"  {REFERENCE_DIR} doesn't exist yet — nothing to analyze.")
        return

    images = sorted(
        p for p in REFERENCE_DIR.iterdir()
        if p.suffix.lower() in VALID_EXTENSIONS
    )
    if not images:
        print(f"  No reference images found in {REFERENCE_DIR}.")
        print(f"  Drop screenshots/exports of your proven-performing pins there, then re-run this.")
        return

    print(f"  Found {len(images)} reference pin(s). Analyzing...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    analyses = []
    for i, path in enumerate(images, 1):
        print(f"  [{i}/{len(images)}] {path.name}...")
        try:
            analysis = _analyze_one(client, path)
            analyses.append(f"### Reference: {path.name}\n{analysis}")
        except Exception as e:
            print(f"    Failed: {e} — skipping")

    if not analyses:
        print("  No images could be analyzed. Nothing written.")
        return

    print("  Synthesizing into one style brief...")
    synthesis_prompt = SYNTHESIS_PROMPT.format(
        count=len(analyses),
        analyses="\n\n".join(analyses),
    )
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1200,
        messages=[{"role": "user", "content": synthesis_prompt}],
    )
    style_brief = response.content[0].text.strip()

    OUTPUT_FILE.write_text(style_brief, encoding="utf-8")
    print(f"\n  Saved: {OUTPUT_FILE}")
    print(f"  copy_writer.py will pick this up automatically on its next run.")


if __name__ == "__main__":
    main()
