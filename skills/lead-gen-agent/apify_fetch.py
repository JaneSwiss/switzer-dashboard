"""
Apify Proxy fetch wrapper — routes requests through Apify US residential proxies.
Drop-in replacement for ScraperAPI. Uses APIFY_PROXY_PASSWORD from .env.
"""

import os
import sys
import time
import requests
import urllib3
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

APIFY_PROXY_PASSWORD = os.getenv("APIFY_PROXY_PASSWORD")
_PROXY_URL = (
    f"http://groups-RESIDENTIAL,country-US:{APIFY_PROXY_PASSWORD}@proxy.apify.com:8000"
    if APIFY_PROXY_PASSWORD else None
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

_printed_mode = False


def fetch(url, retries=2, timeout=60):
    """
    Fetch a URL and return the HTML response text.
    Routes through Apify residential proxy if APIFY_PROXY_PASSWORD is set,
    otherwise falls back to a direct connection.
    """
    global _printed_mode

    proxies = {"http": _PROXY_URL, "https": _PROXY_URL} if _PROXY_URL else None

    if not _printed_mode:
        mode = "Apify Proxy (US residential)" if proxies else "direct (no proxy — may be blocked)"
        print(f"[proxy] {mode}", file=sys.stderr)
        _printed_mode = True

    for attempt in range(retries + 1):
        try:
            r = requests.get(
                url,
                headers=_HEADERS,
                proxies=proxies,
                timeout=timeout,
                verify=False,
            )
            r.raise_for_status()
            return r.text
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            if code in (403, 401, 429):
                # Blocked — no point retrying other paths on this domain
                print(f"  [fetch error] {url} — {e}", file=sys.stderr)
                return "BLOCKED"
            if attempt < retries:
                time.sleep(3)
            else:
                print(f"  [fetch error] {url} — {e}", file=sys.stderr)
                return None
        except Exception as e:
            if attempt < retries:
                time.sleep(3)
            else:
                print(f"  [fetch error] {url} — {e}", file=sys.stderr)
                return None
