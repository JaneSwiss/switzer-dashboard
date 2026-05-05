"""
Pinterest Agent — Topic Selector
Three-source keyword scoring: Keywords Everywhere + Pinterest own analytics + account signals.
Copy generation delegated to copy_writer.py (expert-context + analytics).

Scoring sources:
  KE   Keywords Everywhere  — search volume, competition, trend direction
  PT   Pinterest API        — pin performance per keyword (impressions, saves, outbound
                              click rate cross-referenced from live or cached top_pins)
  OA   Own Analytics        — topics already driving traffic to Jane's site, extracted
                              from pins with outbound_clicks ≥ 3 (proven converters)

Pipeline:
  Step 1  Load all keywords from research JSON (KE data + Pinterest top_pins)
          + manual CSV additions
  Step 2a Fetch fresh Pinterest API pins (merge with research file), build pin_index (PT)
  Step 2b Build OA topic set from traffic-driving pins (outbound_clicks ≥ 3)
  Step 3  Score: opportunity × trend × product_match × audience_match × pp_boost (PT) × oa_boost (OA)
  Step 4  Deduplicate plural/singular pairs — keep the higher-volume variant
  Step 5  Auto-fill products with 0 keywords via KE + PT + OA (no manual action needed)
  Step 6  Print scoring table with OA_OCR and SOURCES columns (stop here for review)
  Step 7  Load Pinterest analytics via analytics_loader.py (--generate only)
  Step 8  Apply revenue weighting, generate 5 pin variations per keyword

Usage:
  python3 topic_selector.py                                       # score table only
  python3 topic_selector.py --generate --output topics-final.json # full run
"""
from __future__ import annotations

import os
import re
import csv
import json
import math
import time
import anthropic
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR     = PROJECT_ROOT / "data" / "pinterest-agent"
CONTEXT_DIR  = PROJECT_ROOT / "context"
KE_BASE      = "https://api.keywordseverywhere.com/v1"
KE_BATCH     = 100


# ── Product + audience match rules ───────────────────────────────────────────
# Evaluated in priority order within each score tier.
# First match wins — so Score 3 rules are checked before Score 2.

# (substring_in_keyword, product_name)
_SCORE_3: list[tuple[str, str]] = [
    # 3-in-1 Business Bundle — checked before "wix website" to avoid early match
    ("business bundle",         "3-in-1 Business Bundle"),
    ("branding bundle",         "3-in-1 Business Bundle"),
    ("3-in-1",                  "3-in-1 Business Bundle"),
    ("wix website and branding", "3-in-1 Business Bundle"),
    ("wix and branding",        "3-in-1 Business Bundle"),
    ("website and branding",    "3-in-1 Business Bundle"),
    # Premade Wix Website
    ("wix website",             "Premade Wix Website"),
    ("wix template",            "Premade Wix Website"),
    ("premade wix",             "Premade Wix Website"),
    # Full Branding Kit
    ("branding kit",            "Full Branding Kit"),
    ("premade branding kit",    "Full Branding Kit"),
    ("branding kit canva",      "Full Branding Kit"),
    # Instagram Template Pack
    ("instagram template",      "Instagram Template Pack"),
    ("instagram post template", "Instagram Template Pack"),
    ("instagram branding template", "Instagram Template Pack"),
]

_SCORE_2: list[tuple[str, str]] = [
    # Website-adjacent (Premade Wix Website)
    ("coach website",           "Premade Wix Website"),
    ("wix site",                "Premade Wix Website"),
    ("online store template",   "Premade Wix Website"),
    # Branding Kit-adjacent
    ("canva instagram template","Instagram Template Pack"),
    ("instagram branding",      "Full Branding Kit"),
    ("instagram feed",          "Full Branding Kit"),
    ("social media template",   "Full Branding Kit"),
    ("social media branding",   "Full Branding Kit"),
    ("branding design",         "Full Branding Kit"),
    ("branding identity",       "Full Branding Kit"),
    ("branding template",       "Full Branding Kit"),
    ("brand identity",          "Full Branding Kit"),
    ("canva template",          "Full Branding Kit"),
    # General
    ("business template",       "All Products"),
]

# Audience signals — any match → product_match = max(existing, 1), audience_match = 1
_AUDIENCE_SIGNALS: list[str] = [
    "coach", "coaches", "consultant",
    "virtual assistant",              # "va " removed — matched falsely inside "canva "
    "therapist", "wellness", "beauty", "esthetician", "nutritionist",
    "photographer", "entrepreneur", "small business", "service provider",
    "female", "women", "freelancer",
    "online business",
]

# Hard-eliminate these patterns — zero intent for Switzertemplates.
# Eliminated immediately like falling-trend keywords (return None from _score_keyword).
_ELIMINATE_SUBSTRINGS: list[str] = [
    # Navigational
    "login", "log in", "sign in", "sign up",
    # Job-seeker intent
    " jobs", " job ",
    # Dictionary / informational (pinterest-expert.md: "what is" / "what does" prefix)
    "definition", "what is", "what does", "meaning",
    # Free-seeker intent (pinterest-expert.md: "free" in keyword = non-buyer)
    " free",
    # Software-seeking intent (pinterest-expert.md: "app" suffix)
    " app",
    # Wrong document types
    "download", "blank template", "business plan", "template word",
    # Canva feature / platform navigation
    "photo editor", "canva uk", "canva us ", "canva au",
    "canva upgrade", "canva desktop",
    # File format queries
    " png", " pdf", "template pdf", " psd",
    # Research / wrong-stage intent
    "ideas for beginner", "should i", "how much",
    # Hiring intent
    "marketing agency",
    # Year-dated queries
    " 2017", " 2018", " 2019", " 2020", " 2021",
    # Informational without buyer intent (research/inspiration intent, not buying)
    "examples of small", "business examples", " example", " examples",
    # Wrong niches
    "coaching fitness", "wood branding",
    # Comparison shopping (pinterest-expert.md: comparison shopping = wrong stage)
    "website builder software", "best website builder",
    "vs shopify", "vs squarespace", "vs wix",
]

# Keywords whose KE Pinterest trend shows as falling but Jane has confirmed as relevant.
# These are treated as stable regardless of what KE returns.
_TREND_OVERRIDE: set[str] = {
    "starting a business",
    "small business marketing",
    "small business templates",
    "how to grow business",
    "pinterest for business",
    "personal branding",
    "business templates",
}

# Exact-match eliminations — substring rules would be too broad here
_ELIMINATE_EXACT: set[str] = {
    "coaching",                          # 2.7M volume but too generic; "life coaching" etc. are kept
    "pinterest",                         # platform navigation — comes in via PASF, never buyer intent
    "therapist website examples",        # "examples" = passive research intent, not buyer intent
    "free canva templates",              # "free" = non-buyer intent
    "brand identity for coaches template", # noise variant of "brand identity for coaches"
    "wix website and branding kit",          # auto-research fill — not a real search term
    "branding identity",                     # generic informational, not product-specific intent
    "canva templates",                       # too broad — canva platform navigation, not buyer
    "social media templates branding",       # vol=0 noise variant of branding kit keywords
    "social media templates design posts",   # vol=0 noise variant
    "branding design social media",          # vol=0 noise variant of branding design
}

_MIN_VOLUME = 300   # keywords below this are not worth targeting (Tier 3 floor from pinterest-expert.md)

# Wix opportunity boost: competitor analysis shows Wix keywords are completely
# uncontested — no competitor pins target them. Apply 1.3x to final_score.
_WIX_BOOST = 1.3

# Terms that indicate no direct product match — product_match = 0, but not eliminated
_NOISE_SUBSTRINGS: list[str] = [
    "logo design",   # competitor/generic search, not direct product intent
]

