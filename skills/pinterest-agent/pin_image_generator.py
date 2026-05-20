"""
pin_image_generator.py — Pinterest pin image generator

Generates one Gemini Imagen image per pin (9:16 portrait), rotates through
3 prompt types across pins, saves locally, uploads to Cloudinary, and returns
results for Canva insertion.

Prompt type rotation:
    pin 1 → type 1 (general lifestyle)
    pin 2 → type 2 (topic-specific props/objects)
    pin 3 → type 3 (topic-specific person + action)
    pin 4 → type 1 again, etc.

Usage (standalone):
    python3 skills/pinterest-agent/pin_image_generator.py --pages 1-5

Usage (as module):
    from skills.pinterest_agent.pin_image_generator import generate_pin_images
    results = generate_pin_images(page_numbers=[1, 2, 3, 4, 5])
"""

from __future__ import annotations

import os
import sys
import json
import time
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    import anthropic
except ImportError:
    sys.exit("Missing: pip install anthropic")

try:
    import google.genai as genai
    import google.genai.types as genai_types
except ImportError:
    sys.exit("Missing: pip install google-genai")

try:
    import requests
except ImportError:
    sys.exit("Missing: pip install requests")

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("Missing: pip install python-dotenv")

# ── paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOPICS_FILE  = PROJECT_ROOT / "data" / "pinterest-agent" / "topics-2026-04-30.json"
IMAGE_DIR    = PROJECT_ROOT / "outputs" / "pins" / "images"

# ── env ───────────────────────────────────────────────────────────────────────

