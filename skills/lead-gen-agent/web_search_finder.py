"""
Web Search Lead Finder — discovers solo service businesses and e-commerce brands
via Google (Serper API). Targets coaches, therapists, consultants, and product
sellers who have their own websites and no Pinterest presence.

Found leads are added to the tracker. Leads where an email is found directly
in the Google snippet skip the extraction stage entirely.
"""

import os
import re
import sys
import time
import requests
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from lead_tracker import append_leads, _is_sendable_email

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# ── Service niches — searched per city ───────────────────────────────────────
# Solo practitioners and coaches who need Pinterest strategy.
# Ordered roughly by expected email/form find rate.

SERVICE_NICHES = [
    ("life coach",              "life coaching"),
    ("health coach",            "health coaching"),
    ("relationship coach",      "relationship coaching"),
    ("financial coach",         "financial coaching"),
    ("mindset coach",           "mindset coaching"),
    ("therapist",               "therapy"),
    ("business coach",          "business coaching"),
    ("nutritionist",            "nutrition coaching"),
    ("esthetician",             "esthetics"),
    ("interior designer",       "interior design"),
    ("wedding photographer",    "wedding photography"),
    ("event planner",           "event planning"),
    ("massage therapist",       "massage therapy"),
    ("personal stylist",        "personal styling"),
    ("home organizer",          "home organizing"),
]

# ── E-commerce / POD niches — no city, lower priority ────────────────────────
# Small product brands with their own websites. Different query structure —
# no city, use product-specific phrases that appear on real brand sites.
# These are skipped during extraction if Pinterest is detected on their site.

ECOMMERCE_QUERIES = [
    (
        '"handmade jewelry" "shop" "about" contact -site:etsy.com -site:amazon.com '
        '-site:folksy.com -site:notonthehighstreet.com',
        "handmade jewelry",
    ),
    (
        '"handmade skincare" OR "natural skincare" "small batch" "shop" contact '
        '-site:etsy.com -site:amazon.com',
        "handmade skincare",
    ),
    (
        '"soy candles" OR "handmade candles" "small batch" "shop" contact '
        '-site:etsy.com -site:amazon.com',
        "handmade candles",
    ),
    (
        '"handmade ceramics" OR "handmade pottery" "shop" contact '
        '-site:etsy.com -site:amazon.com',
        "ceramic pottery",
    ),
    (
        '"print on demand" "my designs" OR "my store" "shop" contact '
        '-site:redbubble.com -site:teepublic.com -site:merch.amazon.com',
        "print on demand",
    ),
    (
        '"handmade candles" "my shop" OR "our shop" contact '
        '-site:etsy.com -site:amazon.com',
        "handmade candles",
    ),
    (
        '"crystal jewelry" OR "gemstone jewelry" "handmade" "shop" contact '
        '-site:etsy.com -site:amazon.com',
        "handmade jewelry",
    ),
    (
        '"natural skincare" "small business" "shop" contact '
        '-site:etsy.com -site:amazon.com',
        "handmade skincare",
    ),
]

# ── Junk site exclusions appended to every service query ─────────────────────
# Prevents directories and booking platforms appearing in results at all,
# rather than filtering them after the fact.

_SERVICE_EXCLUDES = (
    "-site:yelp.com -site:psychologytoday.com -site:thumbtack.com "
    "-site:bark.com -site:zocdoc.com -site:healthgrades.com "
    "-site:betterhelp.com -site:theknot.com -site:weddingwire.com"
)

# US — mid-size cities
US_CITIES = [
    "Seattle", "Portland", "Denver", "Austin", "Nashville", "Charlotte",
    "San Diego", "Boston", "Miami", "Atlanta", "Minneapolis", "New Orleans",
    "Tampa", "Raleigh", "Phoenix", "Scottsdale", "Charleston", "Savannah",
    "Boulder", "Asheville", "Boise", "Salt Lake City", "Kansas City",
    "Louisville", "Indianapolis", "Columbus Ohio", "Pittsburgh", "Richmond Virginia",
    "Tucson", "Albuquerque", "Spokane", "Bozeman", "Fort Collins",
]

# US — neighbourhoods
US_NEIGHBOURHOODS = [
    "Brooklyn New York", "Santa Monica", "Silver Lake Los Angeles",
    "Lincoln Park Chicago", "Wicker Park Chicago", "West Village New York",
    "Georgetown Washington DC", "Dupont Circle Washington DC",
    "Pasadena California", "Hoboken New Jersey", "Park Slope Brooklyn",
    "Capitol Hill Seattle", "Highland Park Dallas", "South End Boston",
]

# International
INTL_CITIES = [
    "Notting Hill London", "Clapham London", "Edinburgh", "Bristol",
    "Brighton", "Manchester", "Bondi Sydney", "Newtown Sydney",
    "Fitzroy Melbourne", "St Kilda Melbourne", "Brisbane", "Perth Australia",
]


