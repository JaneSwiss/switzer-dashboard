#!/usr/bin/env python3
"""
Canva Full Pipeline — generates a Gemini background photo + Pinterest copy
for a single page, uploads the photo to Cloudinary, and outputs a JSON
payload that Claude applies to the design via Canva MCP tools.

Usage (called once per page by Claude):
  python3 skills/pinterest-agent/canva_full_pipeline.py \
      --page 1 \
      --topics-file data/pinterest-agent/topics-2026-04-30.json \
      --txn-file /tmp/canva_full/txn.json \
      --output /tmp/canva_full/page01_payload.json

Output JSON:
  {
    "page":            int,
    "variation_id":    str,
    "keyword":         str,
    "cloudinary_url":  str,
    "copy_operations": [{"type":"replace_text","element_id":"...","text":"..."}],
    "page_id":         str,   # from txn pages array
    "topic":           str
  }

Architecture:
  Python handles: Gemini image generation, Cloudinary upload, copy generation.
  Claude handles: Canva MCP calls (upload-asset-from-url, insert_fill,
                  replace_text, get-design-thumbnail, commit).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# ─── Page → topic/variation mapping ──────────────────────────────────────────

def build_page_map(topics_file: Path) -> dict[int, dict]:
    """
    Map page numbers 1–25 to the first 5 topics × 5 variations.
    Returns {page_number: {variation_id, keyword, design_brief, maps_to_product, ...}}
    """
    data   = json.loads(topics_file.read_text())
    topics = data["topics"]
    page_map: dict[int, dict] = {}
    page = 1
    for topic in topics[:5]:
        for var in topic["variations"]:
            page_map[page] = {
                "topic_id":        topic["topic_id"],
                "keyword":         topic["keyword"],
                "topic":           topic["topic"],
                "maps_to_product": topic["maps_to_product"],
                "variation_id":    var["id"],
                "design_brief":    var["design_brief"],
                "pin_headline":    var.get("pin_headline", ""),
                "highlight_words": var.get("highlight_words", []),
            }
            page += 1
            if page > 25:
                break
        if page > 25:
            break
    return page_map


# ─── Gemini image generation ──────────────────────────────────────────────────

_NO_TEXT_PREFIX = (
    "No text, no words, no letters, no numbers, no typography, "
    "no placeholder text, no lorem ipsum, no labels anywhere in the image. "
)

_PORTRAIT_SUFFIX = (
    " Portrait orientation 2:3 ratio. "
    "Quiet luxury, editorial magazine quality, feminine, sophisticated. "
    "Muted warm palette. No text, no logos, no overlays anywhere in the image. "
    "Never generate a laptop screen, phone screen, tablet screen, or any device "
    "showing website content, apps, or UI. Real lifestyle photography only — "
    "no mockups, no screens, no digital displays of any kind."
)


def _build_photo_prompt(design_brief: str, attempt: int = 0) -> str:
    prefix = _NO_TEXT_PREFIX
    if attempt > 0:
        prefix = (
            "CRITICAL: zero text, zero letters, zero numbers, zero words, "
            "zero typography anywhere in the image. Reject and regenerate if "
            "any text appears. "
        ) + prefix
    return prefix + design_brief.strip() + _PORTRAIT_SUFFIX


def generate_gemini_photo(design_brief: str) -> bytes:
    """
    Generate a background photo from design_brief using Gemini.
    Returns raw JPEG bytes.
    Tries Imagen 4 models first, then Gemini flash models.
    """
    from google import genai
    from google.genai import types

    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set.")

    client   = genai.Client(api_key=api_key)
    last_err = None

    for attempt in range(3):
        prompt = _build_photo_prompt(design_brief, attempt)
        if attempt > 0:
            print(f"    Gemini retry {attempt + 1}/3...")

        # Imagen 4 models (best quality)
        for model in ("imagen-4.0-generate-001", "imagen-4.0-fast-generate-001"):
            try:
                resp = client.models.generate_images(
                    model=model,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio="9:16",
                        output_mime_type="image/jpeg",
                    ),
                )
                if resp.generated_images:
                    return resp.generated_images[0].image.image_bytes
            except Exception as e:
                last_err = e

        # Gemini flash/pro models (fallback)
        for model in ("gemini-2.5-flash-image", "gemini-2.0-flash-preview-image-generation"):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                    ),
                )
                for part in resp.candidates[0].content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        raw = part.inline_data.data
                        if isinstance(raw, str):
                            raw = base64.b64decode(raw)
                        return raw
            except Exception as e:
                last_err = e

    raise RuntimeError(f"All Gemini attempts failed: {last_err}")


# ─── Cloudinary upload ────────────────────────────────────────────────────────

def upload_to_cloudinary(image_bytes: bytes, slug: str) -> str:
    """Upload image bytes to Cloudinary, return public HTTPS URL."""
    import hashlib
    import requests

    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    api_key    = os.getenv("CLOUDINARY_API_KEY", "")
    api_secret = os.getenv("CLOUDINARY_API_SECRET", "")

    if not all([cloud_name, api_key, api_secret]):
        raise RuntimeError("Cloudinary credentials missing in .env")

    public_id = f"switzertemplates/pins/{slug}"
    timestamp = int(time.time())
    params    = {"public_id": public_id, "timestamp": timestamp}
    body      = "&".join(f"{k}={v}" for k, v in sorted(params.items())) + api_secret
    signature = hashlib.sha1(body.encode()).hexdigest()

    resp = requests.post(
        f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload",
        data={"api_key": api_key, "timestamp": timestamp,
              "signature": signature, "public_id": public_id},
        files={"file": ("photo.jpg", image_bytes, "image/jpeg")},
        timeout=60,
    )
    data = resp.json()
    if "secure_url" not in data:
        raise RuntimeError(f"Cloudinary upload failed: {data}")
    return data["secure_url"]


# ─── Copy generation (word-limited rules) ────────────────────────────────────

import anthropic

_SYSTEM_PROMPT = (
    "You are a Pinterest pin copy writer for Switzer Templates, a digital product business "
    "selling Canva templates, Wix website templates, branding kits and Instagram templates "
    "to small business owners and Etsy sellers. Write in plain language, active voice, "
    "sentence case. Never use all caps. No hashtags."
)

_WORD_LIMITS = {"headline": 7, "body": 5, "cta": 4}


def _classify_slots(slots: list[dict]) -> list[dict]:
    result = []
    for s in slots:
        s = dict(s)
        s["role"]      = "cta" if s["height"] < 50 else None
        s["max_words"] = _WORD_LIMITS.get("cta", 4) if s["height"] < 50 else 0
        result.append(s)

    non_cta = [s for s in result if s["role"] is None]
    if non_cta:
        tallest = max(non_cta, key=lambda s: s["height"])
        tallest["role"] = "body"
        for s in non_cta:
            if s["element_id"] != tallest["element_id"]:
                s["role"] = "headline"

    for s in result:
        if s["max_words"] == 0:
            s["max_words"] = _WORD_LIMITS.get(s["role"], 7)
    return result


def _user_prompt(classified: list[dict], topic: str, product: str,
                 retry_note: str = "") -> str:
    slots = "\n".join(
        f"- element_id: {s['element_id']}\n"
        f"  Role: {s['role']}\n"
        f"  Max words: {s['max_words']}\n"
        f"  Current placeholder text (for context only): {s['current_text']}"
        for s in classified
    )
    return (
        "STRICT RULES — do not break these under any circumstances:\n\n"
        "- headline role: maximum 7 words. Short, punchy, benefit-driven.\n"
        "- body role: maximum 5 words. A tight phrase, not a sentence.\n"
        "- cta role: maximum 4 words. Action verb first. "
        "Examples: 'Shop the kit', 'Get it now', 'Grab yours today'.\n"
        "- Never write full sentences that fill the entire space. Less is more.\n"
        "- Never repeat the same idea across headline and body.\n\n"
        f"{retry_note}"
        f"{slots}\n\n"
        f"Topic: {topic}\n"
        f"Product being promoted: {product}\n"
        "Target audience: small business owners and coaches\n"
        "Return JSON only with no preamble or markdown:\n"
        '{"elements": [{"element_id": "...", "new_text": "..."}, ...]}'
    )


def generate_copy(classified: list[dict], topic: str, product: str,
                  api_key: str, retry_note: str = "") -> list[dict]:
    client  = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_prompt(classified, topic, product, retry_note)}],
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$",          "", raw)
    return json.loads(raw).get("elements", [])


def validate_and_retry(classified: list[dict], generated: list[dict],
                        topic: str, product: str, api_key: str) -> list[dict]:
    limit_map = {s["element_id"]: s["max_words"] for s in classified}

    def violations(elements):
        out = []
        for el in elements:
            wc    = len(el.get("new_text", "").split())
            limit = limit_map.get(el["element_id"], 999)
            if wc > limit:
                out.append(f"{el['element_id'][-12:]} is {wc}w (max {limit}): \"{el['new_text']}\"")
        return out

    current = generated
    for attempt in range(3):
        bad = violations(current)
        if not bad:
            return current
        if attempt >= 2:
            break
        note = ("IMPORTANT — previous response exceeded word limits. "
                "These MUST be shorter:\n" +
                "\n".join(f"  • {v}" for v in bad) + "\n\n")
        current = generate_copy(classified, topic, product, api_key, note)

    for el in current:
        limit = limit_map.get(el["element_id"], 999)
        words = el.get("new_text", "").split()
        if len(words) > limit:
            el["new_text"] = " ".join(words[:limit])
    return current


def generate_page_copy(txn_data: dict, page_number: int,
                        keyword: str, product: str, api_key: str) -> list[dict]:
    """Extract editable text slots for the page and return validated copy operations."""
    all_rt = txn_data.get("richtexts", [])

    page_texts = [
        rt for rt in all_rt
        if rt.get("page_index") == page_number
        and rt.get("containerElement", {}).get("type") == "TEXT"
        and rt.get("regions")
    ]

    slots = []
    for rt in page_texts:
        text = "".join(r.get("text", "") for r in rt["regions"]).strip()
        dim  = rt["containerElement"].get("dimension", {})
        if "switzertemplates.com" in text.lower():
            continue
        slots.append({
            "element_id":   rt["element_id"],
            "current_text": text,
            "width":        round(dim.get("width", 0), 2),
            "height":       round(dim.get("height", 0), 2),
        })

    if not slots:
        return []

    classified = _classify_slots(slots)

    print(f"  Copy slots ({len(classified)}):")
    for s in classified:
        print(f"    {s['role']:8s}  max={s['max_words']}w  '{s['current_text'][:40]}'")

    generated = generate_copy(classified, keyword, product, api_key)
    validated = validate_and_retry(classified, generated, keyword, product, api_key)

    operations = [
        {"type": "replace_text", "element_id": el["element_id"], "text": el["new_text"]}
        for el in validated
    ]

    limit_map = {s["element_id"]: s for s in classified}
    print(f"  Generated copy:")
    for op in operations:
        role = limit_map.get(op["element_id"], {}).get("role", "?")
        wc   = len(op["text"].split())
        print(f"    {role:8s}  {wc}w  \"{op['text']}\"")

    return operations


# ─── CLI entry point ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page",        type=int, required=True)
    parser.add_argument("--topics-file", type=Path,
                        default=PROJECT_ROOT / "data/pinterest-agent/topics-2026-04-30.json")
    parser.add_argument("--txn-file",    type=Path, required=True,
                        help="JSON file from start-editing-transaction")
    parser.add_argument("--output",      type=Path, required=True)
    parser.add_argument("--skip-image",  action="store_true",
                        help="Skip Gemini generation (use existing cloudinary_url in output if present)")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    # Load page map
    page_map = build_page_map(args.topics_file)
    if args.page not in page_map:
        print(f"Error: page {args.page} not in map (1–{max(page_map)})", file=sys.stderr)
        sys.exit(1)

    info     = page_map[args.page]
    var_id   = info["variation_id"]
    keyword  = info["keyword"]
    product  = info["maps_to_product"]
    brief    = info["design_brief"]

    print(f"\n{'='*60}")
    print(f"  Page {args.page}: [{var_id}] {keyword}")
    print(f"{'='*60}")

    # Load transaction data
    txn_data = json.loads(args.txn_file.read_text())

    # Get page_id for this page
    pages    = txn_data.get("pages", [])
    page_obj = next((p for p in pages if p["page_number"] == args.page), None)
    page_id  = page_obj["page_id"] if page_obj else ""

    # Existing output (check for cached URL)
    existing: dict = {}
    if args.output.exists():
        try:
            existing = json.loads(args.output.read_text())
        except Exception:
            pass

    cloudinary_url = existing.get("cloudinary_url", "")

    # ── Step 1: Gemini image generation + Cloudinary upload ──────────────────
    if not args.skip_image or not cloudinary_url:
        print(f"  [1] Generating Gemini photo ({var_id})...")
        print(f"      Brief: {brief[:80]}...")
        try:
            img_bytes = generate_gemini_photo(brief)
            print(f"  [1] Generated ({len(img_bytes) // 1024}KB). Uploading to Cloudinary...")
            slug      = f"pins-01-p{args.page:02d}-{var_id}-{int(time.time())}"
            cloudinary_url = upload_to_cloudinary(img_bytes, slug)
            print(f"  [1] Cloudinary URL: {cloudinary_url}")
        except Exception as e:
            print(f"  [1] Image generation failed: {e}")
            cloudinary_url = ""
    else:
        print(f"  [1] Using cached Cloudinary URL: {cloudinary_url}")

    # ── Step 2: Generate copy ─────────────────────────────────────────────────
    print(f"  [2] Generating copy for '{keyword}'...")
    copy_ops = generate_page_copy(txn_data, args.page, keyword, product, api_key)

    # ── Output ────────────────────────────────────────────────────────────────
    output = {
        "page":            args.page,
        "variation_id":    var_id,
        "keyword":         keyword,
        "product":         product,
        "cloudinary_url":  cloudinary_url,
        "copy_operations": copy_ops,
        "page_id":         page_id,
        "topic":           info["topic"],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"  Output: {args.output}")


if __name__ == "__main__":
    main()