load_dotenv(PROJECT_ROOT / ".env")
ANTHROPIC_API_KEY       = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY          = os.environ.get("GOOGLE_API_KEY", "")
CLOUDINARY_CLOUD_NAME   = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY_CLD  = os.environ.get("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET   = os.environ.get("CLOUDINARY_API_SECRET", "")

# ── prompt type names ─────────────────────────────────────────────────────────

PROMPT_TYPE_NAMES = {
    1: "GENERAL LIFESTYLE",
    2: "TOPIC SPECIFIC (props/objects)",
    3: "TOPIC SPECIFIC (person + action)",
}

# ── system prompt ─────────────────────────────────────────────────────────────

IMAGE_PROMPT_SYSTEM = """You are generating a single image prompt for a Pinterest pin for SwitzerTemplates.
The image must be visually striking, keyword-relevant, and styled as warm editorial quiet luxury.
The image is portrait orientation (9:16 ratio) — tall, not wide.

THE FEMALE CHARACTER (when present):
- Always has long chocolate brown hair
- Face never fully visible - back, side profile, or hands/wrists only
- OUTFIT - choose freely:
  oversized cream knit jumper, camel oversized coat, white linen shirt,
  chocolate brown blazer, black turtleneck, beige trench coat,
  white oversized sweatshirt, rust coloured knit, grey blazer,
  soft sage green cardigan
- Hands when shown: long gel nails in nude or white French, gold jewellery -
  rings, thin bangles, delicate chain bracelet, small gold hoop earrings visible

COMPOSITION OPTIONS:
1. Woman from behind at a desk, seated, slight 45-degree angle
2. Overhead flat lay, no person, objects arranged loosely
3. Close-up of hands only from above or side, mid-action
4. Woman on sofa or floor with laptop on lap, legs crossed
5. Woman at a café table outdoors or by a window, side profile
6. Woman standing and leaning over a desk, action shot
7. Low angle shot from desk level looking slightly up
8. Wide room shot showing the full luxurious interior, woman small in frame
9. Close-up of one hero object on a surface, blurred background
10. Woman's back and side, looking out a large window, holding a drink

SETTINGS OPTIONS (choose one):
- White marble desk or table, bright airy room with gold accents
- Dark oak oval desk, warm moody interior
- Glass coffee table, cream bouclé sofa visible
- Café table with rattan chairs, outdoors or large window behind
- Travertine or concrete surface, minimal grey interior
- Light grey minimal desk, large floor-to-ceiling windows
- Cream linen surface on a bed or sofa
- Stone or plaster surface, Mediterranean or European interior feel
- Wooden floor, person seated or cross-legged with items around them

DRINKS OPTIONS (choose one or none):
- Starbucks iced latte in clear cup with green straw
- Starbucks matcha in clear cup with green straw
- Latte in a ribbed clear glass
- Espresso in a small ceramic cup on a saucer
- Matcha in a ceramic bowl or small ceramic cup
- Stanley tumbler in cream or sand tone
- Iced coffee in a plain clear glass
- Pretty glass water bottle with a straw
- No drink at all - leave it out entirely

SIGNATURE PROPS (use 1-2, varied):
- Apple MacBook in silver or space grey
- Apple AirPods Max in silver
- Productivity Planner by Intelligent Change - black linen hardcover with gold foil
- Gold jewellery pieces placed casually
- Tortoiseshell claw clip
- Fine-line pen
- Small ceramic object in matte taupe or cream

ACTION OPTIONS (when a person is present, choose one):
- Typing on a laptop
- Writing in a notebook with a pen
- Holding and reading from an iPad
- On a phone call, phone to ear
- Holding and flicking through printed documents or papers
- Reading a hardcover book
- Holding a phone, scrolling
- Writing on a notepad with a fine-line pen, close-up
- Holding an open MacBook while standing
- Reviewing printed papers spread across a desk

PHOTOGRAPHY STYLE (all images):
- Warm editorial quiet luxury - real and lived-in, not staged
- Kodak Portra 400: warm colour grading, visible grain, slightly soft
- Natural window light with directional shadows, never studio lighting
- Shallow depth of field, something slightly blurred in foreground or background
- Intentionally imperfect: one element cropped at frame edge,
  uneven light, visible surface texture, signs of real use
- Candid, not arranged - feels genuinely real

VARIETY IS MANDATORY AND STRICTLY ENFORCED. Before choosing any element check the
used_combinations list in the user message and never repeat anything already used in
this batch.

The woman must always be performing one action from the ACTION OPTIONS list above.
Never just standing or sitting with only a drink. The drink is a secondary prop, not
the main action. The action must be visible and specific in the image description.

You MUST begin your response with a CHOICES block in this exact format, then a blank
line, then the full image prompt:

CHOICES:
composition: [number from 1-10]
setting: [exact setting text chosen]
outfit: [exact outfit text chosen, or "none" if no person]
drink: [exact drink text chosen, or "none"]
props: [comma-separated list of props used]
action: [exact action chosen from ACTION OPTIONS, or "none" if no person]"""


# ── prompt type builders ──────────────────────────────────────────────────────

def _type1_instruction(keyword: str, used_combinations: dict | None = None) -> str:
    uc           = used_combinations or {}
    comp_used    = uc.get("compositions_used", []) or "none yet"
    set_used     = uc.get("settings_used",     []) or "none yet"
    out_used     = uc.get("outfits_used",      []) or "none yet"
    drink_used   = uc.get("drinks_used",       []) or "none yet"
    props_used   = uc.get("props_used",        []) or "none yet"
    actions_used = uc.get("actions_used",      []) or "none yet"
    variety = (
        f"\nVARIETY ENFORCEMENT — already used in this batch:\n"
        f"Compositions already used: {comp_used} — pick a different one.\n"
        f"Settings already used: {set_used} — pick a different one.\n"
        f"Outfits already used: {out_used} — pick a different one.\n"
        f"Drinks already used: {drink_used} — pick a different one or no drink.\n"
        f"Props already used: {props_used} — rotate props, black planner maximum once per 5 pins.\n"
        f"Actions already used: {actions_used} — pick a completely different action. "
        f"Never default to laptop typing unless no other action has been used yet. "
        f"Rotate through the full action list — iPad, phone calls, books, printed documents, "
        f"handwriting are all equally valid and must appear across the batch.\n"
        f"State explicitly which composition number, setting, outfit, drink, props and action "
        f"you chose and confirm none appear in the used lists above.\n"
    )
    return (
        f'Generate a GENERAL LIFESTYLE image prompt for a Pinterest pin about: "{keyword}"\n'
        + variety +
        "\nChoose one composition, one setting, one drink, and one action from the lists above.\n"
        "Scene should loosely relate to the keyword theme but not be too literal.\n"
        "The woman is present and performing the chosen action.\n\n"
        "End with: No text, no words, no writing, no labels, no readable typography\n"
        "anywhere in the image. If a screen is visible it shows only a softly blurred\n"
        "website UI or app - blurred enough that no text is readable. No distorted AI\n"
        "text. No bright colours, no gradients, no studio lighting, no stock photography\n"
        "look, no digital sharpening. Portrait 9:16, high resolution.\n\n"
        "Return the CHOICES block first, then the image prompt."
    )


def _type2_instruction(keyword: str, used_combinations: dict | None = None) -> str:
    uc           = used_combinations or {}
    comp_used    = uc.get("compositions_used", []) or "none yet"
    set_used     = uc.get("settings_used",     []) or "none yet"
    out_used     = uc.get("outfits_used",      []) or "none yet"
    drink_used   = uc.get("drinks_used",       []) or "none yet"
    props_used   = uc.get("props_used",        []) or "none yet"
    actions_used = uc.get("actions_used",      []) or "none yet"
    variety = (
        f"\nVARIETY ENFORCEMENT — already used in this batch:\n"
        f"Compositions already used: {comp_used} — pick a different one.\n"
        f"Settings already used: {set_used} — pick a different one.\n"
        f"Outfits already used: {out_used} — no person needed for this type, use 'none'.\n"
        f"Drinks already used: {drink_used} — pick a different one or no drink.\n"
        f"Props already used: {props_used} — rotate props, black planner maximum once per 5 pins.\n"
        f"Actions already used: {actions_used} — no person in this type, use 'none' for action.\n"
        f"State explicitly which composition number, setting, outfit (none), drink, props "
        f"and action (none) you chose and confirm none appear in the used lists above.\n"
    )
    return (
        f'Generate a TOPIC SPECIFIC (props/objects) image prompt for a Pinterest pin about: "{keyword}"\n'
        + variety +
        "\nDirectly illustrates the keyword topic through objects and scene only - no person needed.\n"
        "Choose one composition and one setting from the lists above.\n"
        "Use a drink or no drink.\n"
        "Screen content is allowed and encouraged - show relevant UI like Etsy dashboard,\n"
        "Canva, Pinterest feed, website template, AI tool - but slightly blurred so\n"
        "individual words are not readable. No handwritten text visible anywhere.\n"
        "Any printed materials, papers, or cards in the scene should show\n"
        "only abstract marks, lines, shapes, or textures - no readable words or\n"
        "font names visible on any surface.\n\n"
        "End with: No distorted AI text, no garbled words, no bright colours,\n"
        "no gradients, no studio lighting. Portrait 9:16, high resolution.\n\n"
        "Return the CHOICES block first, then the image prompt."
    )


def _type3_instruction(keyword: str, used_combinations: dict | None = None) -> str:
    uc           = used_combinations or {}
    comp_used    = uc.get("compositions_used", []) or "none yet"
    set_used     = uc.get("settings_used",     []) or "none yet"
    out_used     = uc.get("outfits_used",      []) or "none yet"
    drink_used   = uc.get("drinks_used",       []) or "none yet"
    props_used   = uc.get("props_used",        []) or "none yet"
    actions_used = uc.get("actions_used",      []) or "none yet"
    variety = (
        f"\nVARIETY ENFORCEMENT — already used in this batch:\n"
        f"Compositions already used: {comp_used} — pick a different one.\n"
        f"Settings already used: {set_used} — pick a different one.\n"
        f"Outfits already used: {out_used} — pick a different one.\n"
        f"Drinks already used: {drink_used} — pick a different one or no drink.\n"
        f"Props already used: {props_used} — rotate props, black planner maximum once per 5 pins.\n"
        f"Actions already used: {actions_used} — pick a completely different action. "
        f"Never default to laptop typing unless no other action has been used yet. "
        f"Rotate through the full action list — iPad, phone calls, books, printed documents, "
        f"handwriting are all equally valid and must appear across the batch.\n"
        f"State explicitly which composition number, setting, outfit, drink, props and action "
        f"you chose and confirm none appear in the used lists above.\n"
    )
    return (
        f'Generate a TOPIC SPECIFIC (person + action) image prompt for a Pinterest pin about: "{keyword}"\n'
        + variety +
        "\nThe woman with long chocolate brown hair performing the chosen action from the ACTION OPTIONS list.\n"
        "Choose a composition, setting, outfit, drink, and action from the lists above.\n"
        "Mid-action, not posed. Back or side profile only.\n"
        "Any printed materials, papers, or cards in the scene should show\n"
        "only abstract marks, lines, shapes, or textures - no readable words or\n"
        "font names visible on any surface.\n\n"
        "End with: No text, no words, no writing, no labels, no readable typography\n"
        "anywhere in the image. If a screen is visible it shows only a softly blurred\n"
        "website UI - blurred enough that no text is readable. No distorted AI text.\n"
        "No bright colours, no gradients, no studio lighting, no stock photography\n"
        "look, no digital sharpening. Portrait 9:16, high resolution.\n\n"
        "Return the CHOICES block first, then the image prompt."
    )


_PROMPT_BUILDERS = {1: _type1_instruction, 2: _type2_instruction, 3: _type3_instruction}


# ── helpers ───────────────────────────────────────────────────────────────────

def keyword_for_page(page_number: int) -> str:
    data   = json.loads(TOPICS_FILE.read_text())
    topics = data.get("topics", [])
    idx    = (page_number - 1) // 5
    if idx < len(topics):
        return topics[idx].get("keyword", f"page-{page_number}")
    return f"page-{page_number}"


def prompt_type_for_page(page_number: int) -> int:
    """Rotate: page 1→type 1, page 2→type 2, page 3→type 3, page 4→type 1, ..."""
    return ((page_number - 1) % 3) + 1


# ── Parse Claude's CHOICES block ─────────────────────────────────────────────

def _parse_prompt_response(raw: str) -> tuple[str, dict]:
    """
    Split Claude's response into (image_prompt, choices_made).

    Handles two formats:
        Format A — explicit header:
            CHOICES:
            composition: 3
            ...
            [blank line]
            [prompt text]

        Format B — choices at top without header (fallback):
            composition: 3
            setting: White marble...
            ...
            [blank line]
            [prompt text]
    """
    _CHOICE_KEYS = {"composition", "setting", "outfit", "drink", "props", "action"}
    choices: dict = {}
    prompt         = raw

    # Strip optional CHOICES: header then try to read key:value lines from top
    body = raw
    if raw.upper().startswith("CHOICES:"):
        body = raw[len("CHOICES:"):].lstrip("\n")

    lines        = body.split("\n")
    prompt_start = 0
    in_choices   = True
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if choices:          # blank line after at least one choice → end of block
                prompt_start = i + 1
                in_choices   = False
                break
            continue
        if in_choices and ":" in stripped:
            key, _, val = stripped.partition(":")
            key_clean   = key.strip().lower().replace(" ", "_")
            if key_clean in _CHOICE_KEYS:
                choices[key_clean] = val.strip()
                prompt_start       = i + 1
            else:
                # First non-choice line — prompt has started
                in_choices   = False
                prompt_start = i
                break
        else:
            in_choices   = False
            prompt_start = i
            break

    if choices:
        prompt = "\n".join(lines[prompt_start:]).strip()

    return prompt, choices


# ── Claude: generate image prompt ────────────────────────────────────────────

def generate_image_prompt(
    keyword: str,
    prompt_type: int,
    used_combinations: dict | None = None,
) -> tuple[str, dict]:
    """Returns (image_prompt, choices_made)."""
    client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    user_msg = _PROMPT_BUILDERS[prompt_type](keyword, used_combinations)
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1200,
        system=IMAGE_PROMPT_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    return _parse_prompt_response(response.content[0].text.strip())


# ── Gemini: generate image ────────────────────────────────────────────────────

def generate_image_bytes(prompt: str) -> bytes | None:
    client = genai.Client(api_key=GOOGLE_API_KEY)
    try:
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config=genai_types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="9:16",
                output_mime_type="image/jpeg",
            ),
        )
        if response.generated_images:
            return response.generated_images[0].image.image_bytes
        print("  Gemini returned no images.")
    except Exception as e:
        print(f"  Gemini error: {e}")
    return None


