"""
Full-pin infographic prompt builder — generates the ENTIRE pin (headline, numbered
list, icons, CTA bar, all text) in one OpenAI gpt-image-2 call, instead of the
photo-background + Pillow-text-overlay approach in image_generator.py.

Grounded in Jane's real reference pins (agents/general-manager/switzertemplates-pins/),
which span several genuinely different structures — not one template. Three are
built here; image_generator.py rotates between them per variation so 5 pins in a
topic look structurally different, not just recolored:

  icon_grid      — numbered circle badges + icon + bold title + description,
                   2-column grid. (d4622a7f / 47e8a9b6 reference style)
  outline_list   — single column, thin outline numerals (no color fill), elegant
                   serif titles, sentence case. (c9cbe4df reference style)
  colored_block  — flat colored rounded-rectangle blocks, numbered text only,
                   no icons. (6a3e5ded reference style)

Copy comes first (see copy_writer.py) — this module only ever renders text
that's already been written and approved; it never invents wording.

No hairline dividers/rule lines, no ornamental frames, and no leaf/floral/sparkle
decoration — these are gpt-image-2's default "elegant" fillers and they're exactly
what makes a pin read as AI-generated rather than custom-designed. Structure comes
from spacing and color, not drawn lines or botanical clip-art.

gpt-image-2 renders short-to-medium text blocks reliably but accuracy drops as
text density rises. Capped at 6 list items by design.
"""
from __future__ import annotations

# Rotating badge/accent colors — same warm-neutral palette already used
# elsewhere in the pin system (image_generator.PIN_PALETTE), kept in sync
# manually since this prompt describes colors in words, not swatches.
_BADGE_COLOR_WORDS = [
    "warm terracotta orange-brown",
    "deep chocolate brown",
    "muted sage green",
    "dusty rose pink",
    "warm taupe",
    "deep charcoal navy",
]

MAX_ITEMS = 6
LAYOUTS = ["icon_grid", "outline_list", "colored_block"]

_STYLE_HEADER = """Design a premium Pinterest marketing graphic — a vertical infographic pin, 1000x1500px, 2:3 portrait aspect ratio.

STYLE: Elegant editorial infographic design, quiet luxury aesthetic, generous whitespace, professional design-agency quality. NOT clip-art, NOT a cartoonish template, NOT a generic PowerPoint-style graphic. Think a boutique branding studio's Pinterest content.

BACKGROUND: Solid warm off-white cream (#f8f5f2), clean and uncluttered.

TYPOGRAPHY: Pair an elegant modern high-contrast serif (like Playfair Display) for the headline with a clean geometric sans-serif (like Montserrat) for labels and body text. All text must be spelled exactly as given below — no typos, no invented words, no extra text beyond what is specified.

LAYOUT, TOP TO BOTTOM:
"""

_STYLE_FOOTER = """
COLOR PALETTE: Warm off-white cream background, deep charcoal (#383838) and chocolate brown (#8d6e63) text, numbered badges/accents rotating through warm terracotta, chocolate brown, muted sage green, dusty rose, warm taupe, and muted navy — never just one or two colors repeated across the whole pin. No bright saturated colors, no neon, no pure black or pure white text blocks except inside the bottom bar.

DO NOT INCLUDE, under any circumstances: no leaf, branch, botanical, or floral line-art anywhere in the image. No sparkle or star accent icons. No hairline divider rules or lines anywhere — separate elements with spacing alone, never a drawn line. No ornamental border or frame around the canvas edge. Nothing rendered below the bottom bar — the bottom bar is the last element in the image, full stop.

Render every quoted text string exactly as written, correctly spelled, in the specified position. Do not add any additional text, labels, numbers, or words anywhere in the image beyond what is explicitly specified above."""


def _header_block(pin_data: dict) -> tuple[str, int]:
    """
    Eyebrow (optional) + headline + optional subtitle bar. Eyebrow is skipped
    entirely when empty — real pins mix eyebrow+headline with headline-only,
    forcing an eyebrow onto every pin is part of what made batches feel repetitive.
    Returns (block_text, next_step_number).
    """
    eyebrow = (pin_data.get("eyebrow") or "").strip()
    headline = pin_data["headline"]
    if eyebrow:
        block = (
            f'1. Centered, small, bold, letter-spaced all-caps label in deep charcoal, '
            f'rendered exactly as: "{eyebrow}"\n\n'
            f'2. Below it, a large bold serif headline, centered, in deep charcoal (#383838), '
            f'rendered exactly as: "{headline}"'
        )
        next_num = 3
    else:
        block = (
            f'1. A large bold serif headline, centered, in deep charcoal (#383838), rendered '
            f'exactly as: "{headline}" — this is the dominant visual element at the top of the '
            f'pin, larger than usual since there is no small label above it.'
        )
        next_num = 2

    if pin_data.get("subtitle_bar"):
        block += (
            f'\n\nDirectly below the headline, a full-width horizontal rectangle bar in warm '
            f'terracotta or chocolate brown, containing centered bold white all-caps text rendered '
            f'exactly as: "{pin_data["subtitle_bar"]}".'
        )
    return block, next_num