def _build_service_queries():
    queries = []
    for niche_term, niche_label in SERVICE_NICHES:
        for city in US_CITIES + US_NEIGHBOURHOODS:
            queries.append((
                f"{niche_term} in {city} {_SERVICE_EXCLUDES}",
                niche_label,
            ))
        for city in INTL_CITIES:
            queries.append((
                f"{niche_term} in {city} {_SERVICE_EXCLUDES}",
                niche_label,
            ))
    return queries


SERVICE_QUERIES = _build_service_queries()

# ── Domain blocklist ──────────────────────────────────────────────────────────

SKIP_DOMAINS = {
    "etsy.com", "amazon.com", "pinterest.com", "instagram.com", "facebook.com",
    "twitter.com", "linkedin.com", "youtube.com", "tiktok.com", "google.com",
    "bing.com", "reddit.com", "quora.com", "wikipedia.org",
    "indeed.com", "glassdoor.com", "seek.com.au",
    "yelp.com", "tripadvisor.com", "yellowpages.com", "yellowpages.com.au",
    "whitepages.com", "bbb.org", "nextdoor.com", "groupon.com",
    "angieslist.com", "angi.com", "thumbtack.com", "bark.com", "houzz.com",
    "theknot.com", "weddingwire.com", "zola.com", "partyslate.com",
    "weddingpro.com", "bridestory.com",
    "psychologytoday.com", "therapyden.com", "therapytribe.com", "zencare.co",
    "healthprofs.com", "zocdoc.com", "healthgrades.com",
    "mentalhealthmatch.com", "noomii.com", "getfyt.com", "betterhelp.com",
    "talkspace.com", "growtherapy.com", "fresha.com", "booksy.com",
    "naturaltherapypages.com.au", "aedit.com",
    "classpass.com", "mindbodyonline.com", "peerspace.com", "lessons.com",
    "blockclubchicago.org", "bostonmagazine.com", "timeout.com", "citysearch.com",
    "clubpilates.com", "ymca.org", "ymcasd.org", "ymcanyc.org", "ymcacnm.org",
    "actioncoach.com", "actioncoach.co.uk", "thriveworks.com", "lifestance.com",
    "dalecarnegie.com", "jccindy.org",
    "rusticandmain.com", "rappahannock.co", "decorilla.com", "dsasociety.org",
    "nourish.com", "brighamandwomens.org", "bmc.org", "southshorehealth.org",
    "codman.org",
    "practo.com", "counselling-directory.org.uk", "nutritionist-resource.org.uk",
    "lifecoach-directory.org.uk", "halaxy.com",
    "findyourtrainer.com", "fitnesstrainer.com", "lifetime.life", "methodpilates.com",
    "secondnature.io", "bodyrok.com",
    "axios.com", "theurbanlist.com", "goop.com", "hobokengirl.com",
    "eater.com", "visitkc.com", "clutch.co", "mapquest.com", "heytutor.com",
    "medstarhealth.org", "uwmedicine.org", "uchealth.org", "nyp.org",
    "saintalphonsus.org", "stlukesonline.org", "bristolhealth.org",
    "indymca.org", "ymcanorth.org", "tucsonjcc.org", "tucsonymca.org",
    "shalomaustin.org", "tbpm.org",
    "eventective.com", "onefinedayweddingexpo.com.au",
    # E-commerce marketplaces
    "redbubble.com", "teepublic.com", "society6.com", "zazzle.com",
    "notonthehighstreet.com", "folksy.com", "artfire.com", "storenvy.com",
    "bigcartel.com",
}

_SNIPPET_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

_CONTENT_PATH_SEGMENTS = {
    "blog", "news", "journal", "articles", "article", "press",
    "news-and-updates", "updates", "insights", "resources", "stories",
    "posts", "post", "editorial", "media",
}

_PRODUCT_PATH_SEGMENTS = {
    "shop", "collections", "products", "product", "store", "catalogue", "catalog",
}


def _normalise_url(url: str) -> str:
    """
    Strip non-homepage paths so extraction always starts from the right place:
    - Blog/article paths → homepage (the business is valid, just wrong page)
    - Product/collection paths → homepage (same reason)
    - Shopify Google Shopping tracking param (srsltid) → homepage
    """
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]

    is_content = any(part.lower() in _CONTENT_PATH_SEGMENTS for part in path_parts)
    is_product = any(part.lower() in _PRODUCT_PATH_SEGMENTS for part in path_parts)
    is_shopify_tracking = "srsltid" in parsed.query

    if is_content or is_product or is_shopify_tracking:
        return f"{parsed.scheme}://{parsed.netloc}"
    return url