# ── local save ────────────────────────────────────────────────────────────────

def save_image(image_bytes: bytes, page_number: int, run_ts: str) -> Path:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = IMAGE_DIR / f"pin-page-{page_number:02d}-{run_ts}.jpg"
    path.write_bytes(image_bytes)
    return path


# ── Cloudinary upload ─────────────────────────────────────────────────────────

def upload_to_cloudinary(local_path: Path) -> str | None:
    if not (CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY_CLD and CLOUDINARY_API_SECRET):
        print("  Cloudinary credentials missing — skipping upload.")
        return None
    ts     = int(time.time())
    folder = "switzertemplates/pins"
    params = f"folder={folder}&timestamp={ts}"
    sig    = hashlib.sha1((params + CLOUDINARY_API_SECRET).encode()).hexdigest()
    try:
        with open(local_path, "rb") as f:
            r = requests.post(
                f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload",
                data={
                    "api_key":   CLOUDINARY_API_KEY_CLD,
                    "timestamp": ts,
                    "folder":    folder,
                    "signature": sig,
                },
                files={"file": (local_path.name, f, "image/jpeg")},
                timeout=60,
            )
        if r.ok:
            return r.json().get("secure_url")
        print(f"  Cloudinary error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  Cloudinary upload failed: {e}")
    return None