# Audience-only keywords (PM=1) must also contain one of these product/solution signals.
# If none are present the keyword is eliminated. If at least one is present PM is upgraded to 2.
_COMPOUND_SIGNALS: list[str] = [
    "branding", "template", "website", "kit", "bundle", "package",
    "canva", "wix", "instagram", "social media", "marketing",
]

# Revenue weighting for pin batch product distribution
_PRODUCT_WEIGHT: dict[str, float] = {
    "Premade Wix Website":     0.35,
    "3-in-1 Business Bundle":  0.30,
    "Full Branding Kit":       0.25,
    "Instagram Template Pack": 0.10,
}

# Product-specific seeds used when a product has 0 keywords after scoring.
# The auto-fill step queries KE for these, scores them, and adds the best 3 per product.
_PRODUCT_AUTO_SEEDS: dict[str, list[str]] = {
    "3-in-1 Business Bundle": [
        "business branding bundle", "branding and website bundle",
        "brand kit and website template", "business starter pack for coaches",
        "complete business template bundle", "brand package for small business",
        "wix website and branding kit", "business bundle for coaches",
        "branding website bundle for coaches", "branding bundle for small business",
    ],
    "Premade Wix Website": [
        "wix website for therapists", "wix website for consultants",
        "wix website template for service business", "premade website templates",
        "wix website for wellness coach", "wix business website template",
        "wix website for esthetician", "wix website for photographers",
        "wix website for small business owner", "wix template for service provider",
    ],
    "Full Branding Kit": [
        "canva branding kit for coaches", "branding kit for therapists",
        "branding kit for wellness", "complete branding kit canva",
        "branding kit for esthetician", "branding pack for small business",
        "brand kit for coaches", "branding kit for female entrepreneur",
    ],
    "Instagram Template Pack": [
        "instagram templates for coaches", "instagram templates for therapists",
        "canva instagram templates for business", "instagram post templates canva",
        "instagram templates for wellness", "instagram templates for esthetician",
        "instagram templates for service providers", "instagram templates for consultants",
    ],
}


# ── Pinterest own-analytics helpers ──────────────────────────────────────────

def _build_pin_index(pins: list[dict]) -> dict:
    """Pre-process top_pins for fast keyword matching at scoring time."""
    return {
        "pins":         pins,
        "titles_lower": [p.get("title", "").lower() for p in pins],
        "desc_lower":   [p.get("description", "").lower() for p in pins],
    }


def _get_pin_signal(keyword: str, pin_index: dict) -> dict:
    """
    Find every top pin whose title or description contains this keyword (or its
    singular/plural variant) and return aggregate OA performance metrics.
    """
    if not pin_index or not pin_index.get("pins"):
        return {"pt_pin_count": 0, "pt_ocr_best": 0.0, "pt_ocr_avg": 0.0,
                "pt_impressions": 0, "pt_source": "no_pin_data"}

    kw = keyword.lower()
    # Build a small set of variants to broaden matching slightly
    variants: set[str] = {kw}
    if kw.endswith("s") and len(kw) > 4:
        variants.add(kw[:-1])          # templates → template
    else:
        variants.add(kw + "s")         # template  → templates
    # Also try first two words for compound keywords
    words = kw.split()
    if len(words) >= 2:
        variants.add(" ".join(words[:2]))

    matching = [
        pin_index["pins"][i]
        for i, (title, desc) in enumerate(
            zip(pin_index["titles_lower"], pin_index["desc_lower"])
        )
        if any(v in title or v in desc for v in variants)
    ]

    if not matching:
        return {"pt_pin_count": 0, "pt_ocr_best": 0.0, "pt_ocr_avg": 0.0,
                "pt_impressions": 0, "oa_outbound_clicks": 0, "pt_source": "no_pin_data"}

    ocrs = [p.get("outbound_click_rate", 0.0) for p in matching]
    return {
        "pt_pin_count":        len(matching),
        "pt_ocr_best":         round(max(ocrs), 4),
        "pt_ocr_avg":          round(sum(ocrs) / len(ocrs), 4),
        "pt_impressions":      sum(p.get("impressions", 0) for p in matching),
        "oa_outbound_clicks":  sum(p.get("outbound_clicks", 0) for p in matching),
        "pt_source":           "own_analytics",
    }


def _pp_boost(pin_signal: dict) -> float:
    """
    Translate PT pin performance into a score multiplier.
    Good OCR → boost (double down on what's working).
    No pin data → neutral (don't penalise uncharted keywords).
    Covered but not converting → slight discount only if we have enough data.
    """
    ocr   = pin_signal.get("pt_ocr_best", 0.0)
    count = pin_signal.get("pt_pin_count", 0)
    impr  = pin_signal.get("pt_impressions", 0)

    if ocr >= 0.005:                        # ≥0.5% OCR — strong performer
        return 1.4
    if ocr >= 0.001:                        # 0.1–0.5% — solid signal
        return 1.2
    if count > 0 and impr >= 3000:          # covered, decent reach, not converting
        return 0.9                          # slight discount — try new copy first
    return 1.0                              # no pin data or too little data → neutral


def _ke_pin_boost(kw_data: dict) -> float:
    """
    Boost based on average saves of top Pinterest search result pins for this keyword.
    High saves on competitor pins = strong market engagement signal for the keyword.
    Falls back to pin_count when save_count wasn't returned by the API.
    Thresholds are provisional — adjust after the first real data run.
    """
    avg_saves = kw_data.get("search_pin_avg_saves", 0)
    pin_count = kw_data.get("search_pin_count", 0)

    if avg_saves >= 500:
        return 1.25
    if avg_saves >= 100:
        return 1.10
    if avg_saves > 0:
        return 1.0    # data present but low saves — neutral
    if pin_count >= 5:
        return 1.05   # fallback: 5 pins confirmed but no save_count data
    return 1.0        # no data or no results — neutral


# ── Product + audience match rules ───────────────────────────────────────────

def _score_product_match(keyword: str) -> tuple[int, str]:
    """Return (product_match_score 0-3, maps_to_product string)."""
    kw = keyword.lower()

    # Noise check first
    if any(n in kw for n in _NOISE_SUBSTRINGS):
        return 0, "No direct product match"

    for phrase, product in _SCORE_3:
        if phrase in kw:
            return 3, product

    for phrase, product in _SCORE_2:
        if phrase in kw:
            return 2, product

    for signal in _AUDIENCE_SIGNALS:
        if signal in kw:
            return 1, "Audience — all products"

    return 0, "No direct product match"


def _score_audience_match(keyword: str) -> int:
    kw = keyword.lower()
    return 1 if any(s in kw for s in _AUDIENCE_SIGNALS) else 0


def _opportunity_score(vol: int, comp: float) -> float:
    if vol == 0:
        return 0.0
    vol_score  = min(math.log10(vol + 1) / 5, 1.0)
    comp_score = 1.0 - comp
    return round((vol_score * 0.6 + comp_score * 0.4) * 100, 1)


_TREND_MULT = {"rising": 1.0, "stable": 0.7, "falling": 0.0}


