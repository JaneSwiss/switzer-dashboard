"""
Full-pin infographic prompt builder — generates the ENTIRE pin (headline, numbered
list, icons, CTA bar, all text) in one OpenAI gpt-image-2 call, instead of the
photo-background + Pillow-text-overlay approach in image_generator.py.

Modeled directly on Jane's own proven top-performing pins
(agents/content-repurposer/switzertemplates-pins/) — numbered-list infographic
format: eyebrow label -> serif headline -> optional colored subtitle bar ->
numbered icon grid -> solid bottom bar with URL -> italic tagline.

gpt-image-2 renders short-to-medium text blocks reliably but accuracy drops as
text density rises. Capped at 6 list items by design — matches the two
on-brand reference pins (both 6 items) and stays inside gpt-image-2's reliable
range. Don't push this past 6-7 items without testing first.
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


def build_infographic_prompt(pin_data: dict) -> str:
    """
    pin_data = {
        "eyebrow": "HOW TO",                                   # small label above headline
        "headline": "Use Pinterest SEO",                       # main serif headline, verbatim
        "accent_word": "SEO",                                  # optional — one word from headline
                                                                 # rendered in italic/script accent color
        "subtitle_bar": "7 Steps to Get Your Pins Found",       # optional colored bar under headline
        "items": [
            {"title": "THINK SEARCH, NOT SOCIAL",
             "description": "Pinterest works like a search engine, not a feed.",
             "icon": "a magnifying glass over a search bar"},
            ...  # 4-6 items, each with a short title, one-line description, and a
                 # simple concept for the line-art icon next to it
        ],
        "bottom_bar_text": "SWITZERTEMPLATES.COM/BLOG",
        "tagline": "More Pinterest tips for small business owners",
        "color_offset": 0,   # optional — rotates the badge color start point so different
                              # variations of the same topic don't render identical colors
                              # even when they happen to share items
    }
    """
    items = pin_data["items"][:MAX_ITEMS]
    n = len(items)
    columns = 2 if n > 3 else 1
    color_offset = pin_data.get("color_offset", 0)

    items_block_lines = []
    for i, item in enumerate(items, start=1):
        color = _BADGE_COLOR_WORDS[(i - 1 + color_offset) % len(_BADGE_COLOR_WORDS)]
        items_block_lines.append(
            f'  {i}. Small solid circle badge in {color} containing the white numeral "{i}". '
            f'Next to it, a minimal single-line-weight outline icon (thin stroke, no fill, no color '
            f'other than charcoal or {color}) depicting: {item["icon"]}. Below the icon, bold '
            f'all-caps short title rendered exactly as: "{item["title"]}". Below the title, one line '
            f'of smaller regular-weight muted brown-gray text rendered exactly as: '
            f'"{item["description"]}".'
        )
    items_block = "\n".join(items_block_lines)

    accent_line = ""
    if pin_data.get("accent_word"):
        accent_line = (
            f' The word "{pin_data["accent_word"]}" within the headline is rendered in an elegant '
            f'italic serif or script style, in warm chocolate brown, distinct from the rest of the '
            f'headline which is upright bold serif in deep charcoal.'
        )

    subtitle_block = ""
    if pin_data.get("subtitle_bar"):
        subtitle_block = (
            f'\n\nDirectly below the headline, a full-width horizontal rectangle bar in warm '
            f'terracotta or chocolate brown, containing centered bold white all-caps text rendered '
            f'exactly as: "{pin_data["subtitle_bar"]}".'
        )

    prompt = f"""Design a premium Pinterest marketing graphic — a vertical infographic pin, 1000x1500px, 2:3 portrait aspect ratio.

STYLE: Elegant editorial infographic design, quiet luxury aesthetic, generous whitespace, professional design-agency quality. NOT clip-art, NOT a cartoonish template, NOT a generic PowerPoint-style graphic. Think a boutique branding studio's Pinterest content.

BACKGROUND: Solid warm off-white cream (#f8f5f2), clean and uncluttered.

TYPOGRAPHY: Pair an elegant modern high-contrast serif (like Playfair Display) for the headline with a clean geometric sans-serif (like Montserrat) for labels and body text. All text must be spelled exactly as given below — no typos, no invented words, no extra text beyond what is specified.

LAYOUT, TOP TO BOTTOM:

1. Centered, small, bold, letter-spaced all-caps label in deep charcoal, rendered exactly as: "{pin_data['eyebrow']}"

2. Below it, a large bold serif headline, centered, in deep charcoal (#383838), rendered exactly as: "{pin_data['headline']}"{accent_line}{subtitle_block}

3. A thin horizontal hairline rule or generous vertical whitespace separates the headline area from the list below.

4. A numbered list of {n} items, arranged in a clean {columns}-column grid with thin hairline divider lines between items, reading order left-to-right then top-to-bottom:
{items_block}

5. At the very bottom of the canvas, a full-width solid deep charcoal or chocolate-brown horizontal bar containing centered bold letter-spaced white all-caps text rendered exactly as: "{pin_data['bottom_bar_text']}"

6. Directly below that bar (still within the canvas), small centered italic muted brown-gray text rendered exactly as: "{pin_data['tagline']}"

DECORATIVE DETAIL: A few small, subtle sparkle or thin line-art leaf/branch accents near the headline — minimal, not distracting.

COLOR PALETTE: Warm off-white cream background, deep charcoal (#383838) and chocolate brown (#8d6e63) text, numbered badges rotating through warm terracotta, chocolate brown, muted sage green, dusty rose, and warm taupe. No bright saturated colors, no neon, no pure black or pure white text blocks except inside the bottom bar.

Render every quoted text string exactly as written, correctly spelled, in the specified position. Do not add any additional text, labels, numbers, or words anywhere in the image beyond what is explicitly specified above."""

    return prompt
