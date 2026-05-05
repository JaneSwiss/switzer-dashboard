"""
Pinterest Agent — Analytics Loader

Two distinct fetch modes:

  load_pin_patterns()  — fast, used every --generate run for copy-style guidance.
                         Pulls top 50 pins by impressions, last 90 days.

  fetch_pins_12m()     — deep research, used for master keyword list builds.
                         Pulls 4 × 90-day windows (12 months total), each sorted
                         by IMPRESSION *and* OUTBOUND_CLICK, deduped by pin_id.
                         Caches pin details locally so repeat calls are fast.
"""
from __future__ import annotations

import os
import re
import time
import json
import requests
from datetime import date, timedelta
from pathlib import Path

PT_BASE = "https://api.pinterest.com/v5"


# ── Pinterest API helpers ─────────────────────────────────────────────────────

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _fetch_pin_details(pin_id: str, token: str) -> dict:
    try:
        r = requests.get(f"{PT_BASE}/pins/{pin_id}",
                         headers=_headers(token), timeout=10)
        if r.ok:
            d = r.json()
            return {
                "title":       d.get("title", ""),
                "description": d.get("description", ""),
                "link":        d.get("link", ""),
                "board_id":    d.get("board_id", ""),
            }
    except Exception:
        pass
    return {"title": "", "description": "", "link": "", "board_id": ""}


def _fetch_top_pins(token: str, n: int = 50) -> tuple[list[dict], str]:
    """Pull top n pins by impressions. Returns (pins, status)."""
    end   = date.today()
    start = end - timedelta(days=90)
    try:
        r = requests.get(f"{PT_BASE}/user_account/analytics/top_pins",
            headers=_headers(token),
            params={"start_date": start.isoformat(), "end_date": end.isoformat(),
                    "sort_by": "IMPRESSION", "num_of_pins": n},
            timeout=15)
        if r.status_code == 401:
            return [], "token_expired"
        if r.status_code == 403:
            return [], "unavailable"
        r.raise_for_status()
    except requests.RequestException as e:
        return [], f"error: {e}"

    items = r.json().get("pins", [])
    if not items:
        return [], "no_data"

    pins = []
    for item in items[:n]:
        m      = item.get("metrics", {})
        pin_id = item.get("pin_id", "")
        impr   = int(m.get("IMPRESSION", 0))
        saves  = int(m.get("SAVE", 0))
        clicks = int(m.get("PIN_CLICK", 0))
        out    = int(m.get("OUTBOUND_CLICK", 0))

        details = _fetch_pin_details(pin_id, token)
        time.sleep(0.15)

        pins.append({
            "pin_id":              pin_id,
            "title":               details["title"],
            "description":         details["description"],
            "link":                details["link"],
            "impressions":         impr,
            "saves":               saves,
            "pin_clicks":          clicks,
            "outbound_clicks":     out,
            "save_rate":           round(m.get("SAVE_RATE", 0), 4),
            "outbound_click_rate": round(m.get("OUTBOUND_CLICK_RATE", 0), 4),
            "pin_click_rate":      round(m.get("PIN_CLICK_RATE", 0), 4),
        })

    return sorted(pins, key=lambda p: p["impressions"], reverse=True), "ok"


# ── Pattern extraction ────────────────────────────────────────────────────────

def _detect_title_structure(title: str) -> str:
    """Classify a pin title into one of the known high-performing structures."""
    t = title.lower().strip()
    if not t:
        return "unknown"
    if re.match(r"^how to ", t):
        return "how_to"
    if " that " in t:
        return "keyword_that_outcome"
    if re.match(r"^a ", t) and " ready to " in t:
        return "a_product_ready_to"
    if ":" in t:
        return "audience_colon"
    if re.match(r"^\d+", t):
        return "numbered_list"
    return "statement"