def _score_keyword(kw_data: dict, pin_index: dict | None = None) -> dict | None:
    """
    Score one keyword using all three sources.

    KE    — opportunity_score from Keywords Everywhere volume + competition
    PT    — Pinterest API pin data: OCR + impressions from matching top_pins
    OA    — Own Analytics: topic match from traffic-driving pins (site referrals)
    Rules — product_match and audience_match from deterministic rule tables

    Returns None for eliminated keywords.
    Adds: trend_multiplier, product_match, audience_match, maps_to_product,
          pt_pin_count, pt_ocr_best, pt_impressions, pp_boost, data_sources,
          final_score.
    """
    _td = kw_data.get("trend_direction", "stable")
    if kw_data.get("keyword", "").lower() in _TREND_OVERRIDE:
        _td = "stable"
    trend_mult = _TREND_MULT.get(_td, 0.7)
    if trend_mult == 0.0:
        return None   # eliminate falling-trend keywords

    kw_lower = kw_data["keyword"].lower()
    if kw_lower in _ELIMINATE_EXACT:
        return None
    if any(e in kw_lower for e in _ELIMINATE_SUBSTRINGS):
        return None

    # ── PT signal: fetched early so volume filter can use impressions ────────
    pin_signal = _get_pin_signal(kw_data["keyword"], pin_index) if pin_index else {}
    pp_boost   = _pp_boost(pin_signal)

    # ── Volume filter with PT impression override ─────────────────────────────
    vol     = kw_data.get("volume", 0)
    min_vol = 100 if kw_data.get("source") == "auto_research" else _MIN_VOLUME
    if vol == 0:
        if pin_signal.get("pt_impressions", 0) < 10_000:
            return None  # no KE volume, insufficient PT impressions
        # vol==0 but PT impressions ≥10,000 — passes, scored on PT signal alone
    elif vol < min_vol:
        return None

    # ── KE signal ────────────────────────────────────────────────────────────
    opp = kw_data.get("opportunity_score", 0.0)
    if opp == 0.0:
        opp = _opportunity_score(vol, kw_data.get("competition", 0))
    # PT-only opportunity: vol=0 but strong PT impressions — substitute as volume proxy.
    # 0.7 discount acknowledges PT impressions (own pins) are less certain than search volume.
    # Competition defaults to 0.25 — these are niche long-tails, typically low competition.
    if opp == 0.0 and pin_signal.get("pt_impressions", 0) >= 10_000:
        opp = round(_opportunity_score(pin_signal["pt_impressions"], 0.25) * 0.7, 1)

    # ── Rule-based product + audience signals ─────────────────────────────────
    pm, maps_to = _score_product_match(kw_data["keyword"])
    am          = _score_audience_match(kw_data["keyword"])

    # Compound keyword check: audience-only (PM=1) must have a product/solution signal
    if pm == 1:
        if not any(sig in kw_lower for sig in _COMPOUND_SIGNALS):
            return None  # standalone audience keyword — eliminated
        pm = 2           # audience + product modifier → upgrade

    if pm == 0 and am == 0:
        return None   # no product and no audience signal — eliminate

    # ── OA signal: keyword appears in a pin that drove real traffic (≥3 outbound clicks)
    oa_outbound = pin_signal.get("oa_outbound_clicks", 0)
    oa_match    = oa_outbound >= 3
    oa_boost    = 1.15 if oa_match else 1.0

    # ── KE search pin signal ──────────────────────────────────────────────────
    ke_boost = _ke_pin_boost(kw_data)

    # ── Combined score ────────────────────────────────────────────────────────
    final = opp * trend_mult * (1 + pm / 3) * (1 + am / 2) * pp_boost * oa_boost * ke_boost

    # Wix opportunity boost: uncontested category per competitor intelligence
    if maps_to == "Premade Wix Website":
        final = round(final * _WIX_BOOST, 1)

    # Source attribution
    sources = ["KE"]
    if pin_signal.get("pt_pin_count", 0) > 0:
        sources.append("PT")
    if oa_match:
        sources.append("OA")
    if kw_data.get("search_pin_count", 0) > 0:
        sources.append("KE_PINS")

    return {
        **kw_data,
        "opportunity_score":  round(opp, 1),
        "trend_multiplier":   trend_mult,
        "product_match":      pm,
        "audience_match":     am,
        "maps_to_product":    maps_to,
        "pt_pin_count":        pin_signal.get("pt_pin_count", 0),
        "pt_ocr_best":         pin_signal.get("pt_ocr_best", 0.0),
        "pt_impressions":      pin_signal.get("pt_impressions", 0),
        "oa_outbound_clicks":  oa_outbound,
        "pp_boost":           round(pp_boost, 2),
        "ke_pin_boost":       round(ke_boost, 2),
        "data_sources":       sources,
        "final_score":        round(final, 1),
    }


# ── Deduplication ─────────────────────────────────────────────────────────────

def _dedup_key(keyword: str) -> str:
    """
    Normalise to a dedup key: lowercase, strip trailing 's' from each word,
    remove common filler adjectives that don't change intent.
    'instagram templates' and 'instagram template' → same key.
    """
    fillers = {"design", "aesthetic", "ideas", "free", "canva", "modern", "minimal"}
    words = keyword.lower().strip().split()
    normed = []
    for w in words:
        w = re.sub(r"s$", "", w) if len(w) > 3 else w
        if w not in fillers:
            normed.append(w)
    return " ".join(normed).strip() or keyword.lower()


def deduplicate(scored: list[dict]) -> list[dict]:
    """
    Group keywords by dedup_key. Keep the highest-volume variant per group.
    Attach a 'merged_from' list showing what was dropped.
    """
    groups: dict[str, list[dict]] = {}
    for kw in scored:
        key = _dedup_key(kw["keyword"])
        groups.setdefault(key, []).append(kw)

    result = []
    for key, members in groups.items():
        members.sort(key=lambda k: k.get("volume", 0), reverse=True)
        winner = dict(members[0])
        dropped = [m["keyword"] for m in members[1:]]
        winner["merged_from"] = dropped
        result.append(winner)

    return result


# ── Manual CSV loading ────────────────────────────────────────────────────────

def parse_manual_csv(csv_path: Path) -> list[str]:
    """
    Extract flagged keywords from the manual CSV.
    Includes: lines starting with '- ' (primary flags) + WIX section keywords.
    Excludes: PLUS: sections, ALL CAPS headers, obvious noise.
    """
    text  = csv_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    section   = None
    in_plus   = False
    keywords: list[str] = []

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("PLUS:"):
            in_plus = True
            continue
        # Section header: all caps or a known category name
        if re.match(r"^[A-Z][A-Z ]+$", s) or s.isupper():
            section = s
            in_plus = False
            continue
        if in_plus:
            continue
        if s.startswith("- "):
            kw = s[2:].strip().lower()
            if kw:
                keywords.append(kw)
        elif section and "WIX" in section:
            # WIX section lists keywords without bullet prefix
            keywords.append(s.lower())

    # Remove duplicates, preserve order
    seen: set[str] = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique


def _fetch_ke_volumes(keywords: list[str], api_key: str) -> list[dict]:
    """Fetch Pinterest volumes + competition from Keywords Everywhere for a list of keywords."""
    results = []
    batches = [keywords[i:i + KE_BATCH] for i in range(0, len(keywords), KE_BATCH)]
    for batch in batches:
        try:
            payload = [("kw[]", k) for k in batch] + [
                ("currency", "USD"), ("datafor", "pinterest")
            ]
            resp = requests.post(
                f"{KE_BASE}/get_keyword_data",
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                data=payload,
                timeout=20,
            )
            resp.raise_for_status()
            for item in resp.json().get("data", []):
                cpc_raw = item.get("cpc", {})
                cpc  = float(cpc_raw.get("value", 0)) if isinstance(cpc_raw, dict) else float(cpc_raw or 0)
                vol  = int(item.get("vol", 0))
                comp = float(item.get("competition", 0))
                results.append({
                    "keyword":          item["keyword"],
                    "volume":           vol,
                    "cpc":              cpc,
                    "competition":      comp,
                    "trend_direction":  "stable",   # manual keywords default to stable
                    "opportunity_score": _opportunity_score(vol, comp),
                    "source":           "manual",
                    "commercial_intent": True,
                })
        except Exception as e:
            print(f"  [KE] Batch error: {e}")
        time.sleep(0.3)
    return results


