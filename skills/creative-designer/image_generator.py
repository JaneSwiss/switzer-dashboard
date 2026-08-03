from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from infographic_pin_prompt import build_infographic_prompt, LAYOUTS

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

    Layout template and badge color offset are chosen here from the variation
    letter (guaranteed rotation), not left for Claude to remember across 5
    variations — same principle as the case-enforcement in copy_writer.py.
    Copy (headline/eyebrow/subtitle) is never invented here — it's already
    been written and approved by copy_writer.py; this only renders it.

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
    offset = max(0, ord(var_letter) - ord("a")) if var_letter.isalpha() else 0
    layout = LAYOUTS[offset % len(LAYOUTS)]

    pin_data = {
        "eyebrow": copy_data.get("eyebrow", ""),
        "headline": copy_data.get("headline", ""),
        "subtitle_bar": copy_data.get("subtitle_bar", ""),
        "items": items,
        "bottom_bar_text": "SWITZERTEMPLATES.COM",
        "color_offset": offset,
        "layout": layout,
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
