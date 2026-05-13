"""
Font manager - downloads and caches brand fonts for pin text compositing.

Fonts are stored in skills/creative-designer/fonts/.
Falls back to system serif/sans-serif if download fails.
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

FONTS_DIR = Path(__file__).parent / "fonts"

# Google Fonts static TTF download URLs (stable CDN paths)
FONT_URLS = {
    "NotoSerifDisplay-Light.ttf": (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifdisplay/"
        "static/NotoSerifDisplay-Light.ttf"
    ),
    "NotoSerifDisplay-LightItalic.ttf": (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifdisplay/"
        "static/NotoSerifDisplay-LightItalic.ttf"
    ),
    "NotoSerifDisplay-Italic[wdth,wght].ttf": (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifdisplay/"
        "NotoSerifDisplay-Italic%5Bwdth%2Cwght%5D.ttf"
    ),
    "Montserrat-Regular.ttf": (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/"
        "static/Montserrat-Regular.ttf"
    ),
}

# System font fallbacks (checked in order, first found wins)
SERIF_FALLBACKS = [
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/System/Library/Fonts/Times New Roman.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
]

SANS_FALLBACKS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def ensure_fonts_dir():
    FONTS_DIR.mkdir(parents=True, exist_ok=True)


def _download_font(name: str, url: str) -> bool:
    dest = FONTS_DIR / name
    if dest.exists() and dest.stat().st_size > 10_000:
        return True

    print(f"  Downloading {name}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read()
        dest.write_bytes(data)
        if dest.stat().st_size < 10_000:
            dest.unlink()
            return False
        print(f"  Saved {name} ({dest.stat().st_size // 1024}KB)")
        return True
    except Exception as e:
        print(f"  Could not download {name}: {e}")
        return False


def _find_system_font(candidates: list) -> str | None:
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def setup_fonts() -> dict:
    """
    Return a dict with 'serif' and 'sans' keys pointing to usable font paths.
    Attempts to download brand fonts first; falls back to system fonts.
    """
    ensure_fonts_dir()

    fonts = {}

    # --- Serif regular (headline) ---
    serif_path = FONTS_DIR / "NotoSerifDisplay-Light.ttf"
    if not (serif_path.exists() and serif_path.stat().st_size > 10_000):
        _download_font("NotoSerifDisplay-Light.ttf", FONT_URLS["NotoSerifDisplay-Light.ttf"])

    if serif_path.exists() and serif_path.stat().st_size > 10_000:
        fonts["serif"] = str(serif_path)
    else:
        fallback = _find_system_font(SERIF_FALLBACKS)
        fonts["serif"] = fallback
        if fallback:
            print(f"  Using system serif fallback: {fallback}")
        else:
            print("  Warning: no serif font found - text may use Pillow default")

    # --- Serif italic (for mixed italic/regular headline treatment) ---
    serif_italic_path = FONTS_DIR / "NotoSerifDisplay-LightItalic.ttf"
    if not (serif_italic_path.exists() and serif_italic_path.stat().st_size > 10_000):
        _download_font("NotoSerifDisplay-LightItalic.ttf", FONT_URLS["NotoSerifDisplay-LightItalic.ttf"])

    if serif_italic_path.exists() and serif_italic_path.stat().st_size > 10_000:
        fonts["serif_italic"] = str(serif_italic_path)
    else:
        fonts["serif_italic"] = fonts.get("serif")  # graceful fallback to regular

    # --- Serif bold italic (variable font, wght=600 — for highlighted words) ---
    serif_bi_name = "NotoSerifDisplay-Italic[wdth,wght].ttf"
    serif_bi_path = FONTS_DIR / serif_bi_name
    if not (serif_bi_path.exists() and serif_bi_path.stat().st_size > 10_000):
        _download_font(serif_bi_name, FONT_URLS[serif_bi_name])
    fonts["serif_bold_italic"] = (
        str(serif_bi_path) if serif_bi_path.exists() and serif_bi_path.stat().st_size > 10_000
        else fonts.get("serif_italic")
    )

    # --- Sans (category label + watermark) ---
    sans_path = FONTS_DIR / "Montserrat-Regular.ttf"
    if not (sans_path.exists() and sans_path.stat().st_size > 10_000):
        _download_font("Montserrat-Regular.ttf", FONT_URLS["Montserrat-Regular.ttf"])

    if sans_path.exists() and sans_path.stat().st_size > 10_000:
        fonts["sans"] = str(sans_path)
    else:
        fallback = _find_system_font(SANS_FALLBACKS)
        fonts["sans"] = fallback
        if fallback:
            print(f"  Using system sans fallback: {fallback}")
        else:
            print("  Warning: no sans font found - text may use Pillow default")

    return fonts


def load_font(path: str | None, size: int):
    """Load a PIL ImageFont. Returns default font if path is None or fails."""
    from PIL import ImageFont
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def load_variable_font(path: str | None, size: int, wdth: float = 100, wght: float = 600):
    """Load a variable font and set wdth/wght axes. Falls back to load_font on error."""
    from PIL import ImageFont
    if path:
        try:
            font = ImageFont.truetype(path, size)
            font.set_variation_by_axes([wdth, wght])
            return font
        except Exception:
            pass
    return load_font(path, size)
