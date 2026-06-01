"""
Etsy Lead Finder — discovers physical/handmade product sellers on Etsy.

Two-phase approach:
  Phase 1: Apify marketplace Etsy scraper (DpTUzMvbQpfdogIyK) searches by
           keyword and returns listings with shop names. Digital downloads filtered out.
  Phase 2: ValueSERP (Google) searches for each shop to extract Instagram handle,
           website URL, sales count, and location from Google snippets.
"""

import os
import re
import sys
import time
import requests
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from lead_tracker import append_leads

APIFY_API_KEY   = os.getenv("APIFY_API_KEY")
SERPER_API_KEY  = os.getenv("SERPER_API_KEY")
APIFY_BASE      = "https://api.apify.com/v2"

# Apify marketplace actor — handles Etsy's CloudFlare protection
ETSY_ACTOR_ID = "DpTUzMvbQpfdogIyK"

# ── Keywords to search ────────────────────────────────────────────────────────

KEYWORDS = [
    # Gifts & personalised (POD-friendly)
    "personalized gifts",
    "custom gifts",
    "custom tumblers",
    "personalized ornaments",
    "wedding favors handmade",
    # Home & lifestyle
    "handmade candles",
    "ceramic pottery",
    "home decor handmade",
    "handmade skincare",
    # Art & paper goods
    "original art prints",
    "greeting cards handmade",
    # Events & occasions
    "wedding decor handmade",
    "baby shower gifts",
    # Custom / POD products
    "custom pet portrait",
    "custom tote bags",
]

# ── Target country signals (US, UK, Australia, Germany) ──────────────────────

_TARGET_TOKENS = {
    # United States
    "Alabama","Alaska","Arizona","Arkansas","California","Colorado","Connecticut",
    "Delaware","Florida","Georgia","Hawaii","Idaho","Illinois","Indiana","Iowa",
    "Kansas","Kentucky","Louisiana","Maine","Maryland","Massachusetts","Michigan",
    "Minnesota","Mississippi","Missouri","Montana","Nebraska","Nevada",
    "New Hampshire","New Jersey","New Mexico","New York","North Carolina",
    "North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania","Rhode Island",
    "South Carolina","South Dakota","Tennessee","Texas","Utah","Vermont",
    "Virginia","Washington","West Virginia","Wisconsin","Wyoming",
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
    "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN",
    "TX","UT","VT","VA","WA","WV","WI","WY",
    "United States","USA","US",
    # United Kingdom
    "United Kingdom","UK","England","Scotland","Wales","Northern Ireland",
    "London","Manchester","Birmingham","Edinburgh","Glasgow","Bristol",
    # Australia
    "Australia","NSW","VIC","QLD","WA","SA","TAS","ACT","NT",
    "New South Wales","Victoria","Queensland","Western Australia",
    "South Australia","Tasmania","Sydney","Melbourne","Brisbane","Perth",
    # Germany
    "Germany","Deutschland","Berlin","Munich","Hamburg","Frankfurt",
    "Cologne","Stuttgart","Düsseldorf",
}

# Phrases that indicate non-target countries — skip if found
_EXCLUDED_PHRASES = {
    "vietnam","viet nam","china","hong kong","taiwan","indonesia","malaysia",
    "philippines","thailand","india","pakistan","bangladesh","sri lanka",
    "singapore","japan","south korea","korea","israel","russia","ukraine",
    "poland","romania","hungary","czech","slovakia","turkey","iran","egypt",
    "mexico","brazil","argentina","colombia","peru","chile","south africa",
    "nigeria","kenya","ghana","indonesia",
}

def _is_target_country(text):
    text_lower = text.lower()
    # Reject if clearly a non-target country
    for phrase in _EXCLUDED_PHRASES:
        if phrase in text_lower:
            return False
    # Accept if a target location token is found
    for token in _TARGET_TOKENS:
        if re.search(rf"\b{re.escape(token)}\b", text, re.I):
            return True
    return False


# ── Apify actor runner ────────────────────────────────────────────────────────

