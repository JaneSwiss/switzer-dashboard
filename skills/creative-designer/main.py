#!/usr/bin/env python3
from __future__ import annotations
"""
Creative Designer - Pinterest Pin Generator for Switzertemplates

Full pipeline:
  1. Receive topics (CLI, file, or interactive)
  2. Generate SEO copy for each topic via Claude
  3. Generate pin image for each topic via Gemini Imagen + Pillow compositing
  4. Save all pins to outputs/pins/review/<session>/
  5. Open HTML preview in browser for visual review
  6. Interactive approval (enter pin numbers to approve)
  7. Copy approved pins to outputs/pins/approved/<session>/
  8. Submit to Tailwind API (or write queue file if image hosting needed)

Usage:
  python3 main.py                                  # interactive topic entry
  python3 main.py --topics "topic1" "topic2" ...   # inline topics
  python3 main.py --topics-file topics.txt         # one topic per line
  python3 main.py --skip-images                    # skip Gemini (placeholder bg)
  python3 main.py --skip-tailwind                  # skip Tailwind submission
"""

import os
import sys
import json
import shutil
import socket
import threading
import argparse
import webbrowser
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add skill dir to path for sibling imports
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# ── Path constants ────────────────────────────────────────────────────────

SKILL_DIR = Path(__file__).parent
PROJECT_ROOT = SKILL_DIR.parent.parent
CONTEXT_DIR = PROJECT_ROOT / "context"
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "pins"


# ── Context loading ───────────────────────────────────────────────────────

def load_context() -> dict:
    files = {
        "visual_style":    "visual-style-guide.md",
        "brand_voice":     "brand-voice.md",
        "product_catalog": "product-catalog.md",
        "target_audience": "target-audience.md",
    }
    context = {}
    for key, filename in files.items():
        p = CONTEXT_DIR / filename
        context[key] = p.read_text() if p.exists() else ""
    return context


# ── Topic input ───────────────────────────────────────────────────────────

def get_topics(args) -> list[str]:
    if args.topics:
        # Support both multiple args and a single comma-separated string
        joined = " ".join(args.topics)
        if "," in joined:
            return [t.strip() for t in joined.split(",") if t.strip()]
        return [t.strip() for t in args.topics if t.strip()]

    if args.topics_file:
        p = Path(args.topics_file)
        if not p.exists():
            print(f"Error: topics file not found: {p}")
            sys.exit(1)
        lines = p.read_text().strip().splitlines()
        return [l.strip() for l in lines if l.strip() and not l.startswith("#")]

    print("\nEnter one topic per line. Press Enter twice when done:\n")
    topics = []
    while True:
        line = input("  Topic: ").strip()
        if not line:
            if topics:
                break
        else:
            topics.append(line)
    return topics


# ── Output helpers ────────────────────────────────────────────────────────

def create_session_dir() -> tuple[Path, str]:
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    d = OUTPUTS_DIR / "review" / ts
    d.mkdir(parents=True, exist_ok=True)
    return d, ts


def save_pin(session_dir: Path, index: int, copy_data: dict, image_path: Path) -> tuple[Path, Path]:
    slug = copy_data.get("topic", "pin").lower()
    slug = "".join(c if c.isalnum() or c == "-" else "-" for c in slug.replace(" ", "-"))[:40]
    slug = slug.strip("-")
    pin_dir = session_dir / f"{index:02d}_{slug}"
    pin_dir.mkdir(exist_ok=True)

    dest = pin_dir / "pin.png"
    shutil.copy2(image_path, dest)
    (pin_dir / "meta.json").write_text(
        json.dumps(copy_data, indent=2, ensure_ascii=False)
    )
    return pin_dir, dest


