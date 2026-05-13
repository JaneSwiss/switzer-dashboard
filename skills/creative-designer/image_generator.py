from __future__ import annotations

import os
import io
import re
import math
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

from font_manager import setup_fonts, load_font, load_variable_font


# ── Constants ─────────────────────────────────────────────────────────────────

TEXT_WHITE  = (255, 255, 255)
TEXT_DARK   = (56, 56, 56)       # #383838 charcoal — headline on white box
LABEL_COLOR = (187, 176, 170)    # warm taupe — watermark
BOX_WHITE   = (255, 255, 255)    # white headline box

# 10-color palette — each variation letter gets a unique color per topic.
# Offsets guarantee all 5 pins in a topic always use different colors.
PIN_PALETTE = [
    (242, 201,  76),  # yellow        #F2C94C
    (196, 113,  79),  # terracotta    #C4714F
    (107,  63,  42),  # chocolate     #6B3F2A
    (122, 140, 110),  # sage          #7A8C6E
    (201, 144, 138),  # dusty pink    #C9908A
    (123,  59,  78),  # burgundy      #7B3B4E
    ( 44,  62,  80),  # navy          #2C3E50
    (212, 133, 106),  # warm coral    #D4856A
    (107, 122,  71),  # olive         #6B7A47
    ( 92, 122, 140),  # slate blue    #5C7A8C
]
_VAR_OFFSET = {"a": 0, "b": 2, "c": 4, "d": 6, "e": 8}

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


_SCENE_FRAMING = {
    "person":     ("No text, no logos. Rich scene detail fills every corner of the frame. "
                   "Portrait orientation 2:3 ratio."),
    "flat_lay":   ("No person, no hands, no text, no logos. Every corner of the frame filled "
                   "with styled elements — nothing empty. Portrait orientation 2:3 ratio."),
    "workspace":  ("No person, no text, no logos. Rich environmental detail fills every corner "
                   "of the frame from desk surface to upper wall — nothing empty, no blank ceiling. "
                   "Portrait orientation 2:3 ratio."),
    "hands_only": ("No face visible, no text, no logos. The entire frame filled with hands, "
                   "surface texture and props — nothing empty. Portrait orientation 2:3 ratio."),
}

_VAR_SCENE_FALLBACK = {"a": "hands_only", "b": "person", "c": "person",
                        "d": "flat_lay",   "e": "workspace"}

LAYOUTS = {
    "A": {
        "gemini_instruction": (
            "The human subject is positioned on the left third of the frame only, facing slightly "
            "right toward the center. The right two-thirds of the frame is a clean, softly blurred "
            "or plain background — completely empty of any subject, hands, or props. Do not place "
            "any part of the subject in the right half of the frame."
        ),
        "box_x_pct":  0.70,
        "box_y_pct":  0.50,
        "safe_zone":  (500, 0, 1000, 1500),
    },
    "B": {
        "gemini_instruction": (
            "The human subject is positioned on the right third of the frame only, facing slightly "
            "left toward the center. The left two-thirds of the frame is a clean, softly blurred "
            "or plain background — completely empty of any subject, hands, or props. Do not place "
            "any part of the subject in the left half of the frame."
        ),
        "box_x_pct":  0.30,
        "box_y_pct":  0.50,
        "safe_zone":  (0, 0, 500, 1500),
    },
    "C": {
        "gemini_instruction": (
            "Strict 90-degree overhead top-down flat lay. Styled objects arranged around the outer "
            "edges and corners of the frame only. The center of the frame is intentionally left as "
            "clean empty surface — no objects, no props in the center. No person, no hands."
        ),
        "box_x_pct":  0.50,
        "box_y_pct":  0.50,
        "safe_zone":  (200, 400, 800, 1100),
    },
    "D": {
        "gemini_instruction": (
            "Wide medium shot of a fully styled workspace or interior. The upper third of the frame "
            "is a clean wall with minimal detail — empty enough for a text overlay. Rich environmental "
            "detail fills the lower two-thirds of the frame. No person."
        ),
        "box_x_pct":  0.50,
        "box_y_pct":  0.20,
        "safe_zone":  (0, 0, 1000, 500),
    },
}

# ── Gemini image generation ────────────────────────────────────────────────────