def _run_actor(actor_id, input_data, timeout_secs=300):
    """Start an Apify actor, wait for completion, return dataset items."""
    if not APIFY_API_KEY:
        print("[warn] APIFY_API_KEY not set", file=sys.stderr)
        return []

    token = {"token": APIFY_API_KEY}

    resp = requests.post(
        f"{APIFY_BASE}/acts/{actor_id}/runs",
        params=token, json=input_data, timeout=30,
    )
    if resp.status_code not in (200, 201):
        print(f"  [actor error] {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        return []

    run_id = resp.json().get("data", {}).get("id")
    print(f"  Actor run started: {run_id}", file=sys.stderr)

    deadline = time.time() + timeout_secs
    dataset_id = None
    while time.time() < deadline:
        s = requests.get(f"{APIFY_BASE}/actor-runs/{run_id}", params=token, timeout=15)
        data   = s.json().get("data", {})
        status = data.get("status", "")
        if status == "SUCCEEDED":
            dataset_id = data.get("defaultDatasetId")
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            print(f"  [actor] Run ended: {status}", file=sys.stderr)
            return []
        time.sleep(10)
    else:
        print(f"  [actor] Timed out after {timeout_secs}s", file=sys.stderr)
        return []

    if not dataset_id:
        return []

    items = requests.get(
        f"{APIFY_BASE}/datasets/{dataset_id}/items",
        params={**token, "format": "json", "clean": "true"},
        timeout=30,
    )
    return items.json() if items.status_code == 200 else []


# ── Phase 1: Search Etsy by keyword via marketplace actor ─────────────────────

def _search_etsy_by_keyword(keyword, max_items=20):
    """
    Use the Apify marketplace Etsy scraper to search by keyword.
    Returns list of shop names found (physical products only).
    """
    items = _run_actor(
        ETSY_ACTOR_ID,
        {
            "searchQuery": keyword,
            "maxItems": max_items,
        },
        timeout_secs=120,
    )

    shops = {}
    for item in items:
        # Skip digital downloads
        if item.get("isDigitalDownload"):
            continue
        shop = item.get("shop", "")
        if not shop:
            continue
        price = item.get("price", "")
        if shop not in shops:
            shops[shop] = {
                "shopName": shop,
                "shopId":   item.get("shopId", ""),
                "prices":   [price] if price else [],
                "currency": item.get("currency", ""),
            }
        elif price:
            shops[shop]["prices"].append(price)

    return shops


# ── Phase 2: ValueSERP Google enrichment for each shop ───────────────────────

def _valueserp(query, num=3):
    if not SERPER_API_KEY:
        return []
    try:
        r = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": num},
            timeout=20,
        )
        if r.status_code != 200:
            return []
        # Normalise to match expected format: list of {title, snippet, link}
        return [
            {"title": i.get("title", ""), "snippet": i.get("snippet", ""), "link": i.get("link", "")}
            for i in r.json().get("organic", [])
        ]
    except Exception:
        return []


_IG_RE      = re.compile(r"instagram\.com/([a-zA-Z0-9_.]+)", re.I)
_SALES_RE   = re.compile(r"([\d,]+(?:\.\d+)?[KkMm]?)\s+(?:sales?|Sales?)", re.I)
_SHIPS_RE   = re.compile(r"(?:Ships from|Located in|Location)[:\s]+([^\n|·–]{2,50})", re.I)
_YEAR_RE    = re.compile(r"(?:Member since|On Etsy since|[Ss]hop opened?|Joined)[:\s]+(\d{4})", re.I)
_MEMBERS_RE = re.compile(r"(\d+)\s+[Mm]embers?", re.I)

# Domains that are NOT a business website
_SKIP_WEBSITE = {
    "etsy.com", "instagram.com", "facebook.com", "pinterest.com", "twitter.com",
    "tiktok.com", "youtube.com", "google.com", "bing.com", "linkedin.com",
    "linktr.ee", "benable.com", "threads.net", "snapchat.com", "bio.site",
    "beacons.ai", "amazon.com", "reddit.com", "tumblr.com", "apple.com",
    # Analytics, review, and directory platforms — not the shop's own site
    "judge.me", "trustpilot.com", "reviews.io", "koalanda.pro", "everbee.io",
    "alura.io", "marmalead.com", "etsyrank.com", "craftcount.com",
    "theknot.com", "weddingwire.com", "thumbtack.com", "yelp.com",
    "houzz.com", "bark.com", "angi.com", "angieslist.com",
}

def _is_business_url(url):
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower().lstrip("www.")
    return not any(domain == s or domain.endswith("." + s) for s in _SKIP_WEBSITE)


def _enrich_shop(shop_name, keyword):
    """
    Search Google for the shop to extract: instagram, website, sales, location.
    Returns a dict of enrichment fields.
    """
    results = _valueserp(f'"{shop_name}" etsy shop', num=5)

    instagram = ""
    website   = ""
    sales     = 0
    location  = ""
    shop_year = 0
    team_size = 0

    for r in results:
        text = " ".join([r.get("title", ""), r.get("snippet", ""), r.get("link", "")])

        # Instagram from any field
        if not instagram:
            m = _IG_RE.search(text)
            if m and m.group(1).lower() not in ("p", "explore", "reel", "reels", "stories"):
                instagram = "@" + m.group(1)

        # Sales count — handles "1,234 sales" and "20K sales"
        if not sales:
            m = _SALES_RE.search(text)
            if m:
                raw = m.group(1).replace(",", "")
                if raw.lower().endswith("k"):
                    sales = int(float(raw[:-1]) * 1000)
                elif raw.lower().endswith("m"):
                    sales = int(float(raw[:-1]) * 1_000_000)
                else:
                    sales = int(float(raw))

        # Location
        if not location:
            m = _SHIPS_RE.search(text)
            if m:
                location = m.group(1).strip()

        # Shop opening year — e.g. "Member since 2018"
        if not shop_year:
            m = _YEAR_RE.search(text)
            if m:
                shop_year = int(m.group(1))

        # Team member count — e.g. "4 Members"
        if not team_size:
            m = _MEMBERS_RE.search(text)
            if m:
                team_size = int(m.group(1))

        # Business website — prefer non-Etsy result links
        if not website:
            link = r.get("link", "")
            if link and _is_business_url(link):
                website = link

    return {
        "instagram": instagram,
        "website":   website,
        "sales":     sales,
        "location":  location,
        "shop_year":  shop_year,
        "team_size":  team_size,
    }


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_lead(instagram, website, pinterest_present, sales):
    score = 0
    if website:         score += 3
    if instagram:       score += 2
    if not pinterest_present: score += 5
    if 200 <= sales <= 2000:  score += 5
    elif 50 <= sales < 200:   score += 3
    elif 2000 < sales <= 5000: score += 2
    return score


