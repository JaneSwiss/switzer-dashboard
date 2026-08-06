"""
Pinterest Pins — Generator

Orchestrator, mirrors blog_seo_agent.run(): write copy, validate, generate
images, save, upload, submit to Tailwind. One call per already-written post.

Run:
    python3 agents/blog-seo-agent/pinterest-pins/pin_generator.py <slug> "<keyword>"
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "skills" / "creative-designer"))

load_dotenv(ROOT / ".env")

from pin_writer import write_pins
from pin_image_prompt import build_pin_prompt
from openai_images import generate_image_bytes
from cloudinary_uploader import upload_pin
from tailwind_client import submit_to_tailwind

OUTPUT_DIR = ROOT / "outputs" / "pinterest-pins"
MAX_ATTEMPTS = 3


def _pin_type_and_offsets(variation_id: str, keyword: str) -> tuple:
    var_offset = ord(variation_id[-1].lower()) - ord("a")
    topic_base = sum(ord(c) for c in keyword)
    offset = topic_base + var_offset
    pin_type = "photo" if (var_offset % 5) in (3, 4) else "infographic"
    return pin_type, offset


def _generate_one_image(pin_data: dict) -> Path:
    prompt = build_pin_prompt(pin_data)
    last_err = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            image_bytes, cost = generate_image_bytes(prompt, aspect_ratio="9:16", quality="high")
            print(f"    (est. ${cost:.2f})")
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            tmp = Path(tempfile.mktemp(suffix=".png"))
            img.save(tmp, "PNG", optimize=False)
            return tmp
        except Exception as e:
            last_err = e
            print(f"    Attempt {attempt + 1} failed: {e}")
    raise RuntimeError(f"All {MAX_ATTEMPTS} attempts failed: {last_err}")


def generate_pins_for_post(slug: str, keyword: str, submit: bool = True) -> dict:
    print(f"[1/3] Writing pin copy for '{keyword}' (grounded in posts/{slug}.html)...")
    variations = write_pins(slug, keyword)
    print(f"  {len(variations)} variation(s) written and validated.")

    post_dir = OUTPUT_DIR / slug
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "copy.json").write_text(json.dumps(variations, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n[2/3] Generating images...")
    approved_pins = []
    for v in variations:
        pin_type, offset = _pin_type_and_offsets(v["id"], keyword)
        pin_data = {
            "image_headline": v["image_headline"],
            "image_eyebrow": v.get("image_eyebrow", ""),
            "pin_items": v.get("pin_items", []),
            "pin_type": pin_type,
            "reference_offset": offset,
            "palette_offset": offset,
        }
        print(f"  Pin {v['id']} ({pin_type})...")
        try:
            tmp_path = _generate_one_image(pin_data)
            final_path = post_dir / f"{v['id']}.png"
            tmp_path.replace(final_path)
            approved_pins.append({
                "index": v["id"],
                "topic": f"{keyword} ({v['id']})",
                "image_path": str(final_path),
                "folder": f"{slug}-{v['id']}",
                "tailwind_title": v["seo_title"],
                "tailwind_description": v["seo_description"],
                "link": v["destination_url"],
            })
        except Exception as e:
            print(f"  Pin {v['id']} image generation failed: {e}")

    result = {"slug": slug, "keyword": keyword, "pins_written": len(variations),
              "images_generated": len(approved_pins), "tailwind": []}

    if not submit or not approved_pins:
        return result

    print("\n[3/3] Uploading + submitting to Tailwind...")
    for pin in approved_pins:
        try:
            pin["image_url"] = upload_pin(Path(pin["image_path"]), pin["folder"])
            print(f"  Uploaded {pin['index']}: {pin['image_url']}")
        except Exception as e:
            print(f"  Upload failed for {pin['index']}: {e}")
            pin["image_url"] = ""

    tailwind_results = submit_to_tailwind(approved_pins)
    result["tailwind"] = tailwind_results

    queue_path = post_dir / "tailwind_queue.json"
    queue_path.write_text(json.dumps(approved_pins, indent=2, ensure_ascii=False), encoding="utf-8")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 pin_generator.py <slug> \"<keyword>\"")
        sys.exit(1)
    result = generate_pins_for_post(sys.argv[1], sys.argv[2])
    print("\n" + json.dumps(result, indent=2))