# ── Pinterest API fetch for scoring step ─────────────────────────────────────

def _fetch_pt_pins(
    pt_token: str,
    fallback_pins: list[dict],
    deep: bool = False,
) -> tuple[list[dict], str, dict]:
    """
    Get Pinterest pin data for keyword cross-referencing.

    deep=False (default — used every batch run):
        Pulls top 50 pins by IMPRESSION, last 90 days.
        Merges with research file pins so no pin is lost between runs.
        Returns a minimal pin_summary dict.

    deep=True (used for master list builds and --deep-research runs):
        Pulls top 50 by IMPRESSION *and* top 50 by OUTBOUND_CLICK, deduped —
        up to ~100 unique pins. Caches pin details locally.
        Returns a full pin_summary dict with coverage metadata.

    Returns (pins, status_label, pin_summary).
    Falls back silently to research file pins when the token is absent or fails.
    """
    import sys as _sys
    _agent_dir = str(Path(__file__).parent)
    if _agent_dir not in _sys.path:
        _sys.path.insert(0, _agent_dir)

    _empty_summary: dict = {"unique_pins": 0, "converters": 0, "sort_passes": "", "date_range": "", "api_calls": 0}

    if not pt_token:
        n = sum(1 for p in fallback_pins if p.get("outbound_clicks", 0) >= 3)
        return fallback_pins, "research_fallback (no token)", {**_empty_summary, "unique_pins": len(fallback_pins), "converters": n}

    try:
        if deep:
            from analytics_loader import fetch_pins_deep  # type: ignore[attr-defined]
            cache_path = DATA_DIR / "pin-details-cache.json"
            fresh, summary = fetch_pins_deep(pt_token, n=50, cache_path=cache_path)
            if not fresh:
                n = sum(1 for p in fallback_pins if p.get("outbound_clicks", 0) >= 3)
                return fallback_pins, f"fallback ({summary.get('status')})", {**_empty_summary, "unique_pins": len(fallback_pins), "converters": n}
            merged = {p["pin_id"]: p for p in fallback_pins}
            for p in fresh:
                merged[p["pin_id"]] = p
            pins = list(merged.values())
            label = (f"deep_api ({summary['unique_pins']} pins, "
                     f"{summary['sort_passes']}, {summary['date_range']})")
            return pins, label, summary
        else:
            from analytics_loader import _fetch_top_pins  # type: ignore[attr-defined]
            fresh, status = _fetch_top_pins(pt_token, n=50)
            if status == "ok" and fresh:
                merged = {p["pin_id"]: p for p in fallback_pins}
                for p in fresh:
                    merged[p["pin_id"]] = p
                pins = list(merged.values())
                n    = sum(1 for p in pins if p.get("outbound_clicks", 0) >= 3)
                summary = {"unique_pins": len(pins), "converters": n,
                           "sort_passes": "IMPRESSION", "date_range": "last 90 days", "api_calls": 1}
                return pins, "api", summary
            n = sum(1 for p in fallback_pins if p.get("outbound_clicks", 0) >= 3)
            return fallback_pins, f"fallback ({status})", {**_empty_summary, "unique_pins": len(fallback_pins), "converters": n}
    except Exception as e:
        n = sum(1 for p in fallback_pins if p.get("outbound_clicks", 0) >= 3)
        return fallback_pins, f"fallback (error: {e})", {**_empty_summary, "unique_pins": len(fallback_pins), "converters": n}


# ── Auto-fill: research missing products automatically ────────────────────────

def _auto_fill_products(
    deduped: list[dict],
    ke_key: str,
    pin_index: dict,
) -> tuple[list[dict], list[str]]:
    """
    After scoring and deduplication, check which products still have 0 keywords.
    For each missing product, query KE for product-specific seeds, score them
    with the full three-source pipeline, and add the top 3 to the pool.

    Never asks Jane to fix this manually — runs silently and reports what was added.
    """
    present = {k.get("maps_to_product") for k in deduped}
    missing = [p for p in _PRODUCT_WEIGHT if p not in present]

    if not missing:
        return deduped, []

    all_added: list[str] = []
    existing_kws = {k["keyword"].lower() for k in deduped}

    for product in missing:
        seeds = _PRODUCT_AUTO_SEEDS.get(product, [])
        if not seeds:
            print(f"  [Auto-research] No seeds defined for '{product}' — cannot auto-fill.")
            continue

        new_seeds = [s for s in seeds if s.lower() not in existing_kws]
        print(f"\n  [Auto-research] '{product}' has 0 keywords — querying {len(new_seeds)} seeds...")

        if ke_key and new_seeds:
            new_kw_data = _fetch_ke_volumes(new_seeds, ke_key)
        else:
            if not ke_key:
                print("    KE key unavailable — using baseline scores for auto-research seeds.")
            new_kw_data = [
                {
                    "keyword":           s,
                    "volume":            500,
                    "cpc":               0.0,
                    "competition":       0.5,
                    "trend_direction":   "stable",
                    "opportunity_score": _opportunity_score(500, 0.5),
                    "source":            "auto_research",
                    "commercial_intent": True,
                }
                for s in new_seeds
            ]

        scored_new = []
        for kd in new_kw_data:
            r = _score_keyword(kd, pin_index)
            if r is not None:
                r["source"] = r.get("source", "auto_research")
                scored_new.append(r)

        if not scored_new:
            # Find the best raw volume returned to give a useful diagnosis
            best_vol = max((kd.get("volume", 0) for kd in new_kw_data), default=0)
            if best_vol < 100:
                print(
                    f"    No direct keyword universe found on Pinterest for '{product}' "
                    f"(highest seed volume: {best_vol:,}). "
                    f"Recommendation: promote via component-product keywords "
                    f"(e.g. branding kit, wix website) with copy that highlights the bundle's combined value."
                )
            else:
                print(f"    No keywords passed scoring filters — all had insufficient volume or were eliminated.")
            continue

        scored_new.sort(key=lambda k: k["final_score"], reverse=True)
        best = scored_new[:3]
        deduped.extend(best)
        newly = [b["keyword"] for b in best]
        all_added.extend(newly)
        existing_kws.update(k.lower() for k in newly)
        print(f"    Added: {newly}")

    if all_added:
        deduped.sort(key=lambda k: k["final_score"], reverse=True)

    return deduped, all_added


# ── Main scoring orchestrator ─────────────────────────────────────────────────