# ── per-page pipeline ─────────────────────────────────────────────────────────

def generate_pin_image(
    page_number: int,
    run_ts: str,
    used_combinations: dict | None = None,
) -> tuple[dict, dict]:
    """
    Full pipeline for one pin page:
      1. Resolve keyword from topics JSON
      2. Generate image prompt via Claude (prompt type rotates per page, variety enforced)
      3. Generate 9:16 image via Gemini Imagen
      4. Save locally
      5. Upload to Cloudinary
    Returns (result_dict, updated_used_combinations).
    result_dict has upload_url=None if any step failed.
    """
    uc = {
        "compositions_used": list(used_combinations.get("compositions_used", [])),
        "settings_used":     list(used_combinations.get("settings_used",     [])),
        "outfits_used":      list(used_combinations.get("outfits_used",      [])),
        "drinks_used":       list(used_combinations.get("drinks_used",       [])),
        "props_used":        list(used_combinations.get("props_used",        [])),
        "actions_used":      list(used_combinations.get("actions_used",      [])),
    } if used_combinations else {
        "compositions_used": [],
        "settings_used":     [],
        "outfits_used":      [],
        "drinks_used":       [],
        "props_used":        [],
        "actions_used":      [],
    }

    keyword    = keyword_for_page(page_number)
    ptype      = prompt_type_for_page(page_number)
    ptype_name = PROMPT_TYPE_NAMES[ptype]

    print(f"\n[Page {page_number}] keyword='{keyword}'  type={ptype} ({ptype_name})")
    print(f"  Used so far — compositions:{uc['compositions_used']}  settings:{uc['settings_used']}")

    print("  Generating image prompt via Claude...")
    try:
        img_prompt, choices = generate_image_prompt(keyword, ptype, uc)
    except Exception as e:
        print(f"  Claude prompt generation failed: {e}")
        return _failed(page_number, keyword, ptype, ptype_name, ""), uc

    print(f"  Choices: {choices}")
    print(f"  Prompt ({len(img_prompt)} chars): {img_prompt[:100]}...")

    # Update variety tracking from Claude's declared choices
    if choices.get("composition"):
        uc["compositions_used"].append(choices["composition"])
    if choices.get("setting"):
        uc["settings_used"].append(choices["setting"])
    if choices.get("outfit") and choices["outfit"].lower() not in ("none", "n/a", ""):
        uc["outfits_used"].append(choices["outfit"])
    if choices.get("drink") and choices["drink"].lower() not in ("none", "n/a", ""):
        uc["drinks_used"].append(choices["drink"])
    if choices.get("props"):
        for prop in choices["props"].split(","):
            prop = prop.strip()
            if prop:
                uc["props_used"].append(prop)
    if choices.get("action") and choices["action"].lower() not in ("none", "n/a", ""):
        uc["actions_used"].append(choices["action"])

    print("  Generating image via Gemini Imagen (9:16)...")
    img_bytes = generate_image_bytes(img_prompt)
    if not img_bytes:
        print("  FAILED: no image bytes returned.")
        return _failed(page_number, keyword, ptype, ptype_name, img_prompt), uc

    local_path = save_image(img_bytes, page_number, run_ts)
    print(f"  Saved: {local_path.name}  ({len(img_bytes):,} bytes)")

    print("  Uploading to Cloudinary...")
    upload_url = upload_to_cloudinary(local_path)
    if upload_url:
        print(f"  URL: {upload_url}")
    else:
        print("  Upload failed — Canva insertion will need to be skipped for this page.")

    result = {
        "page_number":      page_number,
        "keyword":          keyword,
        "prompt_type":      ptype,
        "prompt_type_name": ptype_name,
        "image_prompt":     img_prompt,
        "choices":          choices,
        "local_path":       str(local_path),
        "upload_url":       upload_url,
        "success":          upload_url is not None,
    }
    return result, uc