def _build_gemini_prompt(variation_letter: str = "a",
                          scene_type: str = "",
                          layout: str = "C",
                          retry_prefix: str = "") -> str:
    """
    Build the Gemini prompt: layout instruction → photo concept → scene framing → fixed suffix.
    layout drives spatial composition; scene_type provides the framing constraint.
    retry_prefix is prepended on retries only.
    """
    hint         = _SCENE_HINTS.get(variation_letter.lower(), _SCENE_HINTS["a"])
    st           = scene_type or _VAR_SCENE_FALLBACK.get(variation_letter.lower(), "person")
    framing      = _SCENE_FRAMING.get(st, "")
    layout_instr = LAYOUTS.get(layout.upper(), LAYOUTS["C"])["gemini_instruction"]
    prompt = (
        f"{layout_instr} "
        f"{hint} "
        f"{framing} "
        "No text, no words, no letters, no numbers, no typography anywhere in the image. "
        "Never generate a laptop screen, phone screen, tablet screen, or any device "
        "showing website content, apps, or UI. Real lifestyle photography only — "
        "no mockups, no screens, no digital displays of any kind. "
        "Aesthetic: quiet luxury, feminine, sophisticated, magazine quality. "
        "Portrait orientation 2:3 ratio."
    )
    return (retry_prefix + prompt) if retry_prefix else prompt


def _generate_background_gemini(variation_letter: str = "a",
                                  scene_type: str = "",
                                  layout: str = "C",
                                  retry_prefix: str = "") -> Image.Image:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set in environment.")

    from google import genai
    from google.genai import types
    import base64

    client   = genai.Client(api_key=api_key)
    prompt   = _build_gemini_prompt(variation_letter, scene_type, layout, retry_prefix)
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


def _generate_background_with_retry(variation_letter: str = "a",
                                      scene_type: str = "",
                                      layout: str = "C") -> Image.Image:
    """Retry up to MAX_ATTEMPTS. On retries, prepend stronger no-text instruction."""
    last_err: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        prefix = _RETRY_PREFIX if attempt > 0 else ""
        if attempt > 0:
            print(f"    Retrying ({attempt + 1}/{MAX_ATTEMPTS})...")
        try:
            return _generate_background_gemini(variation_letter, scene_type, layout, prefix)
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
    total_w = sum(s[1].getbbox(s[0])[2] - s[1].getbbox(s[0])[0] for s in word_specs)
    total_w += space_w * (len(word_specs) - 1)
    x = (PIN_W - total_w) // 2
    for i, spec in enumerate(word_specs):
        word, font, color = spec[0], spec[1], spec[2]
        stroke_fill = spec[3] if len(spec) > 3 else None
        if stroke_fill is not None:
            draw.text((x, y), word, font=font, fill=color,
                      stroke_width=1, stroke_fill=stroke_fill)
        else:
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


def _pin_color(copy_data: dict) -> tuple:
    """Unique color for this pin within its topic — accent, CTA bar, or rule."""
    vid = copy_data.get("variation_id", "") or copy_data.get("id", "")
    var_letter = vid[-1].lower() if vid and vid[-1].isalpha() else "a"
    offset = _VAR_OFFSET.get(var_letter, 0)
    return PIN_PALETTE[(_topic_number(copy_data) - 1 + offset) % len(PIN_PALETTE)]

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