def score_and_rank(
    research_path: Path,
    manual_csv_path: Path | None = None,
    api_key_ke: str = "",
    pt_token: str = "",
    deep_research: bool = False,
) -> tuple[list[dict], dict]:
    """
    Three-source keyword scoring pipeline.

    Step 1  Load KE keyword universe from research JSON + manual CSV additions
    Step 2  Fetch Pinterest pins (standard 90-day/50-pin, or 12-month/400-pin if deep),
            build pin_index (PT + OA signal embedded via oa_outbound_clicks)
    Step 3  Score: KE opportunity × trend × product_match × pp_boost (PT) × oa_boost (OA)
    Step 4  Deduplicate
    Step 5  Sort by final_score
    Step 6  Auto-fill products with 0 keywords
    """
    # Step 1 — load keyword universe
    research = json.loads(research_path.read_text())
    all_kw   = list(research.get("keyword_universe", []))
    existing = {k["keyword"].lower() for k in all_kw}

    if manual_csv_path and manual_csv_path.exists() and api_key_ke:
        manual_kws = parse_manual_csv(manual_csv_path)
        new_kws    = [k for k in manual_kws if k.lower() not in existing]
        if new_kws:
            print(f"  Fetching KE volumes for {len(new_kws)} manual additions...")
            manual_data = _fetch_ke_volumes(new_kws, api_key_ke)
            all_kw.extend(manual_data)
            print(f"  Added {len(manual_data)} manual keywords.")
    elif manual_csv_path and manual_csv_path.exists():
        print("  Skipping KE fetch for manual keywords (KEYWORDS_EVERYWHERE_API_KEY not set).")

    # Step 2 — fetch Pinterest pins and build pin_index
    research_pins = research.get("top_pins", [])
    if deep_research:
        print("  PT: deep research mode — fetching 12-month pin history...")
    pins, pt_status, pin_summary = _fetch_pt_pins(pt_token, research_pins, deep=deep_research)
    converters = sum(1 for p in pins if p.get("outbound_clicks", 0) >= 3)
    if "deep_api" in pt_status:
        print(f"  PT/OA: {pt_status}")
        print(f"         {converters} traffic-driving pins (≥3 outbound clicks) available for OA signal.")
    elif "api" in pt_status:
        print(f"  PT: {len(pins)} pins (fresh 90-day API pull).")
        print(f"  OA: {converters} traffic-driving pins (≥3 outbound clicks).")
    else:
        print(f"  PT: {len(pins)} pins from research file.")
        print(f"  OA: {converters} traffic-driving pins (≥3 outbound clicks).")
    pin_index = _build_pin_index(pins)

    # Step 3 — score using all three sources: KE + PT + OA
    scored = []
    for kw in all_kw:
        result = _score_keyword(kw, pin_index)
        if result is not None:
            scored.append(result)

    eliminated = len(all_kw) - len(scored)

    # Step 4 — deduplicate
    deduped = deduplicate(scored)

    # Step 5 — sort
    deduped.sort(key=lambda k: k["final_score"], reverse=True)

    pt_hits = sum(1 for k in deduped if "PT" in k.get("data_sources", []))
    oa_hits = sum(1 for k in deduped if "OA" in k.get("data_sources", []))
    print(
        f"  {len(all_kw)} keywords → {len(scored)} after elimination "
        f"→ {len(deduped)} after dedup  |  PT: {pt_hits} hits  OA: {oa_hits} hits"
    )

    # Step 6 — auto-fill products with 0 keywords
    deduped, newly_added = _auto_fill_products(deduped, api_key_ke, pin_index)
    if newly_added:
        print(f"  Auto-research filled {len(newly_added)} keyword(s) for under-represented products.")

    return deduped, pin_summary


# ── Keywords file writer ──────────────────────────────────────────────────────

def write_keywords_file(ranked: list[dict], path: Path, top_n: int | None = None) -> Path:
    """
    Write the ranked keyword list to a plain-text file.
    Format: rank | keyword | volume | trend | maps_to_product
    """
    rows = ranked if top_n is None else ranked[:top_n]
    lines = []
    for i, k in enumerate(rows, 1):
        lines.append(
            f"{i} | {k['keyword']} | {k['volume']:,} | "
            f"{k.get('trend_direction', 'stable')} | "
            f"{k.get('maps_to_product', '')}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


# ── Scoring table display ─────────────────────────────────────────────────────

def print_scoring_table(ranked: list[dict], top_n: int = 28) -> None:
    W = 158
    print(f"\n{'─'*W}")
    print(
        f"  {'RK':>2}  {'KEYWORD':<38} {'VOL':>9}  {'OPP':>5}  {'TR':>4}"
        f"  {'PM':>2}  {'AM':>2}  {'OA_OCR':>7}  {'SAVES':>6}  {'PPB':>4}  {'KEB':>5}  {'FINAL':>7}"
        f"  {'SOURCES':<16}  MAPS TO PRODUCT"
    )
    print(
        f"  {'─'*2}  {'─'*38} {'─'*9}  {'─'*5}  {'─'*4}"
        f"  {'─'*2}  {'─'*2}  {'─'*7}  {'─'*6}  {'─'*4}  {'─'*5}  {'─'*7}"
        f"  {'─'*16}  {'─'*28}"
    )
    for i, k in enumerate(ranked[:top_n], 1):
        merged   = f"  [+{', '.join(k['merged_from'][:2])}]" if k.get("merged_from") else ""
        tr_label = {1.0: "↑ ri", 0.7: "→ st", 0.0: "↓ fa"}.get(k["trend_multiplier"], "?")

        ocr_best = k.get("pt_ocr_best", 0.0)
        oa_col   = f"{ocr_best:.2%}" if k.get("pt_pin_count", 0) > 0 else "—"

        ppb     = k.get("pp_boost", 1.0)
        ppb_col = f"{ppb:.1f}×"

        avg_saves = k.get("search_pin_avg_saves", 0)
        if avg_saves > 0:
            saves_col = f"{avg_saves:,}"
        elif k.get("search_pin_count", 0) > 0:
            saves_col = "~"      # pins found but save_count not returned
        else:
            saves_col = "—"

        ke_b    = k.get("ke_pin_boost", 1.0)
        keb_col = f"{ke_b:.2f}×"

        src      = "+".join(k.get("data_sources", ["KE"]))
        auto_tag = " [auto]" if k.get("source") == "auto_research" else ""

        print(
            f"  {i:>2}  {k['keyword']:<38} {k['volume']:>9,}  {k['opportunity_score']:>5.1f}"
            f"  {tr_label}  {k['product_match']:>2}  {k['audience_match']:>2}"
            f"  {oa_col:>7}  {saves_col:>6}  {ppb_col:>4}  {keb_col:>5}  {k['final_score']:>7.1f}"
            f"  {src:<16}  {k['maps_to_product']}{auto_tag}{merged}"
        )
    print(f"{'─'*W}\n")
    print(f"  PM = product match (0-3)   AM = audience match (0-1)")
    print(f"  TR: ↑ri ×1.0  →st ×0.7  ↓fa = eliminated")
    print(f"  OA_OCR = best outbound click rate from Pinterest pins matching this keyword (PT signal)")
    print(f"  SAVES  = avg saves on top 5 Pinterest search results for this keyword (KE_PINS signal)")
    print(f"           ~ = search pins found but save_count not returned by API (pin_count fallback used)")
    print(f"  PPB    = pp_boost: 1.4× if PT OCR ≥0.5%  |  1.2× if ≥0.1%  |  0.9× if covered+low-convert  |  1.0× no data")
    print(f"  KEB    = ke_pin_boost: 1.25× if avg saves ≥500  |  1.10× if ≥100  |  1.05× pin count fallback  |  1.0× no data")
    print(f"  SOURCES: KE = Keywords Everywhere  |  PT = Pinterest API pins  |  OA = Own Analytics (+1.15×)  |  KE_PINS = search pin saves\n")


# ── Revenue-weighted keyword selection ───────────────────────────────────────

def _select_weighted(ranked: list[dict], top_n: int) -> list[dict]:
    """
    Select top_n keywords from the ranked list using greedy revenue weighting.
    Fills product quotas first (by final_score order), then fills remaining
    spots from deferred overflow. Warns if any product is under-represented.
    """
    targets = {p: max(1, round(top_n * r)) for p, r in _PRODUCT_WEIGHT.items()}
    total = sum(targets.values())
    if total > top_n:
        max_p = max(targets, key=lambda p: targets[p])
        targets[max_p] -= 1

    counts   = {p: 0 for p in _PRODUCT_WEIGHT}
    selected: list[dict] = []
    deferred: list[dict] = []

    for kw in ranked:
        if len(selected) >= top_n:
            break
        product = kw.get("maps_to_product", "")
        if product in counts:
            if counts[product] < targets[product]:
                counts[product] += 1
                selected.append(kw)
            else:
                deferred.append(kw)
        else:
            selected.append(kw)

    for kw in deferred:
        if len(selected) >= top_n:
            break
        selected.append(kw)

    under = [
        f"{p} (target {targets[p]}, got {counts[p]})"
        for p in _PRODUCT_WEIGHT
        if counts.get(p, 0) < targets[p]
    ]
    if under:
        print("\n  WARNING — Revenue weighting shortfall. Flag to Jane before generating:")
        for msg in under:
            print(f"    Under-represented: {msg}")

    return selected[:top_n]


# ── End-of-run report CSV ─────────────────────────────────────────────────────

def _save_run_report(topics: list[dict], ranked: list[dict], path: Path) -> None:
    """
    Save data/pinterest-agent/report-[YYYY-MM-DD].csv after every --generate run.
    Columns match the spec in context/pinterest-expert.md § End-of-run report.

    previous_batch_click_rate and status are derived from the PT/OA signal already
    embedded in the scored keywords (pt_ocr_best, pt_pin_count, pt_impressions).
    """
    # Build a lookup from keyword → scored data (contains PT/OA fields)
    kd_map = {k["keyword"].lower(): k for k in ranked}

    rows = []
    for t in topics:
        kw = t.get("keyword", "")
        kd = kd_map.get(kw.lower(), {})
        n_pins  = len(t.get("variations", []))
        count   = kd.get("pt_pin_count", 0)
        ocr     = kd.get("pt_ocr_best", 0.0)
        impr    = kd.get("pt_impressions", 0)

        if count == 0:
            status   = "new"
            ocr_str  = ""
        elif ocr >= 0.005:
            status   = "increase_volume"
            ocr_str  = f"{ocr:.2%}"
        elif ocr >= 0.001:
            status   = "maintain"
            ocr_str  = f"{ocr:.2%}"
        elif impr >= 500:
            status   = "flag_title"
            ocr_str  = f"{ocr:.2%}"
        else:
            status   = "insufficient_data"
            ocr_str  = f"{ocr:.2%}" if ocr else ""

        rows.append({
            "keyword":                   kw,
            "search_volume":             kd.get("volume", 0),
            "competition_score":         round(kd.get("competition", 0.0), 2),
            "trend_direction":           kd.get("trend_direction", "stable"),
            "product_mapped":            t.get("maps_to_product", ""),
            "priority_score":            round(float(t.get("final_score") or kd.get("final_score") or 0), 1),
            "pins_generated_this_batch": n_pins,
            "previous_batch_click_rate": ocr_str,
            "status":                    status,
        })

    rows.sort(key=lambda r: r["priority_score"], reverse=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "keyword", "search_volume", "competition_score", "trend_direction",
            "product_mapped", "priority_score", "pins_generated_this_batch",
            "previous_batch_click_rate", "status",
        ])
        writer.writeheader()
        writer.writerows(rows)


