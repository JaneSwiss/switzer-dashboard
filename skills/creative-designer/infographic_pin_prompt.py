"""
Reference-driven pin prompt builder — generates the ENTIRE pin (headline, list,
icons, CTA bar, all text) in one OpenAI gpt-image-2 call, instead of the old
photo-background + Pillow-text-overlay approach.

Rewritten August 2026, several times. First rewrite: replaced 3 hard-coded
structural templates with a loose per-pin STYLE REFERENCE pulled from Jane's
real reference pins (context/pin-reference-styles.json) — creative freedom
over layout instead of a mechanical spec. Second rewrite: CONTENT TO INCLUDE
was still too specific — exact quoted eyebrow/headline/subtitle/item strings
for gpt-image-2 to reproduce verbatim, just as constraining as the old rigid
templates, only at the copy level. Fixed by only ever telling OpenAI what the
pin is about and what the real points are — a summary, not a script.

Copy from copy_writer.py (seo_title, cta, seo_description) still drives the
Tailwind pin title/description metadata — unaffected by this. What changed is
only the text baked into the image pixels.

Third rewrite, after Jane ran the same idea through ChatGPT directly and
compared it line-by-line against ours: the STYLE REFERENCE had become a long,
mechanical, element-by-element paragraph (colors, icon style, decoration, all
spelled out) — just as over-specified as the old templates, only in prose
form. Confirmed via her own working prompt that a single terse structural
line ("Infographics or a 3-column by 2-row grid of numbered tips.")
outperforms it. Also, CONTENT TO INCLUDE had drifted into hedging language
("for background... you don't need to use all of them") that gave the model
permission to skip content, with no closing instruction telling it to
actually illustrate the information. Fixed by matching her exact working
structure: a short reference line, plain content with no hedging, and a bare
closing directive ("Create a pin to illustrate this topic/information").

Fourth pass: two more requests once that structure was confirmed working —
(1) the brand color section was one fixed string every single time, so every
pin on the account leaned the same colors. Fixed with _PALETTE_VARIANTS, a
rotating "lead color" direction layered on top of the same base palette, so
consecutive pins actually look different from each other. (2) all pins were
infographics (a numbered list of points) — Jane wanted real type variety too,
specifically some pins built around a real photo with just a short punchy
title, matching her two photo reference pins (pin_type: "photo" in the JSON
cache) rather than a list. image_generator.py now sends 3 of every 5 pins
through the infographic pool and 2 through the photo pool; this module builds
a completely different, shorter CONTENT TO INCLUDE for photo-type pins (no
bullet list — a single hook to design a short title around).

context/pin-reference-styles.json holds a short_description (what's actually
sent to OpenAI), a fuller description (documentation only), and a pin_type
("infographic" or "photo") per reference pin in
agents/general-manager/switzertemplates-pins/ — regenerate/extend via
skills/creative-designer/analyze_pin_references.py.
"""
from __future__ import annotations

import json
from pathlib import Path

MAX_ITEMS = 6
BOTTOM_BAR_TEXT = "SWITZERTEMPLATES.COM - grow your business online"

_REFERENCE_FILE = Path(__file__).resolve().parents[2] / "context" / "pin-reference-styles.json"

# Rotating "lead color" direction on top of the same base palette — without this,
# _BRAND was one fixed string and every pin on the account leaned the same two or
# three colors. Still entirely within the brand's earthy, muted family; only the
# emphasis changes pin to pin.
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


def _load_references() -> list[dict]:
    if not _REFERENCE_FILE.exists():
        return []
    try:
        data = json.loads(_REFERENCE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("references", [])


def pick_reference(offset: int, pin_type: str = "infographic") -> dict | None:
    """Deterministic rotation through the cached reference pool, scoped to one pin_type."""
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
- Render every quoted text string exactly as written below, correctly spelled, in a \
sensible position — no typos, no invented words, no extra text or labels beyond what \
is specified.
- No leaf, floral, botanical, sparkle, or star clip-art filler unless the reference \
style description below explicitly mentions it — don't let generic "elegant" AI \
decoration creep in on its own; if the reference is clean and undecorated, keep it \
clean and undecorated.
- Bottom bar, full-width, the last element in the image: "{BOTTOM_BAR_TEXT}\""""


def _content_block(pin_data: dict) -> str:
    if pin_data.get("pin_type") == "photo":
        return (
            f"This pin is about: {pin_data['topic_summary']}\n"
            f"Design a short, punchy title from this — a few words to one short sentence, "
            f"like a magazine cover line, not a list of points.\n"
            f"Create a pin to illustrate this topic/information"
        )

    lines = [f"This pin is about: {pin_data['topic_summary']}"]
    items = pin_data["items"][:MAX_ITEMS]
    if items:
        lines[0] += ":"
        for item in items:
            lines.append(f'- {item["title"]}: {item["description"]}')
    lines.append("Create a pin to illustrate this topic/information")
    return "\n".join(lines)


def build_infographic_prompt(pin_data: dict) -> str:
    """
    pin_data = {
        "topic_summary": "Learn Pinterest SEO the right way...",  # one-line framing, not quoted verbatim
        "items": [{"title": ..., "description": ..., "icon": ...}, ...],  # 4-6 real points, informational
        "pin_type": "infographic",   # or "photo" — picks the matching reference pool + content shape
        "reference_offset": 0,       # rotates which real reference pin (within pin_type) drives this one
        "palette_offset": 0,         # rotates which lead accent color this pin uses
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

    return (
        f"Design a premium Pinterest marketing graphic — a vertical pin, 1000x1500px, "
        f"2:3 portrait aspect ratio.\n\n"
        f"{_brand_block(pin_data.get('palette_offset', 0))}\n\n"
        f"{reference_block}\n\n"
        f"CONTENT TO INCLUDE:\n{_content_block(pin_data)}\n\n"
        f"{_guardrails()}"
    )
