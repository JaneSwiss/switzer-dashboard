#!/usr/bin/env python3
"""
Run this after publishing a blog post to Wix to submit it for fast indexing.

Usage:
    python3 publish_indexing.py <slug>

Examples:
    python3 publish_indexing.py pinterest-marketing
    python3 publish_indexing.py coaching-business
    python3 publish_indexing.py pinterest-affiliate-marketing

What it does:
    1. Pings Google sitemap (tells Google to re-crawl immediately)
    2. Submits the live URL directly to Bing (requires BING_API_KEY in .env)
    3. Submits via IndexNow (notifies Bing, Yandex, and others — requires INDEXNOW_KEY in .env)

Setup (one-time):
    BING_API_KEY  — get from bing.com/webmasters → Settings → API Access
    INDEXNOW_KEY  — any random string, e.g. switzertemplates2026
                    Then create a Wix page at /{your-key} containing only the key text,
                    OR use Wix Velo to serve it at /{your-key}.txt
    BLOG_BASE_URL — the base URL of your Wix blog (default: https://www.switzertemplates.com/blog)
                    Check your actual Wix blog post URLs to confirm the format.
"""

import os
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

BING_API_KEY  = os.getenv("BING_API_KEY", "")
INDEXNOW_KEY  = os.getenv("INDEXNOW_KEY", "")
BLOG_BASE_URL = os.getenv("BLOG_BASE_URL", "https://www.switzertemplates.com/blog")
SITE_URL      = "https://www.switzertemplates.com"


def ping_google_sitemap() -> None:
    for sitemap in [f"{SITE_URL}/blog-posts-sitemap.xml", f"{SITE_URL}/sitemap.xml"]:
        try:
            resp = requests.get(f"https://www.google.com/ping?sitemap={sitemap}", timeout=10)
            label = sitemap.split("/")[-1]
            print(f"  Google sitemap ping ({label}): {'✓ sent' if resp.status_code == 200 else resp.status_code}")
        except Exception as e:
            print(f"  Google sitemap ping failed: {e}")


def submit_bing(post_url: str) -> None:
    if not BING_API_KEY:
        print("  Bing: skipped — add BING_API_KEY to .env")
        print("        Get it from: bing.com/webmasters → Settings → API Access")
        return
    try:
        resp = requests.post(
            f"https://ssl.bing.com/webmaster/api.svc/json/SubmitUrl?apikey={BING_API_KEY}",
            json={"siteUrl": SITE_URL, "url": post_url},
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=15,
        )
        print(f"  Bing direct: {'✓ sent' if resp.status_code == 200 else f'{resp.status_code} — {resp.text[:80]}'}")
    except Exception as e:
        print(f"  Bing failed: {e}")


def submit_indexnow(post_url: str) -> None:
    if not INDEXNOW_KEY:
        print("  IndexNow: skipped — add INDEXNOW_KEY to .env")
        print("            Any string works, e.g. INDEXNOW_KEY=switzertemplates2026")
        print("            Then create a Wix page at /{key} containing only that key.")
        return
    try:
        host = SITE_URL.replace("https://www.", "").replace("https://", "")
        payload = {
            "host": host,
            "key": INDEXNOW_KEY,
            "keyLocation": f"{SITE_URL}/{INDEXNOW_KEY}.txt",
            "urlList": [post_url],
        }
        resp = requests.post(
            "https://api.indexnow.org/indexnow",
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=15,
        )
        print(f"  IndexNow (Bing + Yandex + others): {'✓ sent' if resp.status_code in (200, 202) else f'{resp.status_code} — {resp.text[:80]}'}")
    except Exception as e:
        print(f"  IndexNow failed: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 publish_indexing.py <slug>")
        print("Example: python3 publish_indexing.py pinterest-marketing")
        sys.exit(1)

    slug = sys.argv[1].strip().lower()
    post_url = f"{BLOG_BASE_URL}/{slug}"

    print(f"\nSubmitting for indexing: {post_url}\n")
    ping_google_sitemap()
    submit_bing(post_url)
    submit_indexnow(post_url)
    print("\nDone. Google typically indexes within a few hours. Bing within 24-48 hours.")


if __name__ == "__main__":
    main()
