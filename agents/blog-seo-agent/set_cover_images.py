#!/usr/bin/env python3
"""Set cover images on all Wix draft posts that have cover-1.jpg on GitHub Pages."""
import os, sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from publish_to_wix import set_cover_image, WIX_API_KEY, WIX_SITE_ID, WIX_MEMBER_ID

if not (WIX_API_KEY and WIX_SITE_ID and WIX_MEMBER_ID):
    print("Missing Wix credentials in .env")
    sys.exit(1)

with open(ROOT / "dashboard_data.json") as f:
    data = json.load(f)

posts = data["blog_seo_agent"]["posts"]
done, skipped_no_cover, skipped_no_draft = 0, 0, 0

for p in posts:
    if p.get("published"):
        continue
    draft_id = p.get("wix_draft_id")
    if not draft_id:
        skipped_no_draft += 1
        continue
    url = p.get("url", "")
    slug = url.split("/")[-1].replace(".html", "") if url else ""
    if not slug:
        continue
    img_dir = ROOT / "posts" / "images" / slug
    covers = sorted(img_dir.glob("cover-*.jpg")) if img_dir.exists() else []
    if not covers:
        print(f"[SKIP no cover] {slug}")
        skipped_no_cover += 1
        continue
    # set_cover_image always uses cover-1.jpg name in the URL — pass the actual filename
    cover_num = covers[0].name  # e.g. cover-2.jpg if cover-1 missing
    print(f"\n[{slug}]  draft={draft_id}  using {cover_num}")
    ok = set_cover_image(draft_id, slug, cover_filename=cover_num)
    if ok:
        done += 1

print(f"\n=== Done: {done} covers set | {skipped_no_cover} skipped (no cover image) | {skipped_no_draft} skipped (no draft ID) ===")
