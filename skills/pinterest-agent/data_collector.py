"""
Pinterest Agent — Data Collector
Gathers Pinterest keyword intelligence and top-pin performance data
so Claude can select and prioritise 140 pin topics for Switzertemplates.

Sources:
  1. Keywords Everywhere (KE)   → Pinterest search volumes, competition, related terms,
                                   and autocomplete suggestions (via PASF)
  2. Pinterest search API       → Save counts for top pins per keyword (market signal)
  3. Pinterest API v5           → Jane's own top-performing pins (impressions, clicks)

Output: data/pinterest-agent/research-YYYY-MM-DD.json
"""
from __future__ import annotations

import os
import json
import time
import math
import requests
from datetime import datetime, timedelta, date
from pathlib import Path
from dotenv import load_dotenv

# ── Constants ─────────────────────────────────────────────────────────────────

PROJECT_ROOT          = Path(__file__).parent.parent.parent
DATA_DIR              = PROJECT_ROOT / "data" / "pinterest-agent"
KE_BASE               = "https://api.keywordseverywhere.com/v1"
PT_BASE               = "https://api.pinterest.com/v5"
KE_BATCH              = 100   # keywords per get_keyword_data call
KE_RELATED            = 15    # related/PASF terms per seed
SEARCH_PIN_CACHE_PATH = DATA_DIR / "search-pin-cache.json"

# Default seeds aligned with Switzertemplates' product catalog and audience
DEFAULT_SEEDS = [
    "wix website for coaches",
    "wix website for life coaches",
    "wix website for health coaches",
    "wix website for wellness coaches",
    "wix website for therapists",
    "wix website for consultants",
    "premade wix website for small business",
    "coaching website template",
    "therapy website template",
    "consultant website template",
    "health coach website template",
    "branding for life coaches",
    "branding for health coaches",
    "branding for therapists",
    "branding for consultants",
    "branding for female entrepreneurs",
    "branding for service based business",
    "coach branding package",
    "therapist branding kit",
    "done for you branding kit",
    "brand kit for small business",
    "brand identity for coaches",
    "canva branding kit small business",
    "premade branding kit",
    "instagram templates for coaches",
    "instagram templates for therapists",
    "instagram templates for consultants",
    "instagram templates for wellness coaches",
    "social media templates for coaches",
    "social media templates for therapists",
    "canva templates for small business",
    "canva instagram templates coaches",
    "website and branding package",
    "branding and website bundle",
    "coach website and branding",
    "business bundle for coaches",
    "done for you website and branding",
]


# ── Keywords Everywhere helpers ───────────────────────────────────────────────

def _ke_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def get_volumes(keywords: list[str], api_key: str) -> list[dict]:
    """
    Fetch Pinterest search volume, CPC, competition for every keyword.
    Batches in groups of KE_BATCH to stay within per-request limits.
    Returns list of {keyword, volume, cpc, competition, trend_12m}.
    """
    results = []
    batches = [keywords[i:i + KE_BATCH] for i in range(0, len(keywords), KE_BATCH)]

    for batch in batches:
        try:
            payload = [("kw[]", k) for k in batch] + [
                ("currency", "USD"), ("datafor", "pinterest")
            ]
            resp = requests.post(f"{KE_BASE}/get_keyword_data",
                headers=_ke_headers(api_key), data=payload, timeout=20)
            resp.raise_for_status()
            body = resp.json()
            for item in body.get("data", []):
                cpc_raw = item.get("cpc", {})
                cpc = float(cpc_raw.get("value", 0)) if isinstance(cpc_raw, dict) else float(cpc_raw or 0)
                trend = [t.get("value", 0) for t in item.get("trend", []) if isinstance(t, dict)]
                results.append({
                    "keyword":     item["keyword"],
                    "volume":      int(item.get("vol", 0)),
                    "cpc":         cpc,
                    "competition": float(item.get("competition", 0)),
                    "trend_12m":   trend,
                })
        except Exception as e:
            print(f"  [KE] Volume batch error: {e}")
        time.sleep(0.3)

    return results


