"""
Pin Pipeline — General Manager

Connects a single blog-post keyword to the existing Pinterest pin generation pipeline:
builds pin copy for that one keyword (reusing pinterest-agent's own scoring + copy_writer),
writes it as a topics JSON, then invokes creative-designer to generate images and submit
Tailwind drafts.

Runs creative-designer via subprocess, deliberately not an in-process import:
skills/creative-designer/copy_writer.py and skills/pinterest-agent/copy_writer.py are two
different files with the identical bare module name `copy_writer`, and both directories
rely on sys.path.insert() + bare imports. If both trees ended up on sys.path in the same
long-lived process (which building the topics JSON below requires), an in-process import
of creative-designer's main() could silently resolve `import copy_writer` to the wrong
module. Subprocess isolation sidesteps this entirely — each process gets a fresh sys.path.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINTEREST_AGENT_DIR = ROOT / "skills" / "pinterest-agent"
CREATIVE_DESIGNER_MAIN = ROOT / "skills" / "creative-designer" / "main.py"
TOPICS_DIR = ROOT / "data" / "pinterest-agent"


def generate_pins_for_keyword(keyword: str, volume: int = 0, slug: str = "") -> dict:
    """
    Build pin copy for one keyword and hand it to creative-designer for image
    generation + Tailwind draft submission. Returns a small result dict for the
    caller's per-post reporting.
    """
    sys.path.insert(0, str(PINTEREST_AGENT_DIR))
    from topic_selector import _score_product_match

    product_match, maps_to_product = _score_product_match(keyword)

    ranked = [{
        "keyword": keyword,
        "volume": volume,
        "product_match": product_match,
        "maps_to_product": maps_to_product,
    }]

    import copy_writer  # skills/pinterest-agent/copy_writer.py
    topics = copy_writer.generate(ranked, analytics_context="", top_n=1, batch_size=1)

    if not topics:
        return {"success": False, "message": "No pin copy generated (empty result from copy_writer)"}

    TOPICS_DIR.mkdir(parents=True, exist_ok=True)
    topics_path = TOPICS_DIR / f"gm-topics-{slug or keyword}.json"
    topics_path.write_text(json.dumps({"topics": topics}, indent=2, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(CREATIVE_DESIGNER_MAIN),
            "--from-topics-json", str(topics_path),
            "--auto-approve",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )

    pins_count = sum(len(t.get("variations", [])) for t in topics)

    if result.returncode != 0:
        return {
            "success": False,
            "message": f"creative-designer exited {result.returncode}: {result.stderr[-500:]}",
            "pins_attempted": pins_count,
        }

    return {
        "success": True,
        "message": f"{pins_count} pin(s) generated and submitted to Tailwind as drafts",
        "pins_attempted": pins_count,
        "topics_json": str(topics_path),
    }