# ── Browser-based review server ───────────────────────────────────────────

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _build_review_html(pins: list[tuple], generated: str) -> str:
    cards = ""
    for i, (pin_dir, copy_data, _) in enumerate(pins, 1):
        folder = pin_dir.name
        topic   = copy_data.get("topic", "")
        headline = copy_data.get("pin_headline", "")
        label   = copy_data.get("category_label", "")
        title   = copy_data.get("seo_title", "")
        desc    = copy_data.get("seo_description", "")

        maps_to = copy_data.get("maps_to_product", "")
        dest    = copy_data.get("destination_url", "")
        pin_type = copy_data.get("type", "")

        cards += f"""
      <div class="card" id="card-{i}">
        <div class="num">{i}</div>
        <img src="/{folder}/pin.png" alt="Pin {i}" loading="lazy" />
        <div class="meta">
          <div class="topic">{topic}</div>
          <div class="label-tag">{label}</div>
          <div class="headline">{headline}</div>
          <div class="field"><strong>SEO title:</strong> {title}</div>
          <div class="field desc">{desc}</div>
          {f'<div class="field"><strong>Product:</strong> {maps_to} &nbsp;|&nbsp; {pin_type}</div>' if maps_to else ''}
          {f'<div class="field url">{dest}</div>' if dest else ''}
        </div>
        <button class="btn" onclick="toggle({i})">Approve</button>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Pin Review - Switzertemplates</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:Georgia,serif;background:#f8f5f2;color:#383838;padding:32px 24px}}
  h1{{font-size:22px;color:#8d6e63;margin-bottom:4px}}
  .sub{{color:#a5988e;font-style:italic;font-size:14px;margin-bottom:24px}}
  .grid{{display:flex;flex-wrap:wrap;gap:24px}}
  .card{{background:#fff;border-radius:10px;width:260px;overflow:hidden;
         box-shadow:0 2px 10px rgba(0,0,0,.07);position:relative;
         border:2px solid transparent;transition:border .15s}}
  .card.approved{{border-color:#8d6e63}}
  .num{{position:absolute;top:10px;left:10px;background:#8d6e63;color:#fff;
        width:28px;height:28px;border-radius:50%;display:flex;align-items:center;
        justify-content:center;font-size:13px;font-family:Arial,sans-serif;font-weight:bold}}
  img{{width:100%;display:block}}
  .meta{{padding:12px;font-size:12px;font-family:Arial,sans-serif}}
  .topic{{font-size:10px;text-transform:uppercase;letter-spacing:1px;
          color:#8d6e63;font-weight:bold;margin-bottom:5px}}
  .label-tag{{font-size:10px;text-transform:uppercase;letter-spacing:1.5px;
              color:#bbb0aa;margin-bottom:6px}}
  .headline{{font-size:14px;font-style:italic;color:#383838;margin-bottom:8px;line-height:1.4}}
  .field{{font-size:11px;color:#666;margin-bottom:4px;line-height:1.4}}
  .field.url{{font-size:10px;color:#bbb0aa;word-break:break-all}}
  .btn{{display:block;width:100%;padding:10px;border:none;background:#f8f5f2;
        color:#383838;font-family:Arial,sans-serif;font-size:13px;cursor:pointer;
        border-top:1px solid #ede5de;transition:background .15s}}
  .btn:hover{{background:#e8ddd5}}
  .card.approved .btn{{background:#8d6e63;color:#fff}}
  .submit-bar{{margin-top:36px;display:flex;align-items:center;gap:20px}}
  #submit-btn{{padding:14px 36px;background:#8d6e63;color:#fff;border:none;
               border-radius:6px;font-family:Arial,sans-serif;font-size:15px;
               cursor:pointer;transition:background .15s}}
  #submit-btn:hover{{background:#7a5e55}}
  #submit-btn:disabled{{background:#bbb0aa;cursor:default}}
  #status{{font-family:Arial,sans-serif;font-size:14px;color:#555}}
  #status.done{{color:#8d6e63;font-weight:bold}}
</style>
</head>
<body>
<h1>Pin Review</h1>
<p class="sub">Generated {generated} &nbsp;|&nbsp; {len(pins)} pins — click to approve, then submit</p>
<div class="grid">{cards}
</div>
<div class="submit-bar">
  <button id="submit-btn" onclick="submitApprovals()">Submit Approvals</button>
  <div id="status"></div>
</div>
<script>
function toggle(n) {{
  const c = document.getElementById('card-' + n);
  const on = c.classList.toggle('approved');
  c.querySelector('.btn').textContent = on ? 'Approved ✓' : 'Approve';
}}
function submitApprovals() {{
  const approved = [];
  document.querySelectorAll('.card.approved').forEach(c => {{
    approved.push(parseInt(c.id.replace('card-', '')));
  }});
  document.getElementById('submit-btn').disabled = true;
  document.getElementById('status').textContent = 'Submitting…';
  fetch('/submit', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{approved: approved}})
  }}).then(r => r.json()).then(d => {{
    const el = document.getElementById('status');
    el.textContent = approved.length + ' pin(s) approved. You can close this tab.';
    el.className = 'done';
  }}).catch(e => {{
    document.getElementById('status').textContent = 'Error: ' + e.message;
    document.getElementById('submit-btn').disabled = false;
  }});
}}
</script>
</body>
</html>"""


