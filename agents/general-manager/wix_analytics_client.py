"""
Wix Analytics client — General Manager

Wix's own native Analytics Data API — separate from the Media Manager work removed from
the image-delivery design, and separate from GA4. Reuses WIX_API_KEY/WIX_SITE_ID already
required for publish_to_wix.py — no new credential.

Verified directly against Wix's current REST docs (GET /analytics/v2/site-analytics/data):
measurement types are sitewide totals, not campaign-attributable the way GA4 is via UTM
tags, and Wix retains only 62 days of history (startDate more than 61 days back errors) —
fine for a weekly pull, no use for a later historical backfill.

The WIX_API_KEY needs the "Read Site Analytics" permission scope
(SCOPE.DC-ANALYTICS-AND-REPORTS.READ-SITE-ANALYTICS) — worth checking in Wix's dashboard
under Settings > API Keys if this client returns a permission error.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

WIX_API_KEY = os.getenv("WIX_API_KEY", "")
WIX_SITE_ID = os.getenv("WIX_SITE_ID", "")
WIX_API_BASE = "https://www.wixapis.com"

MEASUREMENT_TYPES = ["TOTAL_SESSIONS", "TOTAL_SALES", "TOTAL_ORDERS", "TOTAL_UNIQUE_VISITORS"]


def _headers() -> dict:
    return {
        "Authorization": WIX_API_KEY,
        "wix-site-id": WIX_SITE_ID,
        "Content-Type": "application/json",
    }


def fetch_sales_and_sessions(days: int = 28) -> dict:
    """
    Native Wix sessions/sales/orders/unique-visitors over the last `days` (capped at
    61 by Wix's own retention limit). Sitewide only — not per-post.
    """
    if not (WIX_API_KEY and WIX_SITE_ID):
        raise RuntimeError("WIX_API_KEY or WIX_SITE_ID not set in .env")

    days = min(days, 61)
    start_date = (date.today() - timedelta(days=days)).isoformat()
    end_date = date.today().isoformat()

    params = [
        ("date_range.start_date", start_date),
        ("date_range.end_date", end_date),
    ] + [("measurement_types", t) for t in MEASUREMENT_TYPES]

    resp = requests.get(
        f"{WIX_API_BASE}/analytics/v2/site-analytics/data",
        headers=_headers(),
        params=params,
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"Wix Analytics API error {resp.status_code}: {resp.text[:300]}")

    body = resp.json()
    result = {"start_date": start_date, "end_date": end_date}
    for item in body.get("data", []):
        result[item["type"].lower()] = item.get("total", 0)

    return result