# ── Batch log writer ──────────────────────────────────────────────────────────

def _save_batch_log(topics: list[dict], path: Path) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    entries = []
    for t in topics:
        for v in t.get("variations", []):
            entries.append({
                "pin_title":       v.get("pin_headline", ""),
                "keyword":         t.get("keyword", ""),
                "product_mapped":  t.get("maps_to_product", ""),
                "destination_url": v.get("destination_url", ""),
                "batch_date":      today,
            })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False))


# ── Steps 6-8: analytics + copy generation (--generate only) ─────────────────

def select_topics(ranked: list[dict], top_n: int = 27,
                  research_path: Path | None = None) -> list[dict]:
    """
    Steps 6-8:
      6. Pull own board performance + conditionally refresh competitor boards.
      7. Load Pinterest pin analytics (live API → research fallback).
      8. Apply revenue weighting, then generate 5 pin variations per keyword.
    All rules come from context/pinterest-expert.md — no hardcoding here.
    """
    from analytics_loader import load_pin_patterns
    from copy_writer import generate

    pt_token = os.getenv("PINTEREST_ACCESS_TOKEN", "")
    today    = datetime.now().strftime("%Y-%m-%d")

    # Board analysis: pull own board performance
    print("\n[Board Analysis] Pulling own board performance from Pinterest API...")
    try:
        from analytics_loader import pull_board_performance  # type: ignore[attr-defined]
        board_data = pull_board_performance(token=pt_token)
        if board_data:
            board_path = DATA_DIR / f"board-report-{today}.json"
            board_path.write_text(json.dumps(board_data, indent=2))
            print(f"  Board report saved → {board_path}")
    except (ImportError, AttributeError):
        print("  Board performance pull not available — add pull_board_performance() to analytics_loader.")

    # Competitor board refresh (every 60 days)
    refresh_path = DATA_DIR / "competitor-board-refresh.json"
    needs_refresh = True
    if refresh_path.exists():
        try:
            state = json.loads(refresh_path.read_text())
            last  = datetime.fromisoformat(state.get("last_refresh", "2000-01-01"))
            if (datetime.now() - last).days < 60:
                needs_refresh = False
                print("  Competitor board refresh not due (< 60 days since last refresh).")
        except Exception:
            pass

    if needs_refresh:
        print("  Competitor board refresh overdue — pulling data for 3 competitors...")
        try:
            from analytics_loader import pull_competitor_boards  # type: ignore[attr-defined]
            comp_data = pull_competitor_boards(
                token=pt_token,
                accounts=["designpixiestore", "macaronsmimosas", "aluncreative"],
            )
            if comp_data:
                comp_path = DATA_DIR / "competitor-intelligence-raw.json"
                comp_path.write_text(json.dumps(comp_data, indent=2))
                refresh_path.write_text(json.dumps({"last_refresh": today}))
                print(f"  Competitor board data → {comp_path}")
        except (ImportError, AttributeError):
            print("  Competitor board pull not available — add pull_competitor_boards() to analytics_loader.")

    print("\n[Step 6] Loading Pinterest pin analytics...")
    patterns = load_pin_patterns(token=pt_token, research_fallback=research_path)
    analytics_context = patterns.get("performance_context",
                                     "No pin analytics available for this run.")

    print("\n[Step 7] Applying revenue weighting to keyword selection...")
    targets = _select_weighted(ranked, top_n)

    print(f"\n[Step 8] Generating pin variations via copy_writer (expert-driven)...")
    topics = generate(targets, analytics_context, top_n=len(targets))

    # Merge authoritative pipeline scores back into topics.
    # Claude's output final_score is unreliable — overwrite with real values.
    score_lookup = {k["keyword"].lower(): k for k in targets}
    for t in topics:
        kd = score_lookup.get(t.get("keyword", "").lower(), {})
        for field in ("final_score", "product_match", "maps_to_product",
                      "pt_ocr_best", "data_sources", "source"):
            if field in kd:
                t[field] = kd[field]

    return topics


# ── Output ────────────────────────────────────────────────────────────────────

