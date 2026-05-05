from __future__ import annotations

import os
import io
import re
import math
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

from font_manager import setup_fonts, load_font


# ── Constants ─────────────────────────────────────────────────────────────────

TEXT_WHITE  = (255, 255, 255)
TEXT_DARK   = (56, 56, 56)       # #383838 charcoal — headline on white box
LABEL_COLOR = (187, 176, 170)    # warm taupe — watermark
BOX_WHITE   = (255, 255, 255)    # white headline box

# CTA bar colors — cycle by topic_id for variety across the batch
CTA_BAR_CYCLE = [
    (0,   0,   0),    # black
    (107, 63,  42),   # chocolate brown  #6B3F2A
    (196, 113, 79),   # warm terracotta  #C4714F
    (122, 140, 110),  # dusty sage       #7A8C6E
    (44,  62,  80),   # muted navy       #2C3E50
]

PIN_W, PIN_H  = 1000, 1500
MAX_ATTEMPTS  = 3

# Base reference photo aesthetic — applies to every pin.
# Derived from context/pin-photos/: muted warm palette, soft natural light,
# editorial quality, generous negative space, quiet luxury.
_PHOTO_BASE = (
    "Editorial lifestyle photograph. "
    "Color palette: warm neutrals — cream, ivory, warm white, soft beige, mocha, or "
    "chocolate brown. Lighting: soft, natural, gently diffused, non-directional, "
    "warm undertones. Composition: generous negative space in the lower portion of the frame. "
    "Aesthetic: quiet luxury, editorial magazine quality, clean, polished, feminine. "
    "Saturation: muted, not vivid. Real and natural, not staged or overly produced. "
    "Leave generous empty space above the subject's head — never crop or frame tightly "
    "against the top edge of the image."
)

# Scene type hints per variation letter — ensures each of the 5 pins in a topic
# has a genuinely different composition, subject and colour temperature.
# Based directly on the variety seen in context/pin-photos/.
_SCENE_HINTS: dict[str, str] = {
    "a": (
        "Scene: tight close-up of a stylish woman's hands holding a coffee cup or iced "
        "drink, white or cream sleeve visible, gold ring or bracelet, warm blurred background. "
        "No face. Intimate, close crop."
    ),
    "b": (
        "Scene: a woman's full or three-quarter figure — face visible — standing or seated, "
        "holding a closed laptop or documents, bright clean neutral background. "
        "Portrait composition, subject fills the upper two-thirds of the frame."
    ),
    "c": (
        "Scene: a woman in rich dark clothing — chocolate brown, deep burgundy, or dark navy "
        "blazer — standing in a minimal interior or urban architectural setting. "
        "Moody, editorial, sophisticated."
    ),
    "d": (
        "Scene: styled desk flat lay — no person — closed laptop, ceramic mug, open notebook, "
        "small plant or flowers, warm accessories. Warm marble, linen, or oak wood surface. "
        "Shot from slightly above or at a gentle angle."
    ),
    "e": (
        "Scene: bright minimal workspace side-angle — clean white or cream desk, minimal objects "
        "(ceramic mug, dried flowers, a notebook), soft natural window light from the side. "
        "Airy, uncluttered, Scandinavian editorial feel."
    ),
}

_RETRY_PREFIX = (
    "CRITICAL: zero text, zero letters, zero numbers, zero words, zero typography "
    "anywhere in the image. Reject and regenerate if any text appears. "
)

_STOP = {
    "a","an","the","is","are","was","were","to","of","in","on","at","by","for",
    "with","from","your","our","its","this","that","and","or","but","not","you",
    "it","we","they","i","my","me","so","as","be","do","get","have","had","has",
    "will","would","could","should","can","if","how","what","when","where","why",
    "who","which","than","then","been","more","no","up","out","without","never",
    "always","just","even","still","only","make","makes","made","use","using",
    "need","look","looks","feel","feels","take","takes","start","starts","run",
}


# ── Gemini image generation ────────────────────────────────────────────────────