def _find_best_zone(image: Image.Image, box_h: int) -> int:
    """
    Analyse background brightness to find the best horizontal zone for the white box.
    Scores each zone on mean brightness vs variance. Penalises watermark overlap.
    """
    from PIL import ImageStat
    gray  = image.convert("L")
    zones = [(0, 500), (500, 1000), (1000, 1500)]

    best_score      = -float("inf")
    best_zone_start = 1000

    for zone_start, zone_end in zones:
        region = gray.crop((0, zone_start, PIN_W, zone_end))
        stat   = ImageStat.Stat(region)
        score  = stat.mean[0] - stat.var[0] * 0.5

        zone_center = (zone_start + zone_end) // 2
        if zone_center + box_h / 2 > 1380:
            score -= 999

        if score > best_score:
            best_score      = score
            best_zone_start = zone_start

    box_top_y = best_zone_start + (500 - box_h) // 2
    return max(60, min(box_top_y, PIN_H - box_h - 80))


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

    regular_font      = load_font(fonts.get("serif"),           headline_size)
    italic_font       = load_font(fonts.get("serif_italic"),    headline_size)
    bold_italic_font  = load_variable_font(fonts.get("serif_bold_italic"), headline_size)
    watermark_font    = load_font(fonts.get("sans"),            watermark_size)

    box_w    = int(PIN_W * 0.86)
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
    box_h        = block_h + pad_y * 2
    _layout_cfg  = LAYOUTS.get(copy_data.get("layout", "C").upper(), LAYOUTS["C"])
    box_x        = int(PIN_W * _layout_cfg["box_x_pct"]) - (box_w // 2)
    box_y        = int(PIN_H * _layout_cfg["box_y_pct"]) - (box_h // 2)
    box_y        = max(60, min(box_y, PIN_H - box_h - 80))
    box_x        = max(20, min(box_x, PIN_W - box_w - 20))

    pin_color = _pin_color(copy_data)

    # Thin 6px colored rule directly above white box — pin c only
    vid_last = (copy_data.get("variation_id", "") or copy_data.get("id", ""))[-1:].lower()
    if vid_last == "c":
        draw.rectangle([box_x, box_y - 6, box_x + box_w, box_y], fill=pin_color)

    # White headline box
    draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h], fill=BOX_WHITE)

    # Headline in dark charcoal; pins a and d get coloured + italic highlights
    uses_accent  = _uses_headline_accent(copy_data)
    accent_color = pin_color if uses_accent else None
    y   = box_y + pad_y
    idx = 0
    for line_words in word_lines:
        specs = []
        for word in line_words:
            accented = _is_accent(word, highlight, idx, fallback)
            font     = bold_italic_font if accented else regular_font
            color    = accent_color if (uses_accent and accented) else TEXT_DARK
            stroke_fill = (pin_color if (uses_accent and accented) else TEXT_DARK) if accented else None
            specs.append((word, font, color, stroke_fill))
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
                       fill=pin_color)
        sub_y = bar_y + bar_pad
        for sl in sub_lines:
            _draw_word_line(draw, [(w, sub_font, TEXT_WHITE) for w in sl], sub_y)
            sub_y += sub_lh

    _draw_watermark(draw, watermark_font)
    return img


def _face_in_safe_zone(image: Image.Image, safe_zone: tuple) -> bool:
    """Return True if a detected face bounding box overlaps the safe_zone (x1,y1,x2,y2)."""
    try:
        import cv2
        import numpy as np
        img_arr = np.array(image.convert("RGB"))
        gray    = cv2.cvtColor(img_arr, cv2.COLOR_RGB2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if len(faces) == 0:
            return False
        sx1, sy1, sx2, sy2 = safe_zone
        for (fx, fy, fw, fh) in faces:
            if fx < sx2 and fx + fw > sx1 and fy < sy2 and fy + fh > sy1:
                return True
        return False
    except Exception:
        return False


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
    scene_type = copy_data.get("scene_type", "")

    # Derive layout from copy_data, falling back through scene_type → variation_letter
    layout = copy_data.get("layout", "")
    if not layout:
        st     = scene_type or _VAR_SCENE_FALLBACK.get(var_letter, "person")
        layout = {"person": "B", "flat_lay": "C", "workspace": "D", "hands_only": "A"}.get(st, "C")
    layout     = layout.upper()
    layout_cfg = LAYOUTS.get(layout, LAYOUTS["C"])

    _centering = {
        "a": (0.5, 0.0),
        "b": (0.5, 0.0),
        "c": (0.5, 0.2),
        "d": (0.5, 0.5),
        "e": (0.5, 0.3),
    }

    _MAX_FD_RETRIES = 2
    bg = None
    for _fd_attempt in range(_MAX_FD_RETRIES + 1):
        try:
            raw_bg = _generate_background_with_retry(var_letter, scene_type, layout)
        except Exception as e:
            print(f"    All Gemini attempts failed: {e}")
            raw_bg = _placeholder_background(copy_data.get("topic", ""))

        cropped = ImageOps.fit(raw_bg, (PIN_W, PIN_H), Image.LANCZOS,
                               centering=_centering.get(var_letter, (0.5, 0.0)))

        if _face_in_safe_zone(cropped, layout_cfg["safe_zone"]) and _fd_attempt < _MAX_FD_RETRIES:
            print(f"    Face detected in safe zone — retrying ({_fd_attempt + 1}/{_MAX_FD_RETRIES})")
            continue

        bg = cropped
        break

    if bg is None:
        bg = _placeholder_background(copy_data.get("topic", ""))

    # No overlay — white box provides contrast
    bg = _composite_white_box(bg, copy_data, fonts, _has_cta_bar(copy_data))

    tmp = Path(tempfile.mktemp(suffix=".png"))
    bg.save(tmp, "PNG", optimize=False)
    return tmp
