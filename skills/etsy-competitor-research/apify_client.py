"""
ScraperAPI wrapper for fetching pages through rotating US proxies.
ScraperAPI handles anti-bot, IP rotation, and retries automatically.

Set SCRAPERAPI_KEY in .env (get yours at scraperapi.com).
Free plan: 5,000 credits/month. One Etsy page ≈ 1 credit.
"""

import os
import sys
import time
import requests
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY")
SCRAPERAPI_ENDPOINT = "https://api.scraperapi.com/"

_DIRECT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xhtml+xml,*/*;q=0.8",
}

_printed_mode = False


def fetch(url, retries=2):
    """
    Fetch a URL and return the HTML response text.
    Routes through ScraperAPI if SCRAPERAPI_KEY is set, otherwise direct.
    ScraperAPI automatically handles rotating IPs, anti-bot, and retries.
    """
    global _printed_mode

    if SCRAPERAPI_KEY:
        if not _printed_mode:
            print("[proxy] ScraperAPI active — US rotating proxies", file=sys.stderr)
            _printed_mode = True
        params = {
            "api_key": SCRAPERAPI_KEY,
            "url": url,
            "country_code": "us",
        }
        for attempt in range(retries + 1):
            try:
                r = requests.get(SCRAPERAPI_ENDPOINT, params=params, timeout=60)
                r.raise_for_status()
                return r.text
            except Exception as e:
                if attempt < retries:
                    time.sleep(3)
                else:
                    print(f"  [fetch error] {e}", file=sys.stderr)
                    return None
    else:
        if not _printed_mode:
            print("[proxy] No SCRAPERAPI_KEY — direct connection (may be blocked by Etsy)",
                  file=sys.stderr)
            _printed_mode = True
        for attempt in range(retries + 1):
            try:
                r = requests.get(url, headers=_DIRECT_HEADERS, timeout=20)
                r.raise_for_status()
                return r.text
            except Exception as e:
                if attempt < retries:
                    time.sleep(2)
                else:
                    print(f"  [fetch error] {e}", file=sys.stderr)
                    return None