def save_topics(topics: list[dict], path: Path | None = None) -> Path:
    if path is None:
        today = datetime.now().strftime("%Y-%m-%d")
        path  = DATA_DIR / f"topics-{today}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    total_vars = sum(len(t.get("variations", [])) for t in topics)
    intent_dist: dict[str, int] = {}
    type_dist:   dict[str, int] = {}
    blog_needed = 0
    for t in topics:
        cat = t.get("commercial_intent", "?")
        intent_dist[cat] = intent_dist.get(cat, 0) + 1
        for v in t.get("variations", []):
            vt = v.get("type", "?")
            type_dist[vt] = type_dist.get(vt, 0) + 1
        if (t.get("blog") or {}).get("blog_post_needed"):
            blog_needed += 1

    output = {
        "generated_at":         datetime.now().isoformat(),
        "total_topics":         len(topics),
        "total_pin_variations": total_vars,
        "intent_distribution":  intent_dist,
        "variation_type_dist":  type_dist,
        "blog_posts_needed":    blog_needed,
        "topics":               topics,
    }
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    return path


def _print_review_table(topics: list[dict]) -> None:
    """
    Clean end-of-run checkpoint for Jane.
    Shows every generated topic so she can approve or adjust before the next batch.
    """
    total_vars = sum(len(t.get("variations", [])) for t in topics)
    type_dist: dict[str, int] = {}
    for t in topics:
        for v in t.get("variations", []):
            k = v.get("type", "?")
            type_dist[k] = type_dist.get(k, 0) + 1

    W = 96
    print(f"\n{'═'*W}")
    print(f"  BATCH REVIEW — {len(topics)} topics  |  {total_vars} pin variations  "
          f"({type_dist.get('PRODUCT', 0)} product  {type_dist.get('EDUCATIONAL', 0)} educational)")
    print(f"  Review each topic below. Adjust keywords, product mapping, or PM score before next run.")
    print(f"{'─'*W}")
    print(f"  {'#':>2}  {'KEYWORD':<40}  {'PM':>2}  {'SCORE':>7}  PRODUCT MAPPED")
    print(f"  {'─'*2}  {'─'*40}  {'─'*2}  {'─'*7}  {'─'*30}")

    prev_product = None
    for t in topics:
        product = t.get("maps_to_product", "—")
        # Print a blank separator line between product groups
        if prev_product and product != prev_product:
            print()
        prev_product = product

        n_vars  = len(t.get("variations", []))
        auto    = " [auto]" if t.get("source") == "auto_research" else ""
        n_prod  = sum(1 for v in t.get("variations", []) if v.get("type") == "PRODUCT")
        n_edu   = n_vars - n_prod
        split   = f"{n_prod}P+{n_edu}E"
        score   = t.get("final_score", t.get("score", "—"))

        print(
            f"  {t['topic_id']:>2}  {t['keyword']:<40}  {t.get('product_match', 0):>2}"
            f"  {score:>7.1f}  {product}{auto}  [{split}]"
        )

    print(f"{'─'*W}")
    # Products with zero topics
    covered = {t.get("maps_to_product") for t in topics}
    missing = [p for p in _PRODUCT_WEIGHT if p not in covered]
    if missing:
        print(f"\n  ⚠  No topics generated for: {', '.join(missing)}")
        print(f"     Promote these via component keywords with bundle-focused copy,")
        print(f"     or add product-specific seeds to manual-keywords.csv for the next run.")
    print(f"{'═'*W}\n")


# ── Master keyword list ───────────────────────────────────────────────────────

MASTER_LIST_PATH = DATA_DIR / "master-keywords.json"


def load_master_list(path: Path = MASTER_LIST_PATH) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _kw_record(k: dict, today: str, existing_rec: dict | None = None) -> dict:
    """Build a single master list keyword record from a scored keyword dict."""
    return {
        "keyword":            k["keyword"],
        "volume":             k.get("volume", 0),
        "competition":        round(k.get("competition", 0.0), 3),
        "trend_direction":    k.get("trend_direction", "stable"),
        "opportunity_score":  k.get("opportunity_score", 0.0),
        "product_match":      k.get("product_match", 0),
        "audience_match":     k.get("audience_match", 0),
        "maps_to_product":    k.get("maps_to_product", ""),
        "pt_pin_count":       k.get("pt_pin_count", 0),
        "pt_ocr_best":        k.get("pt_ocr_best", 0.0),
        "pt_impressions":     k.get("pt_impressions", 0),
        "oa_outbound_clicks": k.get("oa_outbound_clicks", 0),
        "pp_boost":             k.get("pp_boost", 1.0),
        "ke_pin_boost":         k.get("ke_pin_boost", 1.0),
        "search_pin_avg_saves": k.get("search_pin_avg_saves", 0),
        "search_pin_max_saves": k.get("search_pin_max_saves", 0),
        "search_pin_count":     k.get("search_pin_count", 0),
        "data_sources":         k.get("data_sources", ["KE"]),
        "final_score":          k.get("final_score", 0.0),
        "status":               existing_rec.get("status", "active") if existing_rec else "active",
        "added_at":           existing_rec.get("added_at", today) if existing_rec else today,
        "last_refreshed":     today,
        "batches_used":       existing_rec.get("batches_used", 0) if existing_rec else 0,
    }


def build_master_list(ranked: list[dict], pin_summary: dict,
                      path: Path = MASTER_LIST_PATH) -> dict:
    """First-time master list build. Includes every keyword that passed scoring."""
    today = datetime.now().strftime("%Y-%m-%d")
    keywords = [_kw_record(k, today) for k in ranked]
    master = {
        "schema_version": 1,
        "built_at":       today,
        "last_updated":   today,
        "pin_coverage":   {
            "pins_analyzed": pin_summary.get("unique_pins", 0),
            "converters":    pin_summary.get("converters", 0),
            "sort_passes":   pin_summary.get("sort_passes", "IMPRESSION"),
            "date_range":    pin_summary.get("date_range", ""),
            "api_calls":     pin_summary.get("api_calls", 0),
        },
        "keywords": keywords,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(master, indent=2, ensure_ascii=False))
    return master


