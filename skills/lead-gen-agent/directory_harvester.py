"""
Directory Harvester — discovers solo practitioners from professional directories.

Pre-qualified leads: directory listings are vetted solo practitioners who have
invested in their own website. Form rate ~85-90% vs ~36% from general search.

Sources:
  - Psychology Today  → therapists
  - Houzz             → interior designers
  - WeddingWire       → wedding photographers + wedding planners

Strategy: scrape directory listing pages to get profile URLs, then scrape each
profile page to extract the practitioner's own website URL. Website URLs go into
the lead tracker and are picked up by the regular extractor for contact form detection.

Run standalone:
  python3 skills/lead-gen-agent/directory_harvester.py
  python3 skills/lead-gen-agent/directory_harvester.py --pages 5   # listing pages per source
"""

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urljoin

sys.path.insert(0, str(Path(__file__).parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

import apify_fetch
from lead_tracker import append_leads

STATE_PATH = Path(__file__).parent / ".directory_state.json"

# Social/platform domains — skip these when hunting for a practitioner's own website
_SOCIAL_SKIP = {
    "facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
    "youtube.com", "pinterest.com", "tiktok.com", "snapchat.com",
    "yelp.com", "google.com", "maps.google.com",
}


def _base_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _is_own_website(href: str, skip_domains: set) -> bool:
    """Return True if href looks like a practitioner's own website (not a social/platform link)."""
    if not href or not href.startswith("http"):
        return False
    domain = urlparse(href).netloc.lower().lstrip("www.")
    return not any(domain == s or domain.endswith("." + s) for s in skip_domains)


# ── Psychology Today — therapists ─────────────────────────────────────────────

PT_BASE = "https://www.psychologytoday.com"

# (state_abbr, city_slug, display_label)
# Matches the city list used in web_search_finder.py
_PT_CITIES = [
    ("wa", "seattle",        "Seattle WA"),
    ("or", "portland",       "Portland OR"),
    ("co", "denver",         "Denver CO"),
    ("tx", "austin",         "Austin TX"),
    ("tn", "nashville",      "Nashville TN"),
    ("nc", "charlotte",      "Charlotte NC"),
    ("ca", "san-diego",      "San Diego CA"),
    ("ma", "boston",         "Boston MA"),
    ("fl", "miami",          "Miami FL"),
    ("ga", "atlanta",        "Atlanta GA"),
    ("mn", "minneapolis",    "Minneapolis MN"),
    ("la", "new-orleans",    "New Orleans LA"),
    ("fl", "tampa",          "Tampa FL"),
    ("nc", "raleigh",        "Raleigh NC"),
    ("az", "phoenix",        "Phoenix AZ"),
    ("az", "scottsdale",     "Scottsdale AZ"),
    ("sc", "charleston",     "Charleston SC"),
    ("ga", "savannah",       "Savannah GA"),
    ("co", "boulder",        "Boulder CO"),
    ("id", "boise",          "Boise ID"),
    ("ut", "salt-lake-city", "Salt Lake City UT"),
    ("mo", "kansas-city",    "Kansas City MO"),
    ("ky", "louisville",     "Louisville KY"),
    ("in", "indianapolis",   "Indianapolis IN"),
    ("oh", "columbus",       "Columbus OH"),
    ("pa", "pittsburgh",     "Pittsburgh PA"),
    ("va", "richmond",       "Richmond VA"),
    ("az", "tucson",         "Tucson AZ"),
    ("nm", "albuquerque",    "Albuquerque NM"),
    ("wa", "spokane",        "Spokane WA"),
    ("ny", "brooklyn",       "Brooklyn NY"),
    ("ca", "santa-monica",   "Santa Monica CA"),
    ("ca", "pasadena",       "Pasadena CA"),
    ("tx", "dallas",         "Dallas TX"),
    ("tx", "houston",        "Houston TX"),
    ("il", "chicago",        "Chicago IL"),
    ("ny", "new-york-city",  "New York City NY"),
    ("ca", "los-angeles",    "Los Angeles CA"),
    ("ca", "san-francisco",  "San Francisco CA"),
    ("dc", "washington",     "Washington DC"),
]

# 2 pages per city (page 0 and 1), each page ~10-15 therapist cards
PT_LISTING_PAGES = [
    (f"{PT_BASE}/us/therapists/{state}/{city}?page={page}", "therapy", display)
    for state, city, display in _PT_CITIES
    for page in (0, 1)
]

_PT_SKIP = _SOCIAL_SKIP | {"psychologytoday.com"}

# Profile URL pattern: /us/therapists/{state}/{name-12345}
_PT_PROFILE_RE = re.compile(r"^/us/therapists/[a-z]{2}/[a-z0-9][a-z0-9\-]+-\d+$")


def _parse_pt_listing(html: str, listing_url: str) -> list[str]:
    """Return PT profile URLs found on a therapist listing page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0]  # strip query params
        if _PT_PROFILE_RE.match(href):
            full = PT_BASE + href
            if full not in seen:
                seen.add(full)
                urls.append(full)
    return urls


def _parse_pt_profile(html: str, profile_url: str) -> dict:
    """Extract website URL and therapist name from a PT profile page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    result = {}

    # Owner name: PT page title is "First Last, LCSW - Therapist in City | Psychology Today"
    title_tag = soup.find("title")
    if title_tag:
        m = re.match(r"^([^,|\-]+)", title_tag.get_text(strip=True))
        if m:
            result["owner_name"] = m.group(1).strip()

    # Look for "Visit Website" link in two forms:
    # 1. Direct external link with "visit website" text
    # 2. PT redirect: /us/redirect-exit?url=https://...
    website = ""

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()

        # PT redirect URL (they track outbound clicks)
        if "/redirect" in href and "url=" in href:
            qs = parse_qs(urlparse(href).query)
            if "url" in qs:
                candidate = qs["url"][0]
                if candidate.startswith("http") and _is_own_website(candidate, _PT_SKIP):
                    website = candidate
                    break

        # Direct external link with "website" in the anchor text
        if _is_own_website(href, _PT_SKIP) and "website" in text:
            website = href
            break

    # Fallback: first external link that isn't social/PT
    if not website:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if _is_own_website(href, _PT_SKIP):
                website = href
                break

    if website:
        result["website"] = _base_url(website)

    return result


# ── Houzz — interior designers ────────────────────────────────────────────────

HOUZZ_BASE = "https://www.houzz.com"

_HOUZZ_CITY_SLUGS = [
    ("Seattle--WA",          "Seattle WA"),
    ("Portland--OR",         "Portland OR"),
    ("Denver--CO",           "Denver CO"),
    ("Austin--TX",           "Austin TX"),
    ("Nashville--TN",        "Nashville TN"),
    ("Charlotte--NC",        "Charlotte NC"),
    ("San-Diego--CA",        "San Diego CA"),
    ("Boston--MA",           "Boston MA"),
    ("Miami--FL",            "Miami FL"),
    ("Atlanta--GA",          "Atlanta GA"),
    ("Minneapolis--MN",      "Minneapolis MN"),
    ("Tampa--FL",            "Tampa FL"),
    ("Phoenix--AZ",          "Phoenix AZ"),
    ("Scottsdale--AZ",       "Scottsdale AZ"),
    ("Boulder--CO",          "Boulder CO"),
    ("Salt-Lake-City--UT",   "Salt Lake City UT"),
    ("Kansas-City--MO",      "Kansas City MO"),
    ("Indianapolis--IN",     "Indianapolis IN"),
    ("Columbus--OH",         "Columbus OH"),
    ("Pittsburgh--PA",       "Pittsburgh PA"),
    ("Tucson--AZ",           "Tucson AZ"),
    ("Dallas--TX",           "Dallas TX"),
    ("Houston--TX",          "Houston TX"),
    ("Chicago--IL",          "Chicago IL"),
    ("New-York--NY",         "New York NY"),
    ("Los-Angeles--CA",      "Los Angeles CA"),
    ("San-Francisco--CA",    "San Francisco CA"),
    ("Washington--DC",       "Washington DC"),
]

HOUZZ_LISTING_PAGES = [
    (
        f"{HOUZZ_BASE}/professionals/interior-designer/c/{slug}/",
        "interior design",
        display,
    )
    for slug, display in _HOUZZ_CITY_SLUGS
]

_HOUZZ_SKIP = _SOCIAL_SKIP | {"houzz.com"}

# Houzz pro profile paths: /pro/{username} or /professionals/{category}/{name}
_HOUZZ_PRO_RE = re.compile(r"^/(pro/[^/?#]+|professionals/[^/?#]+/[^/?#]+)/?$")


def _parse_houzz_listing(html: str, listing_url: str) -> list[str]:
    """Return Houzz pro profile URLs from a listing page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    urls = []

    for a in soup.find_all("a", href=True):
        href = a["href"].rstrip("/")
        # Relative path
        if _HOUZZ_PRO_RE.match(href):
            full = HOUZZ_BASE + href
            if full not in seen and "search" not in full:
                seen.add(full)
                urls.append(full)
        # Already absolute
        elif "houzz.com/pro/" in href or "houzz.com/professionals/" in href:
            clean = href.split("?")[0]
            if clean not in seen:
                seen.add(clean)
                urls.append(clean)

    return urls[:25]


def _parse_houzz_profile(html: str, profile_url: str) -> dict:
    """Extract website URL and business name from a Houzz professional profile."""
    from bs4 import BeautifulSoup
    import json as _json
    soup = BeautifulSoup(html, "html.parser")
    result = {}

    # Houzz uses JSON-LD structured data — most reliable source
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
            # Handle both single object and list
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = item.get("url", "")
                if url and "houzz.com" not in url and url.startswith("http"):
                    result["website"] = _base_url(url)
                name = item.get("name", "")
                if name and not result.get("shop_or_business_name"):
                    result["shop_or_business_name"] = name
        except Exception:
            pass

    if result.get("website"):
        return result

    # Fallback: look for "Website" anchor text pointing to an external domain
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if _is_own_website(href, _HOUZZ_SKIP) and "website" in text:
            result["website"] = _base_url(href)
            break

    # Business name from page title: "Business Name | Interior Designers | Houzz"
    if not result.get("shop_or_business_name"):
        title_tag = soup.find("title")
        if title_tag:
            m = re.match(r"^([^|]+)", title_tag.get_text(strip=True))
            if m:
                result["shop_or_business_name"] = m.group(1).strip()

    return result


# ── WeddingWire — wedding photographers + planners ────────────────────────────

WW_BASE = "https://www.weddingwire.com"

_WW_PHOTO_CITIES = [
    "seattle", "portland", "denver", "austin", "nashville", "charlotte",
    "san-diego", "boston", "miami", "atlanta", "minneapolis", "tampa",
    "phoenix", "scottsdale", "dallas", "houston", "chicago",
    "new-york", "los-angeles", "san-francisco",
]

_WW_PLANNER_CITIES = [
    "seattle", "portland", "denver", "austin", "nashville", "boston",
    "miami", "atlanta", "dallas", "chicago", "new-york", "los-angeles",
]

_WW_DISPLAY = {
    "seattle": "Seattle WA", "portland": "Portland OR", "denver": "Denver CO",
    "austin": "Austin TX", "nashville": "Nashville TN", "charlotte": "Charlotte NC",
    "san-diego": "San Diego CA", "boston": "Boston MA", "miami": "Miami FL",
    "atlanta": "Atlanta GA", "minneapolis": "Minneapolis MN", "tampa": "Tampa FL",
    "phoenix": "Phoenix AZ", "scottsdale": "Scottsdale AZ", "dallas": "Dallas TX",
    "houston": "Houston TX", "chicago": "Chicago IL", "new-york": "New York NY",
    "los-angeles": "Los Angeles CA", "san-francisco": "San Francisco CA",
}

WW_LISTING_PAGES = [
    (
        f"{WW_BASE}/wedding-photographers/{city}--c_220003/",
        "wedding photography",
        _WW_DISPLAY.get(city, city),
    )
    for city in _WW_PHOTO_CITIES
] + [
    (
        f"{WW_BASE}/wedding-planning/{city}--c_220000/",
        "event planning",
        _WW_DISPLAY.get(city, city),
    )
    for city in _WW_PLANNER_CITIES
]

# ── Noomii — life / business / health / relationship coaches ──────────────────

NOOMII_BASE = "https://www.noomii.com"

_NOOMII_SKIP = _SOCIAL_SKIP | {"noomii.com"}

# Noomii specialties that map to our coach niches
_NOOMII_SPECIALTIES = [
    ("life-coaches",         "life coaching"),
    ("business-coaches",     "business coaching"),
    ("health-coaches",       "health coaching"),
    ("relationship-coaches", "relationship coaching"),
]

_NOOMII_CITIES = [
    ("seattle-washington",     "Seattle WA"),
    ("portland-oregon",        "Portland OR"),
    ("denver-colorado",        "Denver CO"),
    ("austin-texas",           "Austin TX"),
    ("nashville-tennessee",    "Nashville TN"),
    ("charlotte-north-carolina", "Charlotte NC"),
    ("boston-massachusetts",   "Boston MA"),
    ("miami-florida",          "Miami FL"),
    ("atlanta-georgia",        "Atlanta GA"),
    ("minneapolis-minnesota",  "Minneapolis MN"),
    ("phoenix-arizona",        "Phoenix AZ"),
    ("dallas-texas",           "Dallas TX"),
    ("houston-texas",          "Houston TX"),
    ("chicago-illinois",       "Chicago IL"),
    ("new-york-new-york",      "New York NY"),
    ("los-angeles-california", "Los Angeles CA"),
    ("san-francisco-california", "San Francisco CA"),
    ("washington-district-of-columbia", "Washington DC"),
]

NOOMII_LISTING_PAGES = [
    (f"{NOOMII_BASE}/list/{specialty}/{city}", niche, display)
    for specialty, niche in _NOOMII_SPECIALTIES
    for city, display in _NOOMII_CITIES
]

# Noomii coach profile path: /coaches/{id}/{slug} or /list/{specialty}/{city}/{slug}
_NOOMII_PROFILE_RE = re.compile(r"^/coaches/\d+/[^/?#]+/?$")


def _parse_noomii_listing(html: str, listing_url: str) -> list[str]:
    """Return Noomii coach profile URLs from a listing page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    urls = []

    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0].rstrip("/")
        if _NOOMII_PROFILE_RE.match(href):
            full = NOOMII_BASE + href
            if full not in seen:
                seen.add(full)
                urls.append(full)
        elif "noomii.com/coaches/" in href:
            clean = href.split("?")[0]
            if clean not in seen:
                seen.add(clean)
                urls.append(clean)

    return urls[:25]


def _parse_noomii_profile(html: str, profile_url: str) -> dict:
    """Extract website URL and coach name from a Noomii profile page."""
    from bs4 import BeautifulSoup
    import json as _json
    soup = BeautifulSoup(html, "html.parser")
    result = {}

    # JSON-LD first
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = item.get("url", "")
                if url and "noomii.com" not in url and url.startswith("http"):
                    result["website"] = _base_url(url)
                if item.get("name") and not result.get("owner_name"):
                    result["owner_name"] = item["name"]
        except Exception:
            pass

    if result.get("website"):
        return result

    # Look for "Visit Website" or "Website" external link
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if _is_own_website(href, _NOOMII_SKIP) and any(kw in text for kw in ("website", "visit", "my site")):
            result["website"] = _base_url(href)
            break

    # Coach name from page title: "John Smith - Life Coach | Noomii"
    if not result.get("owner_name"):
        title_tag = soup.find("title")
        if title_tag:
            m = re.match(r"^([^|,\-]+)", title_tag.get_text(strip=True))
            if m:
                result["owner_name"] = m.group(1).strip()

    return result


_WW_SKIP = _SOCIAL_SKIP | {"weddingwire.com", "theknot.com"}

# WeddingWire vendor storefront path: /biz/{slug}
_WW_BIZ_RE = re.compile(r"^/biz/[^/?#]+/?$")


def _parse_ww_listing(html: str, listing_url: str) -> list[str]:
    """Return WeddingWire vendor profile URLs from a listing page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    urls = []

    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0]
        if _WW_BIZ_RE.match(href):
            full = WW_BASE + href
            if full not in seen:
                seen.add(full)
                urls.append(full)
        elif "weddingwire.com/biz/" in href:
            clean = href.split("?")[0]
            if clean not in seen:
                seen.add(clean)
                urls.append(clean)

    return urls[:25]


def _parse_ww_profile(html: str, profile_url: str) -> dict:
    """Extract website URL and business name from a WeddingWire vendor profile."""
    from bs4 import BeautifulSoup
    import json as _json
    soup = BeautifulSoup(html, "html.parser")
    result = {}

    # JSON-LD first
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = item.get("url", "")
                if url and "weddingwire.com" not in url and url.startswith("http"):
                    result["website"] = _base_url(url)
                name = item.get("name", "")
                if name and not result.get("shop_or_business_name"):
                    result["shop_or_business_name"] = name
        except Exception:
            pass

    if result.get("website"):
        return result

    # Fallback: external link with "website" in text
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if _is_own_website(href, _WW_SKIP) and "website" in text:
            result["website"] = _base_url(href)
            break

    return result


# ── State management ──────────────────────────────────────────────────────────

def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _get_next_pages(
    state: dict,
    key: str,
    all_pages: list[tuple],
    n: int,
) -> list[tuple]:
    """Return the next n unprocessed (url, niche, display) tuples, rotating when exhausted."""
    processed = set(state.get(key, {}).get("processed", []))
    queue = [p for p in all_pages if p[0] not in processed]
    if not queue:
        # Full cycle done — reset and start over
        state.setdefault(key, {})["processed"] = []
        queue = list(all_pages)
    return queue[:n]


def _mark_processed(state: dict, key: str, urls: list[str]):
    state.setdefault(key, {}).setdefault("processed", [])
    state[key]["processed"].extend(urls)


# ── Core scraper ──────────────────────────────────────────────────────────────

def _scrape_source(
    listing_pages: list[tuple],   # (url, niche_label, display_label)
    parse_listing_fn,
    parse_profile_fn,
    source_name: str,
    source_key: str,
    pages_this_run: int,
    profile_delay: float = 1.5,
    listing_delay: float = 2.0,
) -> int:
    """Generic two-hop directory scraper. Returns count of new leads added."""
    state = _load_state()
    pages_to_run = _get_next_pages(state, source_key, listing_pages, pages_this_run)

    if not pages_to_run:
        print(f"[{source_name}] No pages queued.", file=sys.stderr)
        return 0

    total_added = 0
    processed_listing_urls = []

    for listing_url, niche_label, display in pages_to_run:
        print(f"\n[{source_name}] {display} — {listing_url}", file=sys.stderr)

        html = apify_fetch.fetch(listing_url, timeout=30)
        if not html or html == "BLOCKED":
            print(f"  → blocked/failed, skipping", file=sys.stderr)
            processed_listing_urls.append(listing_url)
            time.sleep(listing_delay)
            continue

        profile_urls = parse_listing_fn(html, listing_url)
        print(f"  → {len(profile_urls)} profiles found", file=sys.stderr)

        if not profile_urls:
            processed_listing_urls.append(listing_url)
            time.sleep(listing_delay)
            continue

        new_leads = []
        for profile_url in profile_urls:
            time.sleep(profile_delay)
            p_html = apify_fetch.fetch(profile_url, timeout=30)
            if not p_html or p_html == "BLOCKED":
                continue

            info = parse_profile_fn(p_html, profile_url)
            website = info.get("website", "").strip()
            if not website or len(website) < 10:
                continue

            new_leads.append({
                "source": "directory",
                "website": website,
                "product_type": niche_label,
                "shop_or_business_name": info.get("shop_or_business_name", ""),
                "owner_name": info.get("owner_name", ""),
                "notes": f"via {source_name}: {display}",
            })
            print(f"    → {website}", file=sys.stderr)

        if new_leads:
            added = append_leads(new_leads)
            total_added += added
            print(
                f"  → {added}/{len(new_leads)} new leads added "
                f"({len(new_leads) - added} duplicates skipped)",
                file=sys.stderr,
            )

        processed_listing_urls.append(listing_url)
        time.sleep(listing_delay)

    _mark_processed(state, source_key, processed_listing_urls)
    _save_state(state)

    return total_added


# ── Public API ────────────────────────────────────────────────────────────────

def run(pages_per_source: int = 3) -> int:
    """
    Scrape all configured directory sources and add leads to the tracker.

    pages_per_source: listing pages to process per source per run (default 3).
    3 pages × ~15 profiles × 3 sources = ~135 new website URLs per run.
    After extraction, expect ~85-90% to have contact forms = ~115-120 form leads.

    Note on e-commerce/POD niches: no curated directories exist for these niches.
    They benefit from the intitle:"contact" search mode in web_search_finder.py instead.
    """
    print("\n[Directory Harvester] Starting", file=sys.stderr)
    totals = {}

    totals["pt"] = _scrape_source(
        listing_pages=PT_LISTING_PAGES,
        parse_listing_fn=_parse_pt_listing,
        parse_profile_fn=_parse_pt_profile,
        source_name="Psychology Today",
        source_key="pt_therapists",
        pages_this_run=pages_per_source,
    )

    totals["houzz"] = _scrape_source(
        listing_pages=HOUZZ_LISTING_PAGES,
        parse_listing_fn=_parse_houzz_listing,
        parse_profile_fn=_parse_houzz_profile,
        source_name="Houzz",
        source_key="houzz_interior",
        pages_this_run=pages_per_source,
    )

    totals["ww"] = _scrape_source(
        listing_pages=WW_LISTING_PAGES,
        parse_listing_fn=_parse_ww_listing,
        parse_profile_fn=_parse_ww_profile,
        source_name="WeddingWire",
        source_key="ww_vendors",
        pages_this_run=pages_per_source,
    )

    totals["noomii"] = _scrape_source(
        listing_pages=NOOMII_LISTING_PAGES,
        parse_listing_fn=_parse_noomii_listing,
        parse_profile_fn=_parse_noomii_profile,
        source_name="Noomii",
        source_key="noomii_coaches",
        pages_this_run=pages_per_source,
    )

    grand_total = sum(totals.values())
    print(
        f"\n[Directory Harvester] Done — "
        f"PT: {totals['pt']}, Houzz: {totals['houzz']}, "
        f"WW: {totals['ww']}, Noomii: {totals['noomii']} "
        f"| Total: {grand_total} new leads",
        file=sys.stderr,
    )
    return grand_total


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scrape professional directories for solo practitioner leads.")
    parser.add_argument(
        "--pages", type=int, default=3,
        help="Listing pages per source per run (default: 3 → ~135 website URLs)",
    )
    args = parser.parse_args()
    run(pages_per_source=args.pages)