# Words that appear in Google titles/snippets for institutions — not solo businesses.
# Checked against title + snippet before ever fetching the URL.
_INSTITUTIONAL_KEYWORDS = {
    # Large health/medical institutions
    "hospital", "hospitals", "rehabilitation", "rehab center", "medical center",
    "medical group", "health system", "health network", "health centre",
    # Education
    "university", "college", "department of", "school of", "faculty of",
    # Other institutions
    "institute", "institution", "foundation",
    "food bank", "food pantry",
    "ymca", "ywca", "jcc",
    "community center", "community centre",
    "nonprofit", "non-profit", "not-for-profit",
    "government", "public health",
    "church", "cathedral", "parish",
    "council", "municipality",
    # Chains and franchises
    "chain", "franchise",
    "massage envy", "massage heights", "hand and stone",
    # Multi-practitioner practices (team, not solo owner)
    "& associates", "and associates", "counseling associates",
    "therapy associates", "coaching associates",
    "group therapy", "therapy group",
    "counseling group", "counseling center", "therapy center",
    "family services", "family counseling center",
    "mental health center", "mental health services",
    "behavioral health", "behavioral services",
    "coaching firm", "coaching company", "coaching team",
    "design group", "design firm", "design studio team",
    "& partners", "and partners",
}


def _is_institutional(title: str, snippet: str) -> bool:
    """Return True if title or snippet suggests an institution, chain, or non-solo business."""
    combined = (title + " " + snippet).lower()
    return any(kw in combined for kw in _INSTITUTIONAL_KEYWORDS)


def _should_skip(url: str) -> bool:
    domain = urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if domain.endswith(".edu") or domain.endswith(".gov"):
        return True
    # Domain-level institutional signals (catches obvious cases before title check)
    _DOMAIN_SIGNALS = ("hospital", "rehab", "health-system", "medcenter", "university", "college")
    if any(sig in domain for sig in _DOMAIN_SIGNALS):
        return True
    return any(domain == s or domain.endswith("." + s) for s in SKIP_DOMAINS)


def _extract_snippet_email(text: str) -> str:
    """Return the first sendable email found in a Serper snippet, or ''."""
    for m in _SNIPPET_EMAIL_RE.finditer(text):
        email = m.group().lower()
        if _is_sendable_email(email):
            return email
    return ""


def _search(query: str, num: int = 10) -> list[dict]:
    """
    Run a Serper search and return list of {url, snippet_email} dicts.
    snippet_email is non-empty when an email is found directly in the result
    snippet — those leads skip the extraction stage entirely.
    """
    if not SERPER_API_KEY:
        print("  [Serper] SERPER_API_KEY not set", file=sys.stderr)
        return []
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": num},
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"  [Serper error] {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            return []
        results = []
        for item in resp.json().get("organic", []):
            link = item.get("link", "")
            if not link or _should_skip(link):
                continue
            title   = item.get("title") or ""
            snippet = item.get("snippet") or ""
            if _is_institutional(title, snippet):
                print(f"  [skip institutional] {title[:80]}", file=sys.stderr)
                continue
            link = _normalise_url(link)
            combined = snippet + " " + title
            results.append({
                "url": link,
                "snippet_email": _extract_snippet_email(combined),
            })
        return results
    except Exception as e:
        print(f"  [Serper error] {e}", file=sys.stderr)
        return []


def _extract_business_name(url: str) -> str:
    domain = urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    name = domain.split(".")[0]
    return name.replace("-", " ").replace("_", " ").title()


def run(service_sample=20, ecommerce_sample=5):
    import random

    # Sample from service queries (city-based) + always include all ecommerce queries
    service_queries = random.sample(SERVICE_QUERIES, min(service_sample, len(SERVICE_QUERIES)))
    ecommerce_queries = random.sample(ECOMMERCE_QUERIES, min(ecommerce_sample, len(ECOMMERCE_QUERIES)))
    all_queries = service_queries + ecommerce_queries

    leads = []
    seen_urls = set()
    snippet_email_count = 0

    for query, niche in all_queries:
        print(f"\n[Web Search] {query[:80]}", file=sys.stderr)
        results = _search(query, num=10)
        print(f"  {len(results)} URLs returned", file=sys.stderr)

        for result in results:
            url = result["url"]
            snippet_email = result["snippet_email"]

            if url in seen_urls:
                continue
            seen_urls.add(url)

            lead = {
                "source": "google",
                "owner_name": "",
                "shop_or_business_name": _extract_business_name(url),
                "website": url,
                "product_type": niche,
                "priority_score": 5,
                "notes": f"Found via web search: {niche}",
            }

            if snippet_email:
                # Email found in Google snippet — skip extraction entirely
                lead["contact_email"] = snippet_email
                lead["outreach_type"] = "email"
                lead["status"] = "qualified"
                snippet_email_count += 1
                print(f"  + {url}  [email from snippet: {snippet_email}]", file=sys.stderr)
            else:
                lead["status"] = "found"
                print(f"  + {url}", file=sys.stderr)

            leads.append(lead)

        time.sleep(1.0)

    added = append_leads(leads)
    print(f"\n[Web Search] {added} new leads added ({snippet_email_count} with email from snippet).", file=sys.stderr)
    return added


if __name__ == "__main__":
    run()