def _extract_patterns(pins: list[dict]) -> dict:
    """
    Extract actionable patterns from the top pins.
    Focuses on outbound_click_rate as the primary signal (per pinterest-expert.md).
    """
    if not pins:
        return {
            "top_by_ocr":        [],
            "avg_ocr":           0.0,
            "best_ocr":          0.0,
            "title_structures":  {},
            "performance_context": "No pin analytics available for this run.",
        }

    top_by_ocr = sorted(pins, key=lambda p: p["outbound_click_rate"], reverse=True)[:10]

    # Count title structures in top 10 by OCR
    structure_counts: dict[str, int] = {}
    for p in top_by_ocr:
        s = _detect_title_structure(p["title"])
        structure_counts[s] = structure_counts.get(s, 0) + 1

    avg_ocr  = round(sum(p["outbound_click_rate"] for p in pins) / len(pins), 4)
    best_ocr = top_by_ocr[0]["outbound_click_rate"] if top_by_ocr else 0.0

    # Build narrative summary for Claude
    top_titles = [p["title"] for p in top_by_ocr[:5] if p["title"]]
    dominant_structure = max(structure_counts, key=structure_counts.get) \
        if structure_counts else "unknown"

    lines = [
        f"Account analytics (last 90 days, {len(pins)} top pins by impressions):",
        f"  Average outbound click rate: {avg_ocr:.3%}",
        f"  Best outbound click rate:    {best_ocr:.3%}",
        f"  Dominant title structure in top 10 by OCR: {dominant_structure}",
        f"  Title structure counts in top 10: {structure_counts}",
        "",
        "Top 5 pins by outbound click rate (titles to learn from):",
    ]
    for p in top_by_ocr[:5]:
        lines.append(
            f"  OCR={p['outbound_click_rate']:.3%}  "
            f"saves={p['save_rate']:.3%}  "
            f"\"{p['title'][:70] or '(no title)'}\""
        )

    # Warn if save rate >> OCR (inspiring but not converting)
    avg_save = sum(p["save_rate"] for p in pins) / len(pins)
    if avg_save > avg_ocr * 3:
        lines.append(
            "\nNote: Save rates are significantly higher than outbound click rates. "
            "Current pins inspire saves but underperform on clicks. "
            "Prioritise titles with specific promises over atmospheric hooks."
        )

    return {
        "top_by_ocr":          [{"title": p["title"], "ocr": p["outbound_click_rate"]}
                                 for p in top_by_ocr[:10]],
        "avg_ocr":             avg_ocr,
        "best_ocr":            best_ocr,
        "title_structures":    structure_counts,
        "dominant_structure":  dominant_structure,
        "performance_context": "\n".join(lines),
    }


# ── Deep 12-month pin fetch ───────────────────────────────────────────────────

