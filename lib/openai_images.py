"""
Shared OpenAI image generation — used by agents/blog-seo-agent/blog_seo_agent.py
(cover images + inline section illustrations) and skills/creative-designer/image_generator.py
(Pinterest pin backgrounds).

A thin wrapper only: generate, decode, compress, return bytes + a rough cost estimate.
Retry/fallback behavior stays with each caller — they already have different philosophies
for it (blog_seo_agent logs-and-continues per prompt; creative-designer has its own
multi-attempt retry loop with an escalating prompt prefix) and shouldn't have that fought
by a shared layer underneath them.

Setup required in .env:
  OPENAI_API_KEY=sk-...
  OPENAI_IMAGE_QUALITY=medium   (optional — low | medium | high, defaults to medium)
"""
from __future__ import annotations

import base64
import io
import os
import time

from openai import OpenAI
from PIL import Image

MODEL = "gpt-image-2"

# aspect_ratio -> OpenAI size preset. Fixed presets only (not arbitrary sizes) for
# predictable cost/reliability.
_SIZE_PRESETS = {
    "16:9": "1536x1024",
    "9:16": "1024x1536",
}
_DEFAULT_SIZE = "1024x1024"

# Rough per-image cost by quality tier, for the cost tally in the completion email.
# These are estimates, not billed truth — OpenAI's actual pricing varies by exact size/
# tier and changes over time; treat this as a ballpark, not an invoice.
_COST_ESTIMATE = {
    "low": 0.02,
    "medium": 0.07,
    "high": 0.19,
}

# Small pacing delay between successive calls when used in a tight loop (one blog post
# run can generate 15-20+ images across a few posts) — cheap insurance against a burst
# tripping a rate limit mid-run. Set to 0 to disable.
PACING_DELAY_SECONDS = 1.5

# Long edge cap + JPEG quality for the compression pass — meaningfully smaller files with
# negligible visible loss, done locally via Pillow rather than a paid compression API.
_MAX_LONG_EDGE = 1600
_JPEG_QUALITY = 82


def _resolve_size(aspect_ratio: str) -> str:
    return _SIZE_PRESETS.get(aspect_ratio, _DEFAULT_SIZE)


def _resolve_quality(quality: str | None) -> str:
    if quality:
        return quality
    return os.getenv("OPENAI_IMAGE_QUALITY", "medium")


def _compress(raw_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")

    long_edge = max(img.size)
    if long_edge > _MAX_LONG_EDGE:
        scale = _MAX_LONG_EDGE / long_edge
        new_size = (round(img.width * scale), round(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, "JPEG", quality=_JPEG_QUALITY, optimize=True)
    return out.getvalue()


def generate_image_bytes(
    prompt: str,
    aspect_ratio: str = "1:1",
    quality: str | None = None,
    output_format: str = "jpeg",
) -> tuple[bytes, float]:
    """
    Generate one image via OpenAI's gpt-image-2, compress it, and return
    (compressed_jpeg_bytes, rough_cost_estimate_usd).

    Raises on failure — callers keep their own try/except + log_error() unchanged.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in .env")

    resolved_quality = _resolve_quality(quality)
    client = OpenAI(api_key=api_key)

    response = client.images.generate(
        model=MODEL,
        prompt=prompt,
        size=_resolve_size(aspect_ratio),
        quality=resolved_quality,
        output_format=output_format,
        n=1,
    )

    # gpt-image-2 doesn't accept response_format — it always returns b64_json.
    # Kept the url fallback anyway in case that ever changes.
    result = response.data[0]
    if getattr(result, "b64_json", None):
        raw_bytes = base64.b64decode(result.b64_json)
    elif getattr(result, "url", None):
        import requests
        raw_bytes = requests.get(result.url, timeout=30).content
    else:
        raise RuntimeError("OpenAI image response had neither b64_json nor url")

    compressed = _compress(raw_bytes)

    cost_estimate = _COST_ESTIMATE.get(resolved_quality, _COST_ESTIMATE["medium"])

    if PACING_DELAY_SECONDS:
        time.sleep(PACING_DELAY_SECONDS)

    return compressed, cost_estimate