# ── Main entry point ──────────────────────────────────────────────────────────

def run(keywords=None, max_per_keyword=20, sales_min=50, sales_max=15000,
        max_shop_age_years=7, max_team_size=3):
    import datetime
    kws = keywords or KEYWORDS
    cutoff_year = datetime.date.today().year - max_shop_age_years  # e.g. 2019

    all_shops   = {}   # shop_name → {shopName, keyword, ...}
    kw_counts   = {}

    for kw in kws:
        print(f"\n  Searching Etsy for: '{kw}'", file=sys.stderr)
        shops = _search_etsy_by_keyword(kw, max_items=max(max_per_keyword * 3, 30))
        print(f"  Found {len(shops)} shops", file=sys.stderr)

        for name, info in shops.items():
            if name in all_shops:
                continue
            count = kw_counts.get(kw, 0)
            if count >= max_per_keyword:
                continue
            all_shops[name] = {**info, "keyword": kw}
            kw_counts[kw] = count + 1

        time.sleep(3.0)  # avoid Apify rate limiting between actor runs

    print(f"\n  Phase 1 complete: {len(all_shops)} unique shops", file=sys.stderr)

    if not all_shops:
        print("[Etsy] No shops found.", file=sys.stderr)
        return 0

    # Phase 2: enrich each shop via Google
    leads = []
    for name, info in all_shops.items():
        # Price filter — skip shops where all sampled listings are under $20
        raw_prices = info.get("prices", [])
        if raw_prices:
            parsed_prices = []
            for p in raw_prices:
                try:
                    parsed_prices.append(float(str(p).replace(",", "").strip()))
                except (ValueError, TypeError):
                    pass
            if parsed_prices and all(p < 20.0 for p in parsed_prices):
                print(f"    Skip {name} — all sampled prices < $20 (max: ${max(parsed_prices):.2f})", file=sys.stderr)
                continue

        print(f"  Enriching: {name}", file=sys.stderr)
        enriched = _enrich_shop(name, info["keyword"])

        sales     = enriched["sales"]
        location  = enriched["location"]
        shop_year = enriched.get("shop_year", 0)
        team_size = enriched.get("team_size", 0)

        # Sales filter (only applies if we have a sales count)
        if sales and not (sales_min <= sales <= sales_max):
            print(f"    Skip {name} — {sales:,} sales out of range", file=sys.stderr)
            continue

        # Country filter — reject known non-target locations
        if location and not _is_target_country(location):
            print(f"    Skip {name} — outside target countries: {location}", file=sys.stderr)
            continue

        # Shop age filter — skip shops opened more than max_shop_age_years ago
        if shop_year and shop_year < cutoff_year:
            print(f"    Skip {name} — opened {shop_year} (>{max_shop_age_years} years old)", file=sys.stderr)
            continue

        # Team size filter — skip shops with too many team members
        if team_size and team_size > max_team_size:
            print(f"    Skip {name} — {team_size} team members (too large)", file=sys.stderr)
            continue

        instagram = enriched["instagram"]
        website   = enriched["website"]
        score     = _score_lead(instagram, website, False, sales)

        notes_parts = []
        if info.get("prices"):
            notes_parts.append(f"Price: {info.get('currency','')}{info['prices'][0]}")
        if shop_year:
            notes_parts.append(f"Opened: {shop_year}")
        if team_size:
            notes_parts.append(f"Team: {team_size}")

        lead = {
            "source":                "etsy",
            "shop_or_business_name": name,
            "etsy_url":              f"https://www.etsy.com/shop/{name}",
            "website":               website,
            "instagram_handle":      instagram,
            "product_type":          info["keyword"],
            "sales_count":           sales,
            "priority_score":        score,
            "status":                "found",
            "notes":                 " | ".join(notes_parts),
        }
        leads.append(lead)
        print(f"    + {name} (sales={sales:,}, year={shop_year or '?'}, team={team_size or '?'}, score={score})", file=sys.stderr)
        time.sleep(0.5)

    added = append_leads(leads)
    print(f"\n[Etsy] {added} new leads added to tracker.", file=sys.stderr)
    return added


if __name__ == "__main__":
    run()
