"""
Pin Pipeline — General Manager

Connects a single blog-post keyword to Pinterest pin generation. Rebuilt
August 2026 to call agents/blog-seo-agent/pinterest-pins/ — a clean, dedicated
build mirroring blog_seo_agent's proven pattern (grounded in the real post,
hardcoded rules, one Claude call, then image generation) — instead of
skills/pinterest-agent/copy_writer.py, which stayed on the old architecture.

Runs pin_generator via subprocess, same isolation reasoning as before: keeps
this process's sys.path clean regardless of what else GM has imported.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIN_GENERATOR = ROOT / "agents" / "blog-seo-agent" / "pinterest-pins" / "pin_generator.py"


def generate_pins_for_keyword(keyword: str, volume: int = 0, slug: str = "") -> dict:
    """
    Write pin copy (grounded in the real post at posts/{slug}.html) and generate +
    submit images to Tailwind. Returns a small result dict for the caller's per-post
    reporting. `volume` kept in the signature for call-site compatibility — no longer
    used (product-match scoring lived in the old pinterest-agent path).
    """
    if not slug:
        return {"success": False, "message": "generate_pins_for_keyword requires a slug (post must already be written)"}

    result = subprocess.run(
        [sys.executable, str(PIN_GENERATOR), slug, keyword],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )

    if result.returncode != 0:
        return {
            "success": False,
            "message": f"pin_generator exited {result.returncode}: {result.stderr[-500:]}",
        }

    # pin_generator prints its result dict as the last line of stdout.
    try:
        last_line = [l for l in result.stdout.strip().splitlines() if l.strip()][-1]
        summary = json.loads(result.stdout[result.stdout.index("{\n"):]) if "{\n" in result.stdout else json.loads(last_line)
    except Exception:
        summary = {}

    tailwind_ok = sum(1 for t in summary.get("tailwind", []) if t.get("success"))
    return {
        "success": summary.get("images_generated", 0) > 0,
        "message": f"{summary.get('pins_written', 0)} pin(s) written, "
                   f"{summary.get('images_generated', 0)} image(s) generated, "
                   f"{tailwind_ok} submitted to Tailwind",
        "pins_attempted": summary.get("pins_written", 0),
        "images_generated": summary.get("images_generated", 0),
    }