def update_master_list(existing: dict, ranked: list[dict], pin_summary: dict,
                       path: Path = MASTER_LIST_PATH) -> tuple[dict, list[str]]:
    """
    Incremental update of the master list.

    - Re-scores every existing keyword with fresh PT/OA signals from this run.
    - Marks keywords whose trend changed to falling as status='declining'.
    - Logs score changes ≥20%.
    - Adds new high-scoring keywords not yet in the list (score > bottom 10%).
    - Caps list at 70 keywords (lowest scorers removed if cap is hit).
    - Returns (updated_master, change_log).
    """
    today   = datetime.now().strftime("%Y-%m-%d")
    fresh   = {k["keyword"].lower(): k for k in ranked}
    changes: list[str] = []

    # Refresh existing keywords
    updated: list[dict] = []
    for rec in existing["keywords"]:
        kl  = rec["keyword"].lower()
        new = fresh.get(kl)
        if new:
            old_score = rec["final_score"]
            old_trend = rec["trend_direction"]
            updated_rec = _kw_record(new, today, rec)
            # Detect declining trend
            if new.get("trend_direction") == "falling" and old_trend != "falling":
                updated_rec["status"] = "declining"
                changes.append(f"↓ declining  {rec['keyword']} (trend → falling)")
            # Detect significant score shift (≥20%)
            new_score = updated_rec["final_score"]
            if old_score > 0 and abs(new_score - old_score) / old_score >= 0.20:
                direction = "↑" if new_score > old_score else "↓"
                changes.append(f"{direction} score      {rec['keyword']}  "
                                f"{old_score:.1f} → {new_score:.1f}")
            updated.append(updated_rec)
        else:
            updated.append(rec)

    # Determine score floor: bottom 10% of current list
    scores = sorted(r["final_score"] for r in updated)
    floor  = scores[max(0, len(scores) // 10)] if scores else 0

    # Add new keywords that beat the floor and are not already present
    existing_lower = {r["keyword"].lower() for r in updated}
    for k in ranked:
        if k["keyword"].lower() in existing_lower:
            continue
        if k.get("source") == "auto_research":
            continue
        if k.get("final_score", 0) <= floor:
            continue
        updated.append(_kw_record(k, today))
        changes.append(f"+ new        {k['keyword']}  (score {k.get('final_score', 0):.1f})")

    # Audit against current elimination rules — drop any keyword that would now be eliminated.
    # This ensures rule changes propagate to the master list without manual cleanup.
    _exact_lower = {e.lower() for e in _ELIMINATE_EXACT}
    audited_out = [
        r for r in updated
        if r["keyword"].lower() in _exact_lower
        or any(e in r["keyword"].lower() for e in _ELIMINATE_SUBSTRINGS)
    ]
    if audited_out:
        updated = [r for r in updated if r not in audited_out]
        for r in audited_out:
            changes.append(f"− audited    {r['keyword']}  (now matches elimination rule)")
        print(f"  Master list audit: {len(audited_out)} keyword(s) removed (now match elimination rules).")

    # Sort and cap at 70
    updated.sort(key=lambda r: r["final_score"], reverse=True)
    if len(updated) > 70:
        removed = updated[70:]
        updated = updated[:70]
        for r in removed:
            changes.append(f"− removed    {r['keyword']}  (score {r['final_score']:.1f}, below cap)")

    master = {
        **existing,
        "last_updated": today,
        "pin_coverage": {
            "pins_analyzed": pin_summary.get("unique_pins", existing["pin_coverage"].get("pins_analyzed", 0)),
            "converters":    pin_summary.get("converters", existing["pin_coverage"].get("converters", 0)),
            "sort_passes":   pin_summary.get("sort_passes", existing["pin_coverage"].get("sort_passes", "")),
            "date_range":    pin_summary.get("date_range", existing["pin_coverage"].get("date_range", "")),
            "api_calls":     pin_summary.get("api_calls", existing["pin_coverage"].get("api_calls", 0)),
        },
        "keywords": updated,
    }
    path.write_text(json.dumps(master, indent=2, ensure_ascii=False))
    return master, changes


def print_master_list_summary(master: dict, changes: list[str], is_new: bool) -> None:
    W    = 90
    kws  = master["keywords"]
    cov  = master.get("pin_coverage", {})
    actv = sum(1 for k in kws if k.get("status") == "active")
    decl = sum(1 for k in kws if k.get("status") == "declining")

    print(f"\n{'═'*W}")
    if is_new:
        print(f"  MASTER KEYWORD LIST — BUILT {master['built_at']}")
    else:
        print(f"  MASTER KEYWORD LIST — Updated {master['last_updated']}  "
              f"(originally built {master['built_at']})")
    print(f"{'─'*W}")
    print(f"  {len(kws)} keywords  |  {actv} active  |  {decl} declining")
    print(f"  Pin coverage: {cov.get('pins_analyzed',0)} pins analysed  "
          f"| {cov.get('converters',0)} converters  "
          f"| {cov.get('sort_passes','')}  "
          f"| {cov.get('date_range','')}")

    if changes:
        print(f"\n  Changes this run ({len(changes)}):")
        for c in changes[:20]:
            print(f"    {c}")
        if len(changes) > 20:
            print(f"    … and {len(changes)-20} more (see {MASTER_LIST_PATH.name})")
    else:
        print(f"\n  No changes to master list this run.")

    print(f"\n  {'RK':<4} {'KEYWORD':<40} {'SCORE':>7}  {'SOURCES':<10}  PRODUCT")
    print(f"  {'─'*4} {'─'*40} {'─'*7}  {'─'*10}  {'─'*28}")
    for i, k in enumerate(kws[:20], 1):
        tag = " ↓" if k.get("status") == "declining" else ""
        src = "+".join(k.get("data_sources", ["KE"]))
        print(f"  {i:<4} {k['keyword']:<40} {k['final_score']:>7.1f}  {src:<10}  {k['maps_to_product']}{tag}")
    if len(kws) > 20:
        print(f"  … {len(kws)-20} more keywords in {MASTER_LIST_PATH.name}")
    print(f"{'═'*W}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(description="Pinterest topic selector — score first, generate on confirmation")
    parser.add_argument("--research",       help="Research JSON path (default: latest in data/pinterest-agent/)")
    parser.add_argument("--manual-csv",     help="Manual keywords CSV path")
    parser.add_argument("--top",            type=int, default=28, help="How many top keywords to show/use (default 28)")
    parser.add_argument("--generate",       action="store_true", help="Generate pin variations after scoring table")
    parser.add_argument("--output",         help="Output JSON path for generated topics")
    parser.add_argument("--deep-research",  action="store_true",
                        help="Pull top-100 pins by both IMPRESSION and OUTBOUND_CLICK (up to 200 unique pins) for master list build")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    ke_key   = os.getenv("KEYWORDS_EVERYWHERE_API_KEY", "")
    pt_token = os.getenv("PINTEREST_ACCESS_TOKEN", "")

    # Find research file
    if args.research:
        research_path = Path(args.research)
    else:
        files = sorted(DATA_DIR.glob("research-*.json"))
        if not files:
            print(f"No research files found in {DATA_DIR}. Run data_collector.py first.")
            sys.exit(1)
        research_path = files[-1]

    manual_path = Path(args.manual_csv) if args.manual_csv else DATA_DIR / "manual-keywords.csv"

    print(f"\nResearch: {research_path}")
    if manual_path.exists():
        print(f"Manual CSV: {manual_path}")

    deep = getattr(args, "deep_research", False)

    # Auto-trigger deep research if master list doesn't exist yet
    master_exists = MASTER_LIST_PATH.exists()
    if not master_exists and not deep:
        print("\nNo master-keywords.json found — switching to --deep-research for initial build.")
        deep = True

    if deep:
        print("\nScoring keywords (DEEP RESEARCH — dual-sort Pinterest pull)...")
    else:
        print("\nScoring keywords...")
    ranked, pin_summary = score_and_rank(
        research_path, manual_path if manual_path.exists() else None,
        ke_key, pt_token, deep_research=deep,
    )

    print_scoring_table(ranked, top_n=args.top)

    # ── Master keyword list: build on first run, update on subsequent runs ────
    existing_master = load_master_list()
    if existing_master is None:
        master = build_master_list(ranked, pin_summary)
        changes: list[str] = []
        is_new = True
    else:
        master, changes = update_master_list(existing_master, ranked, pin_summary)
        is_new = False
    print_master_list_summary(master, changes, is_new=is_new)

    if not args.generate:
        kw_path = DATA_DIR / "keywords-final.txt"
        write_keywords_file(ranked, kw_path, top_n=args.top)
        print(f"Keywords written → {kw_path}")
        sys.exit(0)

    # Use master list keywords for generation (ranked by final_score, already revenue-weighted)
    master_ranked = master["keywords"]

    print(f"\nGenerating pin variations for top {args.top} keywords...")
    topics = select_topics(master_ranked, top_n=args.top, research_path=research_path)

    out_path = save_topics(topics, Path(args.output) if args.output else None)
    print(f"\nSaved → {out_path}")

    batch_log_path = DATA_DIR / f"batch-log-{datetime.now().strftime('%Y-%m-%d')}.json"
    _save_batch_log(topics, batch_log_path)
    print(f"Batch log  → {batch_log_path}")

    report_path = DATA_DIR / f"report-{datetime.now().strftime('%Y-%m-%d')}.csv"
    _save_run_report(topics, master_ranked, report_path)
    print(f"Report     → {report_path}")

    _print_review_table(topics)