def get_related_for_seed(seed: str, api_key: str, num: int = KE_RELATED) -> list[tuple[str, str]]:
    """
    Get related keywords and PASF for one seed.
    Returns list of (keyword, source_type) tuples.
    source_type: "related" (get_related_keywords) | "autocomplete" (get_pasf_keywords)
    """
    found: list[tuple[str, str]] = []
    seen:  set[str]              = set()
    endpoint_sources = [
        ("get_related_keywords", "related"),
        ("get_pasf_keywords",    "autocomplete"),
    ]
    for endpoint, source_type in endpoint_sources:
        try:
            resp = requests.post(f"{KE_BASE}/{endpoint}",
                headers=_ke_headers(api_key),
                data={"keyword": seed, "num": num,
                      "currency": "USD", "datafor": "pinterest"},
                timeout=15)
            if resp.ok:
                for item in resp.json().get("data", []):
                    kw = item if isinstance(item, str) else item.get("keyword", "")
                    kw = kw.strip().lower()
                    if kw and kw not in seen:
                        seen.add(kw)
                        found.append((kw, source_type))
        except Exception as e:
            print(f"  [KE] Related error ({endpoint}, '{seed}'): {e}")
        time.sleep(0.2)
    return found


# ── Pinterest API helpers ─────────────────────────────────────────────────────

def _pt_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _fetch_pin_details(pin_id: str, token: str) -> dict:
    """GET /v5/pins/{pin_id} — returns title, description, link, board_id."""
    try:
        resp = requests.get(f"{PT_BASE}/pins/{pin_id}",
            headers=_pt_headers(token), timeout=10)
        if resp.ok:
            d = resp.json()
            return {
                "title":       d.get("title", ""),
                "description": d.get("description", ""),
                "link":        d.get("link", ""),
                "board_id":    d.get("board_id", ""),
            }
    except Exception:
        pass
    return {"title": "", "description": "", "link": "", "board_id": ""}


def get_top_pins(token: str, n: int = 50) -> tuple[list[dict], str]:
    """
    Fetch the top n pins by impressions over the last 90 days.
    Step 1 — analytics/top_pins for IDs + metrics.
    Step 2 — GET /pins/{id} for each to retrieve title, description, link.

    Returns (pins_list, status).
    """
    end_dt   = date.today()
    start_dt = end_dt - timedelta(days=90)

    try:
        resp = requests.get(f"{PT_BASE}/user_account/analytics/top_pins",
            headers=_pt_headers(token),
            params={
                "start_date":  start_dt.isoformat(),
                "end_date":    end_dt.isoformat(),
                "sort_by":     "IMPRESSION",
                "num_of_pins": n,
            },
            timeout=15)

        if resp.status_code == 401:
            return [], "token_expired"
        if resp.status_code == 403:
            return [], "unavailable"
        resp.raise_for_status()

    except requests.RequestException as e:
        return [], f"error: {e}"

    items = resp.json().get("pins", [])
    if not items:
        return [], "no_data"

    pins = []
    for item in items[:n]:
        m      = item.get("metrics", {})
        pin_id = item.get("pin_id", "")
        impr   = int(m.get("IMPRESSION", 0))
        saves  = int(m.get("SAVE", 0))
        clicks = int(m.get("PIN_CLICK", 0))
        out_clicks = int(m.get("OUTBOUND_CLICK", 0))

        details = _fetch_pin_details(pin_id, token)
        time.sleep(0.15)

        pins.append({
            "pin_id":              pin_id,
            "title":               details["title"],
            "description":         details["description"],
            "link":                details["link"],
            "board_id":            details["board_id"],
            "impressions":         impr,
            "saves":               saves,
            "pin_clicks":          clicks,
            "outbound_clicks":     out_clicks,
            "engagement_rate":     round(m.get("ENGAGEMENT_RATE", 0), 4),
            "save_rate":           round(m.get("SAVE_RATE", 0), 4),
            "pin_click_rate":      round(m.get("PIN_CLICK_RATE", 0), 4),
            "outbound_click_rate": round(m.get("OUTBOUND_CLICK_RATE", 0), 4),
        })

    return sorted(pins, key=lambda p: p["impressions"], reverse=True), "ok"