def fetch_pins_deep(
    token: str,
    n: int = 50,
    cache_path: Path | None = None,
) -> tuple[list[dict], dict]:
    """
    Deep pin pull for keyword master list builds.

    Pinterest API hard limit: top_pins endpoint only supports the last 90 days.
    Multi-window lookback is not possible.

    Within that 90-day window this function makes two calls:
      - sort_by=IMPRESSION    → top n pins by reach
      - sort_by=OUTBOUND_CLICK → top n pins by conversions

    High-OCR pins that don't rank in the impression top-n would be missed by
    a single-sort call. Both sorts are merged by pin_id (best OCR wins) giving
    up to 2n unique pins — the maximum this API supports.

    Pin details (title, description, link) are cached locally so repeat deep
    runs skip the individual GET calls.

    Returns (pins_sorted_by_ocr_desc, coverage_summary).
    """
    if not token:
        return [], {"status": "no_token", "unique_pins": 0}

    end_dt   = date.today()
    start_dt = end_dt - timedelta(days=90)

    cache: dict[str, dict] = {}
    if cache_path and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
        except Exception:
            pass

    merged: dict[str, dict] = {}
    api_calls = 0

    for sort_by in ("IMPRESSION", "OUTBOUND_CLICK"):
        try:
            r = requests.get(
                f"{PT_BASE}/user_account/analytics/top_pins",
                headers=_headers(token),
                params={
                    "start_date":  start_dt.isoformat(),
                    "end_date":    end_dt.isoformat(),
                    "sort_by":     sort_by,
                    "num_of_pins": n,
                },
                timeout=20,
            )
            api_calls += 1
            if r.status_code == 401:
                return [], {"status": "token_expired", "unique_pins": 0}
            if not r.ok:
                continue
        except requests.RequestException:
            time.sleep(1)
            continue

        for item in r.json().get("pins", []):
            m      = item.get("metrics", {})
            pin_id = item.get("pin_id", "")
            if not pin_id:
                continue
            ocr = float(m.get("OUTBOUND_CLICK_RATE", 0))
            if pin_id in merged and merged[pin_id]["outbound_click_rate"] >= ocr:
                continue
            merged[pin_id] = {
                "pin_id":              pin_id,
                "impressions":         int(m.get("IMPRESSION", 0)),
                "saves":               int(m.get("SAVE", 0)),
                "pin_clicks":          int(m.get("PIN_CLICK", 0)),
                "outbound_clicks":     int(m.get("OUTBOUND_CLICK", 0)),
                "save_rate":           round(float(m.get("SAVE_RATE", 0)), 4),
                "outbound_click_rate": round(ocr, 4),
                "pin_click_rate":      round(float(m.get("PIN_CLICK_RATE", 0)), 4),
            }
        time.sleep(0.3)

    need_details = [pid for pid in merged if pid not in cache]
    if need_details:
        print(f"  Fetching details for {len(need_details)} new pins "
              f"({len(merged) - len(need_details)} cached)...")
        for pin_id in need_details:
            cache[pin_id] = _fetch_pin_details(pin_id, token)
            time.sleep(0.15)
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, indent=2))
    elif merged:
        print(f"  All {len(merged)} pin details served from cache.")

    result = []
    for pin_id, p in merged.items():
        d = cache.get(pin_id, {})
        result.append({**p, "title": d.get("title", ""), "description": d.get("description", ""),
                       "link": d.get("link", ""), "board_id": d.get("board_id", "")})

    result.sort(key=lambda p: p["outbound_click_rate"], reverse=True)

    summary = {
        "status":        "ok",
        "unique_pins":   len(result),
        "api_calls":     api_calls,
        "date_range":    f"{start_dt} to {end_dt}",
        "sort_passes":   "IMPRESSION + OUTBOUND_CLICK",
        "converters":    sum(1 for p in result if p.get("outbound_clicks", 0) >= 3),
    }
    return result, summary


# Keep the old name as an alias so any existing callers don't break
fetch_pins_12m = fetch_pins_deep


# ── Main entry point ──────────────────────────────────────────────────────────

def load_pin_patterns(token: str | None = None,
                      research_fallback: Path | None = None) -> dict:
    """
    Load top pin patterns.
    1. Tries the Pinterest API with the provided token.
    2. Falls back to pins already in the research JSON if the token fails.
    3. Returns an empty-patterns dict if neither source is available.
    """
    pins: list[dict] = []
    status = "unavailable"

    if token:
        pins, status = _fetch_top_pins(token, n=50)
        if status == "token_expired":
            print("  Pinterest token expired — falling back to research file pins.")
        elif status == "ok":
            print(f"  Pinterest API: {len(pins)} pins loaded.")

    if not pins and research_fallback and research_fallback.exists():
        try:
            data = json.loads(research_fallback.read_text())
            pins = data.get("top_pins", [])
            if pins:
                status = "research_fallback"
                print(f"  Analytics fallback: {len(pins)} pins from {research_fallback.name}.")
        except Exception:
            pass

    patterns = _extract_patterns(pins)
    patterns["status"] = status
    return patterns