def _footer_block(pin_data: dict, n: int) -> str:
    return (
        f'{n}. At the very bottom of the canvas, the final element in the image: a full-width '
        f'solid deep charcoal or chocolate-brown horizontal bar containing centered bold '
        f'letter-spaced white all-caps text rendered exactly as: "{pin_data["bottom_bar_text"]}". '
        f'Nothing appears below this bar.'
    )


def _icon_grid_body(items: list, color_offset: int, n: int) -> tuple[str, int]:
    columns = 2 if len(items) > 3 else 1
    lines = []
    for i, item in enumerate(items, start=1):
        color = _BADGE_COLOR_WORDS[(i - 1 + color_offset) % len(_BADGE_COLOR_WORDS)]
        lines.append(
            f'  {i}. Small solid circle badge in {color} containing the white numeral "{i}". '
            f'Next to it, a minimal single-line-weight outline icon (thin stroke, no fill, no '
            f'color other than charcoal or {color}) depicting: {item["icon"]}. Below the icon, '
            f'bold all-caps short title rendered exactly as: "{item["title"]}". Below the title, '
            f'one line of smaller regular-weight muted brown-gray text rendered exactly as: '
            f'"{item["description"]}".'
        )
    block = (
        f'{n}. A numbered list of {len(items)} items, arranged in a clean {columns}-column grid '
        f'with generous spacing between items (no divider lines, no boxes around items — '
        f'whitespace alone separates them), reading order left-to-right then top-to-bottom:\n'
        + "\n".join(lines)
    )
    return block, n + 1


def _outline_list_body(items: list, color_offset: int, n: int) -> tuple[str, int]:
    lines = []
    for i, item in enumerate(items, start=1):
        lines.append(
            f'  {i}. A thin outline circle (no fill, charcoal stroke only, monochrome — no color) '
            f'containing the numeral "{i}" in charcoal. To its right (separated by spacing only, '
            f'no divider line), a small minimal single-line-weight outline icon depicting: '
            f'{item["icon"]}. To the right of the icon, an elegant serif title in normal weight '
            f'(not bold, not all-caps), sentence case, rendered exactly as: "{item["title"]}", '
            f'with a smaller all-caps letter-spaced muted taupe subtext directly below it '
            f'rendered exactly as: "{item["description"]}".'
        )
    block = (
        f'{n}. A single-column numbered list of {len(items)} items stacked vertically, each row '
        f'separated from the next by generous vertical spacing alone — no rule lines, no boxes. '
        f'Monochrome numerals throughout — no colored badges here, elegance comes from typography '
        f'and whitespace, not color or line-work:\n' + "\n".join(lines)
    )
    return block, n + 1


def _colored_block_body(items: list, color_offset: int, n: int) -> tuple[str, int]:
    columns = 3 if len(items) >= 6 else 2
    lines = []
    for i, item in enumerate(items, start=1):
        color = _BADGE_COLOR_WORDS[(i - 1 + color_offset) % len(_BADGE_COLOR_WORDS)]
        lines.append(
            f'  {i}. A solid filled rounded rectangle in {color}, containing left-aligned white '
            f'or cream sans-serif text: the numeral "{i}." followed by the short phrase rendered '
            f'exactly as: "{item["title"]}". Text only in this block — no icon.'
        )
    block = (
        f'{n}. A clean grid of {len(items)} solid colored rounded-rectangle blocks, {columns} per '
        f'row, each block a different color from the rotating palette, containing only numbered '
        f'text (no icons, no separate description line below):\n' + "\n".join(lines)
    )
    return block, n + 1


_BODY_BUILDERS = {
    "icon_grid": _icon_grid_body,
    "outline_list": _outline_list_body,
    "colored_block": _colored_block_body,
}


def build_infographic_prompt(pin_data: dict) -> str:
    """
    pin_data = {
        "eyebrow": "LEARN PINTEREST SEO",     # "" to omit — real pins mix both shapes
        "headline": "The right way",           # sentence case, verbatim
        "subtitle_bar": "So you actually...",  # optional colored bar under headline
        "items": [{"title": ..., "description": ..., "icon": ...}, ...],  # 4-6 items
        "bottom_bar_text": "SWITZERTEMPLATES.COM",
        "color_offset": 0,        # rotates badge color start point
        "layout": "icon_grid",    # one of LAYOUTS — which structural template to use
    }
    """
    items = pin_data["items"][:MAX_ITEMS]
    color_offset = pin_data.get("color_offset", 0)
    layout = pin_data.get("layout", "icon_grid")
    body_builder = _BODY_BUILDERS.get(layout, _icon_grid_body)

    header, next_num = _header_block(pin_data)
    body, next_num = body_builder(items, color_offset, next_num)
    footer = _footer_block(pin_data, next_num)

    return f"{_STYLE_HEADER}\n{header}\n\n{body}\n\n{footer}\n{_STYLE_FOOTER}"