def _failed(page_number, keyword, ptype, ptype_name, img_prompt) -> dict:
    return {
        "page_number":      page_number,
        "keyword":          keyword,
        "prompt_type":      ptype,
        "prompt_type_name": ptype_name,
        "image_prompt":     img_prompt,
        "choices":          {},
        "local_path":       None,
        "upload_url":       None,
        "success":          False,
    }


# ── batch ──────────────────────────────────────────────────────────────────────

def generate_pin_images(page_numbers: list[int]) -> list[dict]:
    """Generate images for a list of page numbers with variety enforced across the batch."""
    run_ts           = datetime.now().strftime("%Y%m%d-%H%M%S")
    used_combinations = {
        "compositions_used": [],
        "settings_used":     [],
        "outfits_used":      [],
        "drinks_used":       [],
        "props_used":        [],
        "actions_used":      [],
    }
    results = []
    for pn in page_numbers:
        result, used_combinations = generate_pin_image(pn, run_ts, used_combinations)
        results.append(result)
    return results


# ── CLI entry ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Pinterest pin images via Gemini Imagen")
    parser.add_argument(
        "--pages",
        default="1-5",
        help="Page range (e.g. 1-5) or comma-separated list (e.g. 1,3,5)",
    )
    args = parser.parse_args()

    if "-" in args.pages and "," not in args.pages:
        start, end = args.pages.split("-")
        pages = list(range(int(start), int(end) + 1))
    else:
        pages = [int(p.strip()) for p in args.pages.split(",")]

    print(f"Generating images for pages: {pages}")
    results = generate_pin_images(pages)

    print("\n=== Results ===")
    for r in results:
        status = "OK " if r["success"] else "FAIL"
        url    = r.get("upload_url") or "—"
        print(f"  [{status}] Page {r['page_number']} ({r['keyword']})  type={r['prompt_type']}  {url}")

    out_path = PROJECT_ROOT / "outputs" / "pins" / "image_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to: {out_path}")