# ── Pinterest search pin metrics ──────────────────────────────────────────────

def _load_search_pin_cache() -> dict:
    """Load cached search pin metrics to avoid repeat API calls across runs."""
    if SEARCH_PIN_CACHE_PATH.exists():
        try:
            return json.loads(SEARCH_PIN_CACHE_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_search_pin_cache(cache: dict) -> None:
    SEARCH_PIN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEARCH_PIN_CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def get_search_pin_metrics(keyword: str, token: str, cache: dict, n: int = 5) -> dict:
    """
    Fetch top n pins from Pinterest search for a keyword.
    Returns avg_saves, max_saves, pin_count.
    Uses save_count if the API returns it; falls back to pin_count as demand signal.
    Results cached in search-pin-cache.json so repeat runs skip the API call.
    """
    key = keyword.lower()
    if key in cache:
        return cache[key]

    empty = {"avg_saves": 0, "max_saves": 0, "pin_count": 0}

    if not token:
        cache[key] = {**empty, "source": "no_token"}
        return cache[key]

    try:
        resp = requests.get(
            f"{PT_BASE}/search/pins",
            headers=_pt_headers(token),
            params={"query": keyword, "page_size": n},
            timeout=15,
        )
        if resp.status_code == 401:
            try:
                code = resp.json().get("code")
            except Exception:
                code = None
            # Pinterest code 3 = insufficient scope; code 2 = bad/expired token
            source = "scope_error" if code == 3 else "token_expired"
            cache[key] = {**empty, "source": source}
            return cache[key]
        if not resp.ok:
            cache[key] = {**empty, "source": f"error_{resp.status_code}"}
            return cache[key]

        items = resp.json().get("items", [])
        pin_count = len(items)

        if pin_count == 0:
            cache[key] = {**empty, "source": "no_results"}
            return cache[key]

        saves = [int(p.get("save_count", 0)) for p in items]
        has_saves = any(s > 0 for s in saves)

        if has_saves:
            result = {
                "avg_saves": round(sum(saves) / len(saves)),
                "max_saves": max(saves),
                "pin_count": pin_count,
                "source":    "save_count",
            }
        else:
            # Fallback: API returned pins but no save_count field — use pin_count as signal
            result = {
                "avg_saves": 0,
                "max_saves": 0,
                "pin_count": pin_count,
                "source":    "pin_count_only",
            }

        cache[key] = result
        return result

    except Exception as e:
        cache[key] = {**empty, "source": f"error: {e}"}
        return cache[key]


# ── Summary helpers ───────────────────────────────────────────────────────────

def _trend_direction(trend_12m: list[int]) -> str:
    """Simple 6-month vs prior 6-month comparison."""
    if len(trend_12m) < 6:
        return "unknown"
    recent = sum(trend_12m[-6:])
    prior  = sum(trend_12m[:6])
    if prior == 0:
        return "new"
    ratio = recent / prior
    if ratio >= 1.15:
        return "rising"
    if ratio <= 0.85:
        return "falling"
    return "stable"


def _opportunity_score(vol: int, comp: float) -> float:
    """
    Simple opportunity score: high volume + low competition = high score.
    Normalised to 0-100.
    """
    if vol == 0:
        return 0.0
    vol_score  = min(math.log10(vol + 1) / 5, 1.0)
    comp_score = 1.0 - comp
    return round((vol_score * 0.6 + comp_score * 0.4) * 100, 1)


_NON_COMMERCIAL = {
    "login", "log in", "sign in", "sign up", "password", "forgot",
    "free", "free download", "download", "free trial",
    "what is", "how to use", "tutorial", "support", "help",
    "vs", "review", "reviews", "alternative", "alternatives",
    "coupon", "discount", "promo", "price", "pricing", "cost",
}

def _is_commercial(keyword: str) -> bool:
    """Return False if keyword contains clear non-commercial signals."""
    kw = keyword.lower()
    return not any(signal in kw for signal in _NON_COMMERCIAL)


def _build_summary(keyword_universe: list[dict]) -> dict:
    """Build a summary block Claude uses as a quick reference."""
    with_volume = [k for k in keyword_universe if k["volume"] > 0]
    sorted_vol  = sorted(with_volume, key=lambda k: k["volume"], reverse=True)
    sorted_opp  = sorted(with_volume, key=lambda k: k["opportunity_score"], reverse=True)
    rising      = [k for k in with_volume if k["trend_direction"] == "rising"]
    high_vol_low_comp = [
        k for k in with_volume
        if k["volume"] >= 1000 and k["competition"] <= 0.35
        and k.get("commercial_intent", True)
    ]

    def _slim(items: list[dict], n: int = 20) -> list[dict]:
        return [{"keyword": k["keyword"], "volume": k["volume"],
                 "competition": k["competition"], "opportunity_score": k["opportunity_score"]}
                for k in items[:n]]

    return {
        "total_keywords_analyzed": len(keyword_universe),
        "keywords_with_volume":    len(with_volume),
        "top_by_volume":           _slim(sorted_vol),
        "top_by_opportunity":      _slim(sorted_opp),
        "rising_keywords":         _slim(rising),
        "sweet_spot":              _slim(sorted(high_vol_low_comp,
                                                key=lambda k: k["opportunity_score"],
                                                reverse=True)),
    }


# ── Main collect function ─────────────────────────────────────────────────────

def collect(seeds: list[str] | None = None, top_pins: int = 50) -> dict:
    """
    Full collection run. Returns structured research dict ready for Claude.

    seeds:     list of seed keywords (defaults to DEFAULT_SEEDS)
    top_pins:  how many top Pinterest pins to pull
    """
    load_dotenv(PROJECT_ROOT / ".env")
    ke_key   = os.getenv("KEYWORDS_EVERYWHERE_API_KEY", "")
    pt_token = os.getenv("PINTEREST_ACCESS_TOKEN", "")

    if not ke_key:
        raise RuntimeError("KEYWORDS_EVERYWHERE_API_KEY not set in .env")

    seeds = seeds or DEFAULT_SEEDS
    print(f"Seeds: {len(seeds)}")

    # ── Step 1: volumes for seed keywords ─────────────────────────────────────
    print(f"\n[1/5] Fetching volumes for {len(seeds)} seed keywords...")
    seed_volumes = get_volumes(seeds, ke_key)
    seed_lookup  = {d["keyword"].lower(): d for d in seed_volumes}
    credits_used = len(seeds)
    print(f"  Done. {len(seed_volumes)} results, {credits_used} credits used.")

    # ── Step 2: expand via related + PASF (autocomplete proxy) ────────────────
    print(f"\n[2/5] Expanding via related keywords + PASF ({KE_RELATED} per seed)...")
    related_raw: dict[str, str] = {}   # keyword_lower → source_type
    for i, seed in enumerate(seeds, 1):
        terms = get_related_for_seed(seed, ke_key, num=KE_RELATED)
        for kw, src in terms:
            if kw not in seed_lookup and kw not in related_raw:
                related_raw[kw] = src
        if i % 10 == 0:
            print(f"  {i}/{len(seeds)} seeds expanded, {len(related_raw)} unique so far...")
    new_keywords = list(related_raw.keys())
    print(f"  {len(new_keywords)} new keywords to score.")

    # ── Step 3: volumes for related keywords ──────────────────────────────────
    print(f"\n[3/5] Fetching volumes for {len(new_keywords)} related keywords...")
    related_volumes = get_volumes(new_keywords, ke_key) if new_keywords else []
    credits_used += len(new_keywords)
    print(f"  Done. Credits used this run: ~{credits_used}")

    # ── Step 4: Jane's own top pins ───────────────────────────────────────────
    print(f"\n[4/5] Fetching top {top_pins} Pinterest pins (last 90 days)...")
    pins, pin_status = get_top_pins(pt_token, n=top_pins)
    if pin_status == "token_expired":
        print("  Pinterest token expired. Refresh at developers.pinterest.com → My Apps → your app.")
        print("  Pinterest data will be empty until the token is refreshed.")
    elif pin_status == "ok":
        print(f"  {len(pins)} pins retrieved.")
    else:
        print(f"  Pinterest status: {pin_status}")

    # ── Build keyword universe ─────────────────────────────────────────────────
    all_kw_data = seed_volumes + related_volumes
    seeds_lower = {s.lower() for s in seeds}
    seen: set[str] = set()
    keyword_universe = []
    for item in all_kw_data:
        key = item["keyword"].lower()
        if key in seen:
            continue
        seen.add(key)
        if key in seeds_lower:
            src = "seed"
        else:
            src = related_raw.get(key, "related")
        keyword_universe.append({
            **item,
            "trend_direction":      _trend_direction(item.get("trend_12m", [])),
            "opportunity_score":    _opportunity_score(item["volume"], item["competition"]),
            "source":               src,
            "commercial_intent":    _is_commercial(item["keyword"]),
            "search_pin_avg_saves": 0,
            "search_pin_max_saves": 0,
            "search_pin_count":     0,
        })

    keyword_universe.sort(key=lambda k: k["opportunity_score"], reverse=True)

    # ── Step 5: enrich top keywords with Pinterest search pin metrics ──────────
    print(f"\n[5/5] Enriching top keywords with Pinterest search pin metrics...")
    search_pin_cache = _load_search_pin_cache()
    eligible = [k for k in keyword_universe if k.get("volume", 0) >= 300][:100]
    print(f"  {len(eligible)} keywords eligible (vol ≥ 300, top 100 by opportunity score).")
    enriched = 0
    for kw in eligible:
        metrics = get_search_pin_metrics(kw["keyword"], pt_token, search_pin_cache, n=5)
        kw["search_pin_avg_saves"] = metrics["avg_saves"]
        kw["search_pin_max_saves"] = metrics["max_saves"]
        kw["search_pin_count"]     = metrics["pin_count"]
        if metrics["pin_count"] > 0:
            enriched += 1
        time.sleep(0.3)
    _save_search_pin_cache(search_pin_cache)
    print(f"  {enriched}/{len(eligible)} keywords enriched with search pin data. Cache saved.")

    # ── Assemble output ────────────────────────────────────────────────────────
    output = {
        "collected_at":        datetime.now().isoformat(),
        "seeds_used":          seeds,
        "credits_used_approx": credits_used,
        "pinterest_status":    pin_status,
        "keyword_universe":    keyword_universe,
        "top_pins":            pins,
        "summary":             _build_summary(keyword_universe),
    }

    return output


def save(data: dict, path: Path | None = None) -> Path:
    """Save the research output to JSON. Returns the path written."""
    if path is None:
        today = datetime.now().strftime("%Y-%m-%d")
        path  = DATA_DIR / f"research-{today}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


def enrich_only(research_path: Path, top_pins: int = 50) -> Path:
    """
    Re-run steps 4+5 only (own pins + search pin metrics) on an existing research JSON.
    Use after refreshing the Pinterest token without re-spending KE credits.
    Updates the research JSON in place and returns the path.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    pt_token = os.getenv("PINTEREST_ACCESS_TOKEN", "")

    data = json.loads(research_path.read_text())
    keyword_universe = data["keyword_universe"]

    print(f"\nEnrich-only mode — loading: {research_path.name}")
    print(f"  {len(keyword_universe)} keywords in universe.")

    # Step 4: own top pins
    print(f"\n[4/5] Fetching top {top_pins} Pinterest pins (last 90 days)...")
    pins, pin_status = get_top_pins(pt_token, n=top_pins)
    if pin_status == "token_expired":
        print("  Pinterest token still expired. Refresh at developers.pinterest.com and retry.")
        return research_path
    elif pin_status == "ok":
        print(f"  {len(pins)} pins retrieved.")
    else:
        print(f"  Pinterest status: {pin_status}")

    # Step 5: search pin metrics
    print(f"\n[5/5] Enriching top keywords with Pinterest search pin metrics...")
    search_pin_cache = _load_search_pin_cache()
    eligible = [k for k in keyword_universe if k.get("volume", 0) >= 300][:100]
    print(f"  {len(eligible)} keywords eligible (vol ≥ 300, top 100 by opportunity score).")
    enriched = 0
    for kw in eligible:
        metrics = get_search_pin_metrics(kw["keyword"], pt_token, search_pin_cache, n=5)
        kw["search_pin_avg_saves"] = metrics["avg_saves"]
        kw["search_pin_max_saves"] = metrics["max_saves"]
        kw["search_pin_count"]     = metrics["pin_count"]
        if metrics["pin_count"] > 0:
            enriched += 1
        time.sleep(0.3)
    _save_search_pin_cache(search_pin_cache)
    print(f"  {enriched}/{len(eligible)} keywords enriched. Cache saved.")

    # Update and write
    data["top_pins"]         = pins
    data["pinterest_status"] = pin_status
    data["collected_at"]     = datetime.now().isoformat()
    research_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nUpdated → {research_path}")
    return research_path


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(description="Collect Pinterest keyword + pin data")
    parser.add_argument("--seeds-file",   help="Text file with one seed keyword per line")
    parser.add_argument("--top-pins",     type=int, default=50, help="How many top pins to pull (default 50)")
    parser.add_argument("--output",       help="Output JSON path (default: data/pinterest-agent/research-YYYY-MM-DD.json)")
    parser.add_argument("--enrich-only",  action="store_true",
                        help="Re-run steps 4+5 only (own pins + search pin saves) on the most recent research JSON. "
                             "Use after refreshing the Pinterest token without re-spending KE credits.")
    args = parser.parse_args()

    if args.enrich_only:
        files = sorted(DATA_DIR.glob("research-*.json"))
        if not files:
            print("No research files found. Run without --enrich-only first."); sys.exit(1)
        target = Path(args.output) if args.output else files[-1]
        enrich_only(target, top_pins=args.top_pins)
        sys.exit(0)

    seeds = None
    if args.seeds_file:
        p = Path(args.seeds_file)
        if not p.exists():
            print(f"Seeds file not found: {p}"); sys.exit(1)
        seeds = [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")]
        print(f"Loaded {len(seeds)} seeds from {p}")

    data = collect(seeds=seeds, top_pins=args.top_pins)

    out_path = save(data, Path(args.output) if args.output else None)
    print(f"\nSaved → {out_path}")

    s = data["summary"]
    enriched_count = sum(1 for k in data["keyword_universe"] if k.get("search_pin_count", 0) > 0)
    print(f"\n{'─'*50}")
    print(f"Keywords analysed:   {s['total_keywords_analyzed']}")
    print(f"With volume:         {s['keywords_with_volume']}")
    if s["top_by_opportunity"]:
        top = s["top_by_opportunity"][0]
        print(f"Top opportunity:     {top['keyword']} (score {top['opportunity_score']}) vol {top['volume']}")
    print(f"Search pin data:     {enriched_count} keywords enriched")
    print(f"Pinterest pins:      {len(data['top_pins'])} ({data['pinterest_status']})")
    print(f"Credits used:        ~{data['credits_used_approx']}")
    print(f"{'─'*50}")
