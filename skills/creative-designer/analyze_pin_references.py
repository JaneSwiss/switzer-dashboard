#!/usr/bin/env python3
"""
Analyze Pin References — Switzertemplates

Reads every image in agents/general-manager/switzertemplates-pins/ (Jane's own
proven-performing pins — hers to curate, add to any time) and asks Claude to
describe each one individually as a loose creative-direction brief: composition,
typography, color, icon/illustration style, what makes it feel premium. Writes
one entry per image to context/pin-reference-styles.json.

Deliberately per-image, NOT synthesized into one combined style — a merged
brief averages away the real variety between Jane's pins (grid vs. list vs.
photo-overlay, icon vs. no icon, dividers vs. none) into one generic template,
which is exactly what made pin output feel same-y and over-constrained before.
infographic_pin_prompt.py picks ONE reference per pin generation and gives
OpenAI creative freedom to interpret it, rather than a mechanical spec built
from an averaged-out description.

Idempotent: skips images already in the cache unless --force is passed, so
running this after Jane drops in one new pin only costs one API call.

Standalone and occasional, NOT part of the weekly automated loop — run once
after adding reference pins, and again whenever she adds more.

Run:
    python3 skills/creative-designer/analyze_pin_references.py
    python3 skills/creative-designer/analyze_pin_references.py --force
"""

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = ROOT / "agents" / "general-manager" / "switzertemplates-pins"
OUTPUT_FILE = ROOT / "context" / "pin-reference-styles.json"

load_dotenv(ROOT / ".env")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

PER_IMAGE_PROMPT = """This is one of Jane's own Pinterest pins for Switzertemplates that
has genuinely performed well on her account. Describe it as a loose creative-direction
brief for a designer to riff on — not a mechanical spec to fill in, and not what the text
says, just the visual design: overall layout structure, how the headline is typeset,
whether there's a numbered list/grid and how it's arranged, icon or illustration style
(hand-drawn line art, full-color flat illustration, none), color usage, any dividers or
decorative touches actually present, and the bottom bar/watermark treatment.

Be specific and concrete (name actual colors, actual layout choices) but write it as
flowing creative-direction prose, 3-5 sentences, the way you'd brief a designer — not a
numbered checklist. If the image uses bright/saturated colors that don't match a warm,
muted, earthy premium palette, say so explicitly and note it should be recolored if used
as a reference, rather than pretending the colors are on-brand.

This longer analysis is kept for documentation only — it is NOT what gets sent to
OpenAI (a confirmed real test showed a long, element-by-element description performs
worse than a short structural cue with real creative freedom left in). So also give:
1. A short one-line structural cue, the kind you'd say out loud in one breath — e.g.
   "Infographics or a 3-column by 2-row grid of numbered tips." or "A single-column
   numbered list with a small icon beside each item." Name the structure only — no
   colors, no icon style, no decoration, no typography detail. On its own line at the
   end, prefixed with "SHORT: ".
2. A short 2-4 word family label (e.g. "icon grid", "single column outline list",
   "photo lightbox overlay", "colored block grid") on its own line after that,
   prefixed with "LAYOUT: "."""


def _encode_image(path: Path) -> dict:
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "image/jpeg"
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": mime_type, "data": data},
    }


def _analyze_one(client: anthropic.Anthropic, path: Path) -> dict:
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                _encode_image(path),
                {"type": "text", "text": PER_IMAGE_PROMPT},
            ],
        }],
    )
    text = response.content[0].text.strip()

    layout_family = "unspecified"
    if "\nLAYOUT:" in text:
        text, layout_line = text.rsplit("\nLAYOUT:", 1)
        text = text.strip()
        layout_family = layout_line.strip().lower().replace(" ", "_").strip(".")

    short_description = ""
    description = text
    if "\nSHORT:" in text:
        description, short_line = text.rsplit("\nSHORT:", 1)
        description = description.strip()
        short_description = short_line.strip()

    entry = {
        "file": path.name,
        "layout_family": layout_family,
        "short_description": short_description or description,
        "description": description,
    }
    if "bright" in description.lower() and "recolor" in description.lower():
        entry["off_brand_colors"] = True
    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-analyze every image, not just new ones.")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY not set in .env")
        return

    if not REFERENCE_DIR.exists():
        print(f"  {REFERENCE_DIR} doesn't exist yet — nothing to analyze.")
        return

    images = sorted(
        p for p in REFERENCE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS
    )
    if not images:
        print(f"  No reference images found in {REFERENCE_DIR}.")
        return

    cache = {"_readme": (
        "Per-image style descriptions of Jane's real proven-performing pins in "
        "agents/general-manager/switzertemplates-pins/. 'short_description' is what "
        "actually goes in the OpenAI prompt (see infographic_pin_prompt.py) — kept to "
        "one terse line. 'description' is the fuller analysis, documentation only, not "
        "sent to OpenAI. Regenerate/extend via "
        "skills/creative-designer/analyze_pin_references.py whenever Jane adds new pins."
    ), "references": []}
    existing_by_file = {}
    if OUTPUT_FILE.exists() and not args.force:
        cache = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        existing_by_file = {r["file"]: r for r in cache.get("references", [])}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    to_analyze = [p for p in images if args.force or p.name not in existing_by_file]

    if not to_analyze:
        print(f"  All {len(images)} reference pin(s) already analyzed. Use --force to redo.")
        return

    print(f"  Analyzing {len(to_analyze)} pin(s)...")
    for i, path in enumerate(to_analyze, 1):
        print(f"  [{i}/{len(to_analyze)}] {path.name}...")
        try:
            existing_by_file[path.name] = _analyze_one(client, path)
        except Exception as e:
            print(f"    Failed: {e} — skipping")

    cache["references"] = [existing_by_file[p.name] for p in images if p.name in existing_by_file]
    OUTPUT_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n  Saved {len(cache['references'])} reference(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