def _start_review_server(session_dir: Path, html: str):
    """Start a local HTTP server that serves the review page and receives approvals."""
    port = _free_port()
    approved_indices: list[int] = []
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass  # silence access log

        def do_GET(self):
            if self.path == "/":
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.endswith(".png"):
                img_path = session_dir / self.path.lstrip("/")
                if img_path.exists():
                    data = img_path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_response(404)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/submit":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                data = json.loads(body)
                approved_indices.extend(data.get("approved", []))
                resp = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
                self.wfile.flush()   # ensure response is fully sent before signalling
                done.set()           # signal main thread only after response is on the wire

    httpd = HTTPServer(("localhost", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return port, httpd, done, approved_indices


def browser_approval(session_dir: Path, pins: list[tuple]) -> list[tuple[int, tuple]]:
    """Open a local review page, wait for the user to submit approvals, return approved list."""
    generated = datetime.now().strftime("%d %b %Y, %H:%M")
    html = _build_review_html(pins, generated)
    port, httpd, done, approved_indices = _start_review_server(session_dir, html)

    url = f"http://localhost:{port}/"
    print(f"\nReview page: {url}")
    webbrowser.open(url)
    print("Waiting for you to approve pins and click Submit in the browser...")

    done.wait()   # no timeout — server stays open until Submit is clicked
    httpd.shutdown()

    return [(i, pins[i - 1]) for i in sorted(set(approved_indices)) if 1 <= i <= len(pins)]


# ── Approved output ───────────────────────────────────────────────────────

def save_approved(approved: list[tuple[int, tuple]], timestamp: str) -> tuple[Path, list[dict]]:
    approved_dir = OUTPUTS_DIR / "approved" / timestamp
    approved_dir.mkdir(parents=True, exist_ok=True)

    approved_pins = []
    for idx, (pin_dir, copy_data, image_path) in approved:
        dest_dir = approved_dir / pin_dir.name
        shutil.copytree(pin_dir, dest_dir, dirs_exist_ok=True)
        approved_pins.append({
            "index": idx,
            "folder": pin_dir.name,
            "image_path": str(dest_dir / "pin.png"),
            **copy_data,
        })
    return approved_dir, approved_pins


# ── Placeholder background (no Gemini) ───────────────────────────────────

def _make_placeholder(copy_data: dict, tmp_dir: Path, fonts: dict) -> Path:
    from PIL import Image, ImageDraw
    from font_manager import load_font

    img = Image.new("RGB", (1000, 1500))
    draw = ImageDraw.Draw(img)
    for y in range(1500):
        t = y / 1500
        r = int(80 + (120 - 80) * t)
        g = int(60 + (90 - 60) * t)
        b = int(50 + (75 - 50) * t)
        draw.line([(0, y), (1000, y)], fill=(r, g, b))

    font = load_font(fonts.get("serif"), 52)
    draw.text((70, 600), copy_data.get("pin_headline", ""), font=font, fill=(255, 255, 255))

    slug = copy_data.get("topic", "pin")[:20].replace(" ", "-")
    path = tmp_dir / f"placeholder_{slug}.png"
    img.save(path, "PNG")
    return path


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    load_dotenv(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Generate Pinterest pins for Switzertemplates and submit to Tailwind"
    )
    parser.add_argument("--topics", nargs="+", help="Topics/keywords to generate pins for")
    parser.add_argument("--topics-file", help="Text file with one topic per line")
    parser.add_argument(
        "--from-topics-json",
        help="Load pre-written pin copy from a Pinterest agent topics JSON. "
             "Skips topic input and Claude copy generation — goes straight to "
             "image generation, browser review, and Tailwind."
    )
    parser.add_argument(
        "--review-session",
        help="Load a completed session directory (outputs/pins/review/TIMESTAMP) "
             "and go straight to browser review. Use when image generation finished "
             "but the process hung before the browser opened."
    )
    parser.add_argument(
        "--list-boards", action="store_true",
        help="List all Pinterest boards in your Tailwind account and exit"
    )
    parser.add_argument(
        "--topic-range",
        help="Process only a range of topic IDs from the topics JSON (e.g. 1-7). "
             "Only applies with --from-topics-json."
    )
    parser.add_argument(
        "--skip-copy", action="store_true",
        help="Skip Claude copy generation (use placeholder copy - for pipeline testing)"
    )
    parser.add_argument(
        "--skip-images", action="store_true",
        help="Skip Gemini image generation (use placeholder backgrounds)"
    )
    parser.add_argument(
        "--skip-tailwind", action="store_true",
        help="Skip Tailwind submission (write queue file only)"
    )
    args = parser.parse_args()

    print("\nSwitzertemplates - Creative Designer")
    print("=" * 60)

    # ── Resume from existing session ─────────────────────────────────────────
    if args.review_session:
        session_dir = Path(args.review_session)
        if not session_dir.exists():
            # Try relative to outputs/pins/review/
            session_dir = OUTPUTS_DIR / "review" / args.review_session
        if not session_dir.exists():
            print(f"Error: session directory not found: {args.review_session}")
            sys.exit(1)
        timestamp = session_dir.name
        print(f"\nResuming session: {session_dir}")

        # Reconstruct pins list from saved pin directories + meta.json
        pin_dirs = sorted(
            [d for d in session_dir.iterdir() if d.is_dir() and not d.name.startswith("_")],
            key=lambda d: int(d.name.split("_")[0])
        )
        pins = []
        for pin_dir in pin_dirs:
            meta_path  = pin_dir / "meta.json"
            image_path = pin_dir / "pin.png"
            if meta_path.exists() and image_path.exists():
                copy_data = json.loads(meta_path.read_text())
                pins.append((pin_dir, copy_data, image_path))
        print(f"  {len(pins)} pins loaded from session.")

        # Go straight to browser review
        approved = browser_approval(session_dir, pins)
        if not approved:
            print("\nNo pins approved. Review complete.")
            print(f"All pins saved to: {session_dir}")
            return

        print(f"\n{len(approved)} pin(s) approved.")
        approved_dir, approved_pins = save_approved(approved, timestamp)

        from cloudinary_uploader import upload_approved_pins
        print(f"\n[Uploading {len(approved_pins)} pin(s) to Cloudinary...]")
        try:
            approved_pins = upload_approved_pins(approved_pins)
        except RuntimeError as e:
            print(f"  {e}")
            approved_pins_with_urls = False
        else:
            approved_pins_with_urls = any(p.get("image_url") for p in approved_pins)

        from tailwind_client import submit_to_tailwind, build_queue_entry, generate_csv
        if args.skip_tailwind:
            print("\nSkipping Tailwind (--skip-tailwind).")
            results = [{"index": p["index"], "success": False, "message": "skipped"} for p in approved_pins]
        elif not approved_pins_with_urls:
            print("\nSkipping Tailwind — no image URLs available.")
            results = [{"index": p["index"], "success": False, "message": "no image URL"} for p in approved_pins]
        else:
            print(f"\nSubmitting {len(approved_pins)} pin(s) to Tailwind...")
            results = submit_to_tailwind(approved_pins)

        for r in results:
            icon = "✓" if r.get("success") else "-"
            print(f"  {icon} Pin {r['index']}: {r.get('message', '')}")

        queue = [build_queue_entry(p) for p in approved_pins]
        queue_path = approved_dir / "tailwind_queue.json"
        queue_path.write_text(json.dumps(queue, indent=2, ensure_ascii=False))
        csv_path = approved_dir / "tailwind_pins.csv"
        generate_csv(approved_pins, csv_path)

        print(f"\nDone.")
        print(f"  Approved pins:  {approved_dir}")
        print(f"  Queue JSON:     {queue_path}")
        print(f"  Tailwind CSV:   {csv_path}")
        return

    if args.list_boards:
        from tailwind_client import list_boards
        print("Fetching boards from Tailwind...\n")
        try:
            boards = list_boards()
            print(f"{'ID':<30} {'Name'}")
            print("-" * 60)
            for b in boards:
                print(f"{str(b.get('id','')):<30} {b.get('name','')}")
            print(f"\nSet TAILWIND_BOARD_ID or TAILWIND_BOARD_NAME in .env to target a board.")
        except Exception as e:
            print(f"Error: {e}")
        return

    # Load brand context
    print("Loading brand context...")
    context = load_context()

    # ── Pinterest agent topics JSON mode ──────────────────────────────────────
    # When --from-topics-json is provided, copy is already written by the
    # Pinterest agent. Skip topic input and Claude copy generation entirely.
    # Map the Pinterest agent's fields to what the creative designer expects.
    preloaded_copy = None
    if args.from_topics_json:
        topics_path = Path(args.from_topics_json)
        if not topics_path.exists():
            print(f"Error: topics JSON not found: {topics_path}")
            sys.exit(1)
        data = json.loads(topics_path.read_text())

        # Apply --topic-range filter if provided
        all_topics = data.get("topics", [])
        if args.topic_range:
            parts = args.topic_range.split("-")
            if len(parts) == 2 and all(p.strip().isdigit() for p in parts):
                range_start, range_end = int(parts[0]), int(parts[1])
                all_topics = [t for t in all_topics
                              if range_start <= t.get("topic_id", 0) <= range_end]
                print(f"  Topic range {args.topic_range}: {len(all_topics)} topic(s) selected.")
            else:
                print(f"Warning: invalid --topic-range '{args.topic_range}' — expected format 1-7. Processing all topics.")

        preloaded_copy = []
        for topic in all_topics:
            keyword = topic.get("keyword", "")
            maps_to = topic.get("maps_to_product", "")
            for v in topic.get("variations", []):
                preloaded_copy.append({
                    "topic":           f"{keyword} ({v['id']})",
                    "keyword":         keyword,
                    "topic_id":        topic.get("topic_id", 1),
                    "variation_id":    v.get("id", ""),
                    "type":            v.get("type", ""),
                    "maps_to_product": maps_to,
                    "category_label":  v.get("category_label", "SMALL BIZ"),
                    "pin_headline":    v.get("pin_headline", ""),
                    "highlight_words": v.get("highlight_words", []),
                    "seo_title":       v.get("seo_title", v.get("pin_headline", "")),
                    "seo_description": v.get("seo_description", ""),
                    "photo_concept":   v.get("design_brief", ""),
                    "destination_url": v.get("destination_url", ""),
                })
        topics = [c["topic"] for c in preloaded_copy]
        print(f"\nLoaded {len(topics)} pin variations from {topics_path.name}")
    else:
        # Get topics via CLI / file / interactive input
        topics = get_topics(args)
        if not topics:
            print("No topics provided. Exiting.")
            sys.exit(1)

    print(f"\n{len(topics)} topic(s) queued:")
    for i, t in enumerate(topics, 1):
        print(f"  {i}. {t}")

    # Create session directory
    session_dir, timestamp = create_session_dir()
    print(f"\nSession: {session_dir}")

    # Step 1: Generate copy (Claude) — skipped when topics JSON is provided
    from copy_writer import generate_copy_batch
    if preloaded_copy is not None:
        copy_list = preloaded_copy
        print(f"\n[1/3] Copy loaded from topics JSON — skipping Claude generation.")
    elif args.skip_copy:
        print(f"\n[1/3] Using placeholder copy (--skip-copy).")
        copy_list = generate_copy_batch(topics, context, placeholder=True)
    else:
        print(f"\n[1/3] Generating copy for {len(topics)} pin(s) via Claude...")
        copy_list = generate_copy_batch(topics, context, placeholder=False)
    print(f"  Copy ready for {len(copy_list)} pin(s).")

    # Step 2: Generate images
    print(f"\n[2/3] Generating pin images...")
    from font_manager import setup_fonts
    print("  Setting up fonts...")
    fonts = setup_fonts()

    if not args.skip_images:
        from image_generator import generate_pin_image

    pins = []
    tmp_dir = session_dir / "_tmp"
    tmp_dir.mkdir(exist_ok=True)

    for i, copy_data in enumerate(copy_list, 1):
        topic = copy_data.get("topic", topics[i - 1] if i <= len(topics) else "?")
        print(f"  [{i}/{len(copy_list)}] {topic}")

        try:
            if args.skip_images:
                image_path = _make_placeholder(copy_data, tmp_dir, fonts)
            else:
                image_path = generate_pin_image(copy_data, context, fonts)
        except Exception as e:
            print(f"    Error generating image: {e}")
            image_path = _make_placeholder(copy_data, tmp_dir, fonts)

        pin_dir, saved_image = save_pin(session_dir, i, copy_data, image_path)
        pins.append((pin_dir, copy_data, saved_image))
        print(f"    Saved: {pin_dir.name}")

    # Clean up temp dir
    shutil.rmtree(tmp_dir, ignore_errors=True)

    # Step 3: Browser review + approval
    approved = browser_approval(session_dir, pins)

    if not approved:
        print("\nNo pins approved. Review complete.")
        print(f"All pins saved to: {session_dir}")
        return

    print(f"\n{len(approved)} pin(s) approved.")

    # Save approved pins to their output directory
    approved_dir, approved_pins = save_approved(approved, timestamp)

    # Upload to Cloudinary → get public URLs for Tailwind
    from cloudinary_uploader import upload_approved_pins
    print(f"\n[3a/3] Uploading {len(approved_pins)} pin(s) to Cloudinary...")
    try:
        approved_pins = upload_approved_pins(approved_pins)
    except RuntimeError as e:
        print(f"  {e}")
        print("  Skipping Tailwind — add Cloudinary credentials to .env and re-run.")
        approved_pins_with_urls = False
    else:
        approved_pins_with_urls = any(p.get("image_url") for p in approved_pins)

    # Submit to Tailwind
    from tailwind_client import submit_to_tailwind, build_queue_entry

    if args.skip_tailwind:
        print("\n[3b/3] Skipping Tailwind submission (--skip-tailwind).")
        results = [{"index": p["index"], "success": False, "message": "skipped", "mode": "queue"}
                   for p in approved_pins]
    elif not approved_pins_with_urls:
        print("\n[3b/3] Skipping Tailwind — no image URLs available.")
        results = [{"index": p["index"], "success": False, "message": "no image URL", "mode": "queue"}
                   for p in approved_pins]
    else:
        print(f"\n[3b/3] Submitting {len(approved_pins)} pin(s) to Tailwind...")
        results = submit_to_tailwind(approved_pins)

    for r in results:
        icon = "✓" if r.get("success") else "-"
        print(f"  {icon} Pin {r['index']}: {r.get('message', '')}")

    # Queue file — full metadata including Cloudinary URLs
    queue = [build_queue_entry(p) for p in approved_pins]
    queue_path = approved_dir / "tailwind_queue.json"
    queue_path.write_text(json.dumps(queue, indent=2, ensure_ascii=False))

    # Tailwind CSV — drag straight into Tailwind's bulk scheduler
    from tailwind_client import generate_csv
    csv_path = approved_dir / "tailwind_pins.csv"
    generate_csv(approved_pins, csv_path)

    print(f"\nDone.")
    print(f"  Approved pins:  {approved_dir}")
    print(f"  Tailwind CSV:   {csv_path}")
    print(f"  Queue JSON:     {queue_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
