from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from infographic_pin_prompt import build_infographic_prompt

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from openai_images import generate_image_bytes


PIN_W, PIN_H = 1000, 1500
MAX_ATTEMPTS = 3


def generate_pin_image(copy_data: dict, context: dict, fonts: dict) -> Path:
    """
    Generate a 1000x1500px Pinterest pin as a single whole-image OpenAI call —
    headline, numbered list, icons, CTA bar and all text rendered directly by
    the model in one shot. See infographic_pin_prompt.py for the prompt design
    and MAX_ITEMS cap (reliability drops as text density rises past ~6 items).

    Which real reference pin and lead accent color drive this one are chosen here
    from the variation letter plus a topic-level hash (guaranteed rotation through
    context/pin-reference-styles.json / _PALETTE_VARIANTS), not left for Claude to
    remember across 5 variations — same principle as the case-enforcement in
    copy_writer.py. The topic-level hash matters as much as the per-variation
    offset: without it, every topic's 5 pins would pick the same first 5 references
    in the same order, so different blog posts would still end up looking the same
    as each other even though the 5 pins within one topic varied. OpenAI is given a
    summary of the topic and the real points to cover (from copy_writer.py's
    pin_items, grounded in the real post) and writes its own on-image headline/list
    wording from that — the exact copy fields (seo_title/eyebrow/headline/etc.)
    still drive the Tailwind pin title/description metadata, just not the literal
    pixels of the image anymore.

    3 of every 5 pins in a topic are "infographic" style (a numbered list of
    points); the other 2 are "photo" style (a real photo as the main visual, one
    short punchy title, no list) — matching Jane's two photo reference pins.

    Replaces the old photo-background + Pillow-text-overlay approach entirely —
    `fonts`/`context` are accepted only for call-site signature compatibility
    with the rest of main.py (placeholder fallback still uses fonts).
    """
    items = copy_data.get("pin_items", [])
    if not items:
        raise RuntimeError(
            f"No pin_items for '{copy_data.get('topic', '?')}' — cannot render infographic pin."
        )

    var_letter = (copy_data.get("variation_id") or "a")[-1:].lower()
    var_offset = max(0, ord(var_letter) - ord("a")) if var_letter.isalpha() else 0

    # Deterministic per-topic spread (not Python's hash() — that's randomized per
    # process) so different blog posts don't all draw the same references/colors.
    keyword = copy_data.get("keyword", "")
    topic_base = sum(ord(c) for c in keyword) if keyword else 0
    offset = topic_base + var_offset

    pin_type = "photo" if (var_offset % 5) in (3, 4) else "infographic"

    topic_summary = (
        copy_data.get("seo_title")
        or copy_data.get("headline")
        or copy_data.get("topic", "")
    )
    pin_data = {
        "topic_summary": topic_summary,
        "items": items,
        "pin_type": pin_type,
        "reference_offset": offset,
        "palette_offset": offset,
    }
    prompt = build_infographic_prompt(pin_data)

    last_err: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        if attempt > 0:
            print(f"    Retrying ({attempt + 1}/{MAX_ATTEMPTS})...")
        try:
            image_bytes, cost = generate_image_bytes(prompt, aspect_ratio="9:16", quality="high")
            print(f"    (infographic pin — est. ${cost:.2f})")
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            tmp = Path(tempfile.mktemp(suffix=".png"))
            img.save(tmp, "PNG", optimize=False)
            return tmp
        except Exception as e:
            last_err = e
            print(f"    Attempt {attempt + 1} failed: {e}")

    raise RuntimeError(f"All {MAX_ATTEMPTS} OpenAI infographic pin attempts failed: {last_err}")
