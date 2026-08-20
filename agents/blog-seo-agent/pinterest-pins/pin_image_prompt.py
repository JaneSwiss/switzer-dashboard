"""
Pinterest Pins — Image Prompt

Mirrors blog_seo_agent.generate_image_prompts()'s role: a second step that only
runs after copy is written and validated, turning that finished copy into an
OpenAI image prompt. Never invents wording — pin_writer.py already decided
what the pin says; this only decides how it looks.

Reuses context/pin-reference-styles.json (Jane's real reference pins, unrelated
to the old skills/pinterest-agent system — this file lives in context/ as
shared, neutral ground truth, not part of what got scrapped).

Content dictation removed by Jane's explicit direction: earlier versions fed OpenAI an
exact eyebrow + a list of points to render, one per line. Jane's call — stop telling OpenAI
what the eyebrow/points should be; give it the (now short, corrected) pin title and brand/
style/guardrail context, and let it design the actual pin content itself. Only the headline
and the bottom bar are still quoted exactly; everything else about what appears on the pin
is OpenAI's own creative decision.
"""
from __future__ import annotations

import json
from pathlib import Path

BOTTOM_BAR_TEXT = "SWITZERTEMPLATES.COM - grow your business online"

_REFERENCE_FILE = Path(__file__).resolve().parents[3] / "context" / "pin-reference-styles.json"

_PALETTE_VARIANTS = [
    "For this pin specifically, lead with warm chocolate brown as the dominant accent color.",
    "For this pin specifically, lead with deep charcoal as the dominant accent color.",
    "For this pin specifically, lead with muted sage green as the dominant accent color.",
    "For this pin specifically, lead with dusty rose as the dominant accent color.",
    "For this pin specifically, lead with deep navy as the dominant accent color.",
    "For this pin specifically, lead with warm terracotta as the dominant accent color.",
    "For this pin specifically, lead with olive green as the dominant accent color.",
    "For this pin specifically, lead with muted maroon as the dominant accent color.",
]


def _load_references() -> list:
    if not _REFERENCE_FILE.exists():
        return []
    try:
        data = json.loads(_REFERENCE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("references", [])


def pick_reference(offset: int, pin_type: str = "infographic"):
    refs = [r for r in _load_references() if r.get("pin_type", "infographic") == pin_type]
    if not refs:
        return None
    return refs[offset % len(refs)]


def _brand_block(palette_offset: int) -> str:
    variant = _PALETTE_VARIANTS[palette_offset % len(_PALETTE_VARIANTS)]
    return (
        f"BRAND: Switzertemplates — a premium, editorial, quiet-luxury small business "
        f"brand. Warm neutral base: off-white cream (#f8f5f2), chocolate brown (#8d6e63), "
        f"warm taupe (#bbb0aa), muted sand (#a5988e), charcoal (#383838), plus room for "
        f"muted earthy accents (sage green, dusty rose, terracotta, deep navy, olive, "
        f"muted maroon) — never bright, neon, or primary-colored. {variant}"
    )


def _guardrails() -> str:
    return f"""GUARDRAILS:
- Render the quoted headline and bottom bar text exactly as written, correctly spelled — \
no typos, no invented words.
- Only use icons if the reference style below actually uses them — otherwise keep it \
text-only, don't force icons in where they don't belong.
- No leaf, floral, botanical, sparkle, or star clip-art filler unless the reference style \
description explicitly mentions it.
- Bottom bar, full-width, the last element in the image: "{BOTTOM_BAR_TEXT}\""""


def build_pin_prompt(pin_data: dict) -> str:
    """
    pin_data = {
        "image_headline": "...",       # short, quoted exactly
        "image_eyebrow": "...",        # optional, quoted exactly
        "pin_items": [...],            # informational, paraphrasable
        "pin_type": "infographic"/"photo",
        "reference_offset": 0,
        "palette_offset": 0,
    }
    """
    pin_type = pin_data.get("pin_type", "infographic")
    reference = pick_reference(pin_data.get("reference_offset", 0), pin_type)
    if reference:
        reference_block = (
            f'STYLE REFERENCE (for creative direction — adapt naturally, do not copy '
            f'mechanically or reproduce it literally):\n'
            f'{reference["short_description"]}\n'
            f'Exact layout details, icon choices, precise colors, and spacing are yours '
            f'to design well — as long as the result feels like it belongs in the same '
            f'premium, editorial family as this reference and stays within the brand '
            f'palette below.'
        )
    else:
        reference_block = (
            "STYLE REFERENCE: none available — design a premium editorial pin in the "
            "brand's quiet-luxury aesthetic, your own creative choice of layout."
        )

    title = pin_data["image_headline"]

    if pin_type == "photo":
        content = (
            f'Headline — render exactly: "{title}"\n'
            f'Design a photo-driven pin: a real photo as the main visual, with this short '
            f'headline as the dominant text — not a list, not an infographic.'
        )
    else:
        content = (
            f'Headline — render exactly: "{title}"\n'
            f'This pin is for a blog post about that exact topic. Decide the rest of the '
            f'content yourself — what points, layout, and supporting text best sell this '
            f'specific topic. Be genuinely specific to it, not generic filler.'
        )

    return (
        f"Design a premium Pinterest marketing graphic — a vertical pin, 1000x1500px, "
        f"2:3 portrait aspect ratio.\n\n"
        f"{_brand_block(pin_data.get('palette_offset', 0))}\n\n"
        f"{reference_block}\n\n"
        f"CONTENT TO INCLUDE:\n{content}\n\n"
        f"{_guardrails()}"
    )