def _build_gemini_prompt(variation_letter: str = "a",
                          retry_prefix: str = "") -> str:
    """
    Build the Gemini prompt: no-text instruction + scene hint + base aesthetic.
    variation_letter determines which of 5 scene types is used.
    retry_prefix is prepended on retries only.
    """
    hint = _SCENE_HINTS.get(variation_letter.lower(), _SCENE_HINTS["a"])
    prompt = (
        "No text, no words, no letters, no numbers, no typography, "
        "no placeholder text, no lorem ipsum, no labels anywhere in the image. "
        "Fill the entire frame with the scene - no empty areas, no blank space, "
        "no negative space at the bottom. The subject and scene elements must "
        "occupy the full frame from top to bottom. "
        f"{hint} "
        f"{_PHOTO_BASE} "
        "No text, no logos, no overlays in the image. "
        "IMPORTANT: Generate in strict portrait orientation, taller than wide, "
        "minimum 2:3 aspect ratio (height at least 1.5x the width). "
        "Do not generate square or landscape images. "
        "Portrait orientation (2:3 ratio)."
    )
    return (retry_prefix + prompt) if retry_prefix else prompt


def _generate_background_gemini(variation_letter: str = "a",
                                  retry_prefix: str = "") -> Image.Image:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set in environment.")

    from google import genai
    from google.genai import types
    import base64

    client   = genai.Client(api_key=api_key)
    prompt   = _build_gemini_prompt(variation_letter, retry_prefix)
    last_err = None

    for model in ("imagen-4.0-generate-001", "imagen-4.0-fast-generate-001"):
        try:
            response = client.models.generate_images(
                model=model,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="9:16",
                    output_mime_type="image/jpeg",
                ),
            )
            if response.generated_images:
                img_bytes = response.generated_images[0].image.image_bytes
                return Image.open(io.BytesIO(img_bytes)).convert("RGB")
        except Exception as e:
            last_err = e

    for model in ("gemini-2.5-flash-image", "gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    raw = part.inline_data.data
                    if isinstance(raw, str):
                        raw = base64.b64decode(raw)
                    return Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as e:
            last_err = e

    raise RuntimeError(f"Gemini image generation failed: {last_err}")


def _generate_background_with_retry(variation_letter: str = "a") -> Image.Image:
    """Retry up to MAX_ATTEMPTS. On retries, prepend stronger no-text instruction."""
    last_err: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        prefix = _RETRY_PREFIX if attempt > 0 else ""
        if attempt > 0:
            print(f"    Retrying ({attempt + 1}/{MAX_ATTEMPTS})...")
        try:
            return _generate_background_gemini(variation_letter, prefix)
        except Exception as e:
            last_err = e
            print(f"    Attempt {attempt + 1} failed: {e}")
    raise RuntimeError(f"All {MAX_ATTEMPTS} Gemini attempts failed: {last_err}")






def _placeholder_background(topic: str) -> Image.Image:
    img  = Image.new("RGB", (PIN_W, PIN_H))
    draw = ImageDraw.Draw(img)
    for y in range(PIN_H):
        t = y / PIN_H
        draw.line([(0, y), (PIN_W, y)],
                  fill=(int(80 + 40 * t), int(60 + 30 * t), int(50 + 25 * t)))
    return img


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _format_headline(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


def _wrap_to_word_lines(text: str, font, max_width: int) -> list[list[str]]:
    words, lines, cur_words, cur_text = text.split(), [], [], ""
    for word in words:
        test = (cur_text + " " + word).strip()
        if font.getbbox(test)[2] - font.getbbox(test)[0] <= max_width:
            cur_text = test
            cur_words.append(word)
        else:
            if cur_words:
                lines.append(cur_words[:])
            cur_words, cur_text = [word], word
    if cur_words:
        lines.append(cur_words)
    return lines


def _draw_word_line(draw, word_specs: list[tuple], y: int) -> None:
    if not word_specs:
        return
    space_w = word_specs[0][1].getbbox(" ")[2] - word_specs[0][1].getbbox(" ")[0]
    total_w = sum(f.getbbox(w)[2] - f.getbbox(w)[0] for w, f, _ in word_specs)
    total_w += space_w * (len(word_specs) - 1)
    x = (PIN_W - total_w) // 2
    for i, (word, font, color) in enumerate(word_specs):
        draw.text((x, y), word, font=font, fill=color)
        x += font.getbbox(word)[2] - font.getbbox(word)[0]
        if i < len(word_specs) - 1:
            x += space_w


def _accent_word_indices(words: list[str], count: int = 2) -> set[int]:
    content = [(i, w) for i, w in enumerate(words)
               if w.lower().strip(".,!?-—'\"") not in _STOP]
    n = min(count, max(1, len(content) // 3))
    return {i for i, _ in content[-n:]}


def _highlight_set(copy_data: dict) -> set[str]:
    hw = copy_data.get("highlight_words", [])
    return {w.lower().strip(".,!?-—'\"") for w in hw if w}


def _is_accent(word: str, highlight: set[str], fallback_idx: int,
               fallback_set: set[int]) -> bool:
    if highlight:
        return word.lower().strip(".,!?-—'\"") in highlight
    return fallback_idx in fallback_set


def _extract_cta(seo_description: str) -> str:
    text      = re.sub(r'\s+#\S+', '', seo_description).strip()
    last_dot  = text.rfind('. ')
    return text[last_dot + 2:].strip() if last_dot != -1 else text


def _best_subtitle_size(text: str, font_path: str | None, max_width: int,
                         min_size: int = 22, max_size: int = 44) -> int:
    best = min_size
    for size in range(min_size, max_size + 1):
        font  = load_font(font_path, size)
        lines = _wrap_to_word_lines(text, font, max_width)
        if len(lines) <= 2:
            best = size
        else:
            break
    return best


def _topic_number(copy_data: dict) -> int:
    explicit = copy_data.get("topic_id")
    if explicit is not None:
        return int(explicit)
    vid     = copy_data.get("variation_id", "") or copy_data.get("id", "")
    num_str = "".join(c for c in vid if c.isdigit())
    return int(num_str) if num_str else 1


def _cta_bar_color(copy_data: dict) -> tuple:
    return CTA_BAR_CYCLE[(_topic_number(copy_data) - 1) % len(CTA_BAR_CYCLE)]


HEADLINE_ACCENT_CYCLE = [
    (242, 201, 76),   # yellow      #F2C94C
    (233, 30,  140),  # pink        #E91E8C
    (79,  195, 247),  # blue        #4FC3F7
    (196, 113, 79),   # terracotta  #C4714F
]

def _headline_accent_color(copy_data: dict) -> tuple:
    """Accent colour for highlighted words in pins a and d — cycles by topic."""
    return HEADLINE_ACCENT_CYCLE[(_topic_number(copy_data) - 1) % len(HEADLINE_ACCENT_CYCLE)]

def _uses_headline_accent(copy_data: dict) -> bool:
    """Only pins a and d get coloured highlighted words."""
    vid  = copy_data.get("variation_id", "") or copy_data.get("id", "")
    last = vid[-1].lower() if vid else "a"
    return last in ("a", "d")

def _has_cta_bar(copy_data: dict) -> bool:
    """Pins b and e get a CTA bar below the white box; a, c, d do not."""
    vid  = copy_data.get("variation_id", "") or copy_data.get("id", "")
    last = vid[-1].lower() if vid else "a"
    return last in ("b", "e")


def _box_top_y(copy_data: dict, box_h: int) -> int:
    """
    Place the white box where the photo has the most empty space.
    Per composition instructions, subject is upper/right so lower area is clear.
    Variation c (overhead flat lay) centres the box; all others use lower portion.
    """
    vid  = copy_data.get("variation_id", "") or copy_data.get("id", "")
    last = vid[-1].lower() if vid else "a"
    if last == "c":
        y = int(PIN_H * 0.42) - box_h // 2   # center for overhead
    else:
        y = int(PIN_H * 0.60) - box_h // 2   # lower portion for all others
    return max(80, min(y, PIN_H - box_h - 80))


def _draw_watermark(draw, font) -> None:
    watermark = "switzertemplates.com"
    wm_bbox   = font.getbbox(watermark)
    wm_x      = (PIN_W - (wm_bbox[2] - wm_bbox[0])) // 2
    draw.text((wm_x, PIN_H - 42), watermark, font=font, fill=LABEL_COLOR)


# ── White box compositor ───────────────────────────────────────────────────────

def _composite_white_box(img: Image.Image, copy_data: dict, fonts: dict,
                          include_cta_bar: bool) -> Image.Image:
    """
    All pins use a white rectangle behind the headline — no dark overlay.
    The white box provides contrast. Highlight words rendered in italic.
    Pins b and e also get a coloured CTA bar below the box.
    """
    draw           = ImageDraw.Draw(img)
    headline_size  = 64
    watermark_size = 18

    regular_font   = load_font(fonts.get("serif"),        headline_size)
    italic_font    = load_font(fonts.get("serif_italic"),  headline_size)
    watermark_font = load_font(fonts.get("sans"),          watermark_size)

    box_w    = int(PIN_W * 0.86)
    box_x    = (PIN_W - box_w) // 2
    pad_x    = 48
    pad_y    = 40
    text_max = box_w - pad_x * 2

    headline  = _format_headline(copy_data.get("pin_headline", ""))
    all_words = headline.split()
    highlight = _highlight_set(copy_data)
    fallback  = _accent_word_indices(all_words, count=2)

    word_lines  = _wrap_to_word_lines(headline, regular_font, text_max)
    line_height = headline_size + 18
    block_h     = len(word_lines) * line_height
    box_h       = block_h + pad_y * 2
    box_y       = _box_top_y(copy_data, box_h)

    # White headline box
    draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h], fill=BOX_WHITE)

    # Headline in dark charcoal; pins a and d get coloured + italic highlights
    uses_accent  = _uses_headline_accent(copy_data)
    accent_color = _headline_accent_color(copy_data) if uses_accent else None
    y   = box_y + pad_y
    idx = 0
    for line_words in word_lines:
        specs = []
        for word in line_words:
            accented = _is_accent(word, highlight, idx, fallback)
            font     = italic_font if accented else regular_font
            color    = accent_color if (uses_accent and accented) else TEXT_DARK
            specs.append((word, font, color))
            idx += 1
        _draw_word_line(draw, specs, y)
        y += line_height

    # CTA bar (b and e only)
    if include_cta_bar:
        subtitle  = _extract_cta(copy_data.get("seo_description", ""))
        sub_size  = _best_subtitle_size(subtitle, fonts.get("sans"), text_max)
        sub_font  = load_font(fonts.get("sans"), sub_size)
        sub_lines = _wrap_to_word_lines(subtitle, sub_font, text_max)
        sub_lh    = sub_size + 10
        bar_pad   = 18
        bar_h     = len(sub_lines) * sub_lh + bar_pad * 2
        bar_y     = box_y + box_h + 6
        draw.rectangle([box_x, bar_y, box_x + box_w, bar_y + bar_h],
                       fill=_cta_bar_color(copy_data))
        sub_y = bar_y + bar_pad
        for sl in sub_lines:
            _draw_word_line(draw, [(w, sub_font, TEXT_WHITE) for w in sl], sub_y)
            sub_y += sub_lh

    _draw_watermark(draw, watermark_font)
    return img


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_pin_image(copy_data: dict, context: dict, fonts: dict) -> Path:
    """
    Generate a 1000x1500px Pinterest pin.

    All pins: white headline box on photo, no dark overlay.
    Pins b and e: white box + coloured CTA bar below.
    Pins a, c, d: white box only.
    Photo concept drives the background via Gemini (with retry).
    """
    vid        = copy_data.get("variation_id", "") or copy_data.get("id", "")
    var_letter = vid[-1].lower() if vid and vid[-1].isalpha() else "a"

    try:
        bg = _generate_background_with_retry(var_letter)
    except Exception as e:
        print(f"    All Gemini attempts failed: {e}")
        bg = _placeholder_background(copy_data.get("topic", ""))

    print(f"    [DEBUG] Raw Gemini image: {bg.size[0]}x{bg.size[1]} px")
    bg.save("/tmp/debug_raw_gemini.png")

    _centering = {
        "a": (0.5, 0.0),  # close-up hands — content at top
        "b": (0.5, 0.0),  # full portrait — face at top
        "c": (0.5, 0.2),  # dark editorial — slightly above center
        "d": (0.5, 0.5),  # flat lay overhead — content is centered
        "e": (0.5, 0.3),  # airy workspace — slightly above center
    }
    bg = ImageOps.fit(bg, (PIN_W, PIN_H), Image.LANCZOS,
                      centering=_centering.get(var_letter, (0.5, 0.0)))

    # No overlay — white box provides contrast
    bg = _composite_white_box(bg, copy_data, fonts, _has_cta_bar(copy_data))

    tmp = Path(tempfile.mktemp(suffix=".png"))
    bg.save(tmp, "PNG", optimize=False)
    return tmp
