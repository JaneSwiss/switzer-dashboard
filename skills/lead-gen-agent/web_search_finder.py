"""
Web Search Lead Finder — discovers solo service businesses and e-commerce brands
via Google (Serper API). Targets coaches, therapists, consultants, and product
sellers who have their own websites and no Pinterest presence.

Found leads are added to the tracker. Leads where an email is found directly
in the Google snippet skip the extraction stage entirely.
"""

import json
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

# ── Directory URL path segments ────────────────────────────────────────────────
# These path segments almost never appear on a solo business's own site.
# Checked as EXACT path-segment matches (split on "/") to avoid false positives
# like "/therapists-guide-to-xyz".

_DIRECTORY_PATH_SEGMENTS = {
    "directory", "listings", "listing",
    "providers", "provider",
    "profiles",
    "search-results", "results",
    "therapists", "coaches", "counselors", "practitioners",
    "nutritionists", "estheticians", "photographers", "stylists",
    "organizers", "planners",
}

# ── Listicle / aggregator title phrases ────────────────────────────────────────
# Titles containing these phrases are roundup articles or directory pages,
# not solo business websites.

_LISTICLE_TITLE_PHRASES = {
    "near me", "near you", "in your area",
    "find a ", "find the best", "find your",
    " directory", " listings",
    "top rated", "top-rated",
    "top 10", "top 5", "top 15", "top 20", "top 25", "top 7", "top 3",
    "best rated", "best-rated",
    "therapists in ", "coaches in ", "counselors in ",
    "therapists near", "coaches near",
    "practitioners in", "practitioners near",
    "nutritionists in", "estheticians in",
}

# Extra excludes per niche — appended on top of _SERVICE_EXCLUDES.
# Targets junk that slips through for specific niches.
_NICHE_EXTRA_EXCLUDES = {
    "therapy": ' -"group practice" -"therapy center" -"mental health center" -"counseling center" -"associates"',
    "nutrition coaching": ' -"nutrition center" -"dietitian group" -"registered dietitian center"',
    "business coaching": ' -"coaching firm" -"coaching company" -"coaching group"',
}

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


# Niches where "work with me" is a reliable solo-practitioner signal.
# This phrase almost exclusively appears on individual practitioners' own sites.
_WORK_WITH_ME_NICHES = {
    "life coaching", "health coaching", "relationship coaching",
    "financial coaching", "mindset coaching", "business coaching",
    "personal styling", "home organizing",
}

# Therapy uses "private practice" instead — stronger and more specific signal.
_PRIVATE_PRACTICE_NICHES = {"therapy"}


def _build_service_queries():
    queries = []
    for niche_term, niche_label in SERVICE_NICHES:
        extra = _NICHE_EXTRA_EXCLUDES.get(niche_label, "")
        base_excl = f"{_SERVICE_EXCLUDES}{extra}"

        for city in US_CITIES + US_NEIGHBOURHOODS + INTL_CITIES:
            # Template 1 (broad)
            queries.append((
                f'"{niche_term}" in {city} {base_excl}',
                niche_label,
            ))
            # Template 2 (solo-signal) — targets pages where the owner speaks directly
            if niche_label in _WORK_WITH_ME_NICHES:
                queries.append((
                    f'"{niche_term}" "work with me" {city} {base_excl}',
                    niche_label,
                ))
            elif niche_label in _PRIVATE_PRACTICE_NICHES:
                queries.append((
                    f'"private practice" "{niche_term}" {city} {base_excl}',
                    niche_label,
                ))

    return queries


def _build_intitle_queries():
    """
    Build a separate query pool using intitle:"contact" to find contact pages directly.

    Why intitle: works where inurl: failed:
    - inurl:contact — Google finds "contact" in the URL but returns the canonical
      (homepage) URL anyway. Unreliable and resulted in junk domains last time.
    - intitle:"contact" — Google matches the page's <title> tag. Every contact
      page has "Contact" or "Contact Us" in its title. Because the title match is
      specific to that page, Google returns the actual /contact page URL, not the
      homepage. We store this URL directly as contact_page_url — no extraction needed.

    These queries use ALL service niches and cities. E-commerce niches have a
    separate query pool below (ECOM_INTITLE_QUERIES) — originally assumed not
    worth running since shops "tend not to have Contact | ... page titles,"
    but testing 2026-06-18 found 40-44 leads per ~10-20 queries, so it's worth
    running alongside this pool, just without the city loop (product niches
    aren't searched per-city).
    """
    queries = []
    for niche_term, niche_label in SERVICE_NICHES:
        extra = _NICHE_EXTRA_EXCLUDES.get(niche_label, "")
        base_excl = f"{_SERVICE_EXCLUDES}{extra}"
        for city in US_CITIES + US_NEIGHBOURHOODS + INTL_CITIES:
            queries.append((
                f'"{niche_term}" intitle:"contact" {city} {base_excl}',
                niche_label,
            ))
    return queries


SERVICE_QUERIES = _build_service_queries()
INTITLE_QUERIES = _build_intitle_queries()

# ── E-commerce intitle queries — added 2026-06-18 ────────────────────────────
# No city loop (product niches aren't searched per-city). Curated from queries
# that performed well during manual testing; weaker variants dropped (e.g.
# "ceramic studio shop" and "custom t-shirt designs" returned 0-low results).
ECOM_INTITLE_QUERIES = [
    ('"handmade jewelry" intitle:"contact" -site:etsy.com -site:amazon.com -site:folksy.com -site:notonthehighstreet.com', "handmade jewelry"),
    ('"crystal jewelry" OR "gemstone jewelry" "handmade" intitle:"contact" -site:etsy.com -site:amazon.com', "handmade jewelry"),
    ('"beaded jewelry" OR "wire wrapped jewelry" "handmade" intitle:"contact" -site:etsy.com -site:amazon.com', "handmade jewelry"),
    ('"handcrafted jewelry" "my shop" intitle:"contact" -site:etsy.com -site:amazon.com', "handmade jewelry"),
    ('"handmade skincare" OR "natural skincare" intitle:"contact" -site:etsy.com -site:amazon.com', "handmade skincare"),
    ('"organic skincare" "small business" intitle:"contact" -site:etsy.com -site:amazon.com', "handmade skincare"),
    ('"vegan skincare" OR "clean skincare" "small batch" intitle:"contact" -site:etsy.com -site:amazon.com', "handmade skincare"),
    ('"artisan soap" OR "handmade soap" "shop" intitle:"contact" -site:etsy.com -site:amazon.com', "handmade skincare"),
    ('"handmade candles" OR "soy candles" intitle:"contact" -site:etsy.com -site:amazon.com', "handmade candles"),
    ('"small batch" candles "shop" intitle:"contact" -site:etsy.com -site:amazon.com', "handmade candles"),
    ('"coconut wax candles" OR "beeswax candles" "handmade" intitle:"contact" -site:etsy.com -site:amazon.com', "handmade candles"),
    ('"hand poured candles" "small business" intitle:"contact" -site:etsy.com -site:amazon.com', "handmade candles"),
    ('"handmade ceramics" OR "handmade pottery" intitle:"contact" -site:etsy.com -site:amazon.com', "ceramic pottery"),
    ('"wheel thrown pottery" OR "stoneware pottery" "handmade" intitle:"contact" -site:etsy.com -site:amazon.com', "ceramic pottery"),
    ('"functional pottery" OR "handmade mugs" "shop" intitle:"contact" -site:etsy.com -site:amazon.com', "ceramic pottery"),
    ('"pottery studio" "small batch" intitle:"contact" -site:etsy.com -site:amazon.com', "ceramic pottery"),
    ('"print on demand" "my store" intitle:"contact" -site:redbubble.com -site:teepublic.com -site:merch.amazon.com', "print on demand"),
    ('"print on demand" "my designs" intitle:"contact" -site:redbubble.com -site:teepublic.com -site:merch.amazon.com', "print on demand"),
    ('"sticker designs" OR "art prints" "my shop" intitle:"contact" -site:redbubble.com -site:teepublic.com -site:etsy.com', "print on demand"),
    ('"my illustrations" "print on demand" OR "art prints" intitle:"contact" -site:redbubble.com -site:etsy.com', "print on demand"),
]

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
    "thervo.com", "whereis.com",
    # E-commerce marketplaces
    "redbubble.com", "teepublic.com", "society6.com", "zazzle.com",
    "notonthehighstreet.com", "folksy.com", "artfire.com", "storenvy.com",
    "bigcartel.com",
    # People/contact lookup sites — never a business website
    "rocketreach.co", "zoominfo.com", "radaris.com", "spokeo.com",
    "whitepages.com", "intelius.com", "beenverified.com", "peoplefinders.com",
    "local.yahoo.com", "yellowbook.com", "superpages.com",
    "prospeo.io",
    # Job boards
    "ziprecruiter.com", "monster.com", "careerbuilder.com", "simplyhired.com",
    # Big chains / brands that shouldn't receive our outreach
    "daveandbusters.com", "greatwolf.com", "headspace.com",
    # Media, magazines, home tour sites
    "homestolove.com.au", "realestate.com.au", "domain.com.au",
    "womenshealthmag.com", "cosmopolitan.com", "harpersbazaar.com",
    "vogue.com", "elle.com", "marieclaire.com",
    "scribd.com", "yumpu.com",
    # Convention / event venues (large)
    "denverconvention.com",
    # Therapy room rental (not therapists)
    "roomsfortherapists.co.uk",
    # Coaching/therapy near-me directories with domain signals
    "nutritionistnear.me", "therapistnear.me", "coachnear.me",
    "findmytherapistdirectory.com", "findadietitian.com",
    # Free website builders — low quality, usually inactive or generic resource sites
    "weebly.com",
    # Job boards
    "jobtoday.com", "seek.com",
    # B2B wholesale supplier platforms — listings, not retail shops (added 2026-06-18)
    "goldsupplier.com",
    # Franchise networks (added 2026-06-18)
    "decoratingden.com",
    # Content platforms / academic repositories — never a business's own site (added 2026-06-18)
    "researchgate.net", "medium.com",
    # WordPress theme vendor demo sites, not real businesses (added 2026-06-18)
    "harutheme.com",
    # Local news/lifestyle media outlets (added 2026-06-18)
    "seattlerefined.com",
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


def _base_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


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
    "group practice", "group practices",
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
    # Snippet signals — solo practitioners never say these
    "our team of",
    "our therapists", "our coaches", "our counselors",
    "our practitioners", "our providers", "our psychologists",
    "our dietitians", "our nutritionists",
    "team of therapists", "team of coaches", "team of practitioners",
    "team of licensed", "team of certified",
    "group of therapists", "group of coaches",
}


def _is_institutional(title: str, snippet: str) -> bool:
    """Return True if title or snippet suggests an institution, chain, or non-solo business."""
    combined = (title + " " + snippet).lower()
    return any(kw in combined for kw in _INSTITUTIONAL_KEYWORDS)


def _is_directory_url(url: str) -> bool:
    """
    Return True if the URL path structure indicates a directory listing page.
    Checks exact path segments — avoids false positives like /therapists-guide-to-xyz.
    """
    path_parts = [p.lower() for p in urlparse(url).path.split("/") if p]
    for part in path_parts:
        if part in _DIRECTORY_PATH_SEGMENTS:
            return True
        if part.startswith("find-a"):
            return True
    return False


def _is_directory_connect_path(url: str) -> bool:
    """
    Return True if the URL path ends in /connect with 2+ path segments —
    the common signature of directory-platform profile pages, e.g.
    /united-states/seattle/life-coach/jane-doe/connect or /jane-doe/connect.
    Found across many unrelated directory domains 2026-06-18 (inclusivetherapists.com,
    physicaltherapynearme.co, ukihca.com, serviceprospot.com, longbeachbiz.com,
    catholictherapists.com, quokkahub.com.au, atozhealthguide.com, lifewellness.com).
    A bare single-segment /connect (a solo business's own contact page, e.g.
    alfredtang.com/connect) is NOT flagged — only the multi-segment profile pattern.
    """
    path_parts = [p for p in urlparse(url).path.split("/") if p]
    return len(path_parts) >= 2 and path_parts[-1].lower() == "connect"


_LISTICLE_STARTS_DIGIT = re.compile(r"^\d{1,2}\s")


def _is_listicle_title(title: str) -> bool:
    """
    Return True if the Google title is a roundup article or aggregator page,
    not a solo business website. Checks digit-starts and known aggregator phrases.
    """
    if not title:
        return False
    if _LISTICLE_STARTS_DIGIT.match(title):
        return True
    lower = title.lower()
    return any(phrase in lower for phrase in _LISTICLE_TITLE_PHRASES)


def _is_places_snippet(snippet: str) -> bool:
    """
    Return True if the snippet is a Google Business Profile / Maps result.
    These use the middle dot (·) as a separator between address, hours, and ratings.
    They're useless — the URL links to a GMB profile or Maps, not a real website.
    """
    if snippet.count("·") < 2:
        return False
    lower = snippet.lower()
    return any(kw in lower for kw in (
        "reviews", "open now", "closes", "opens at",
        "rating", "google reviews", "get directions",
    ))


def _should_skip(url: str) -> bool:
    netloc = urlparse(url).netloc.lower()
    domain = netloc[4:] if netloc.startswith("www.") else netloc
    # Academic and government TLDs
    if domain.endswith((".edu", ".gov", ".ac.uk", ".ac.au", ".ac.nz", ".edu.au")):
        return True
    # Nonprofit / cooperative TLDs — almost never a solo small business owner
    if domain.endswith((".org", ".coop")):
        return True
    # Domain-level institutional signals
    _DOMAIN_SIGNALS = ("hospital", "rehab", "health-system", "medcenter", "university", "college",
                       "academy", "rentals",
                       # Franchise networks — domain varies per location, brand name is the signal
                       "actioncoach",
                       # Manufacturer/brand showrooms, not solo small businesses (added 2026-06-18)
                       "siematic",
                       # Medical/clinical/institutional overlap not caught by other filters (added 2026-06-18)
                       "medspa", "dermatology", "plasticsurgery", "institute")
    if any(sig in domain for sig in _DOMAIN_SIGNALS):
        return True
    # "directory" or "near" in subdomain or domain name → almost certainly a listing site
    if "directory" in domain or domain.startswith("near"):
        return True
    if any(domain == s or domain.endswith("." + s) for s in SKIP_DOMAINS):
        return True
    if _is_directory_url(url):
        return True
    return False


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
            if _is_listicle_title(title):
                print(f"  [skip listicle] {title[:80]}", file=sys.stderr)
                continue
            if _is_places_snippet(snippet):
                print(f"  [skip places] {title[:80]}", file=sys.stderr)
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


_STATE_FILE = Path(__file__).parent / ".search_state.json"


def _load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    _STATE_FILE.write_text(json.dumps(state, indent=2))


def run(service_sample=20, ecommerce_sample=5, intitle_sample=10, ecom_intitle_sample=0):
    import random

    # ── Service query rotation queue ─────────────────────────────────────────
    # Works through all niche+city combos systematically before repeating.
    # Queue stored in .search_state.json, consumed front-to-back.
    # When exhausted, reshuffled and restarted.
    state = _load_state()
    queue = state.get("queue", [])
    total_service = len(SERVICE_QUERIES)
    total_intitle = len(INTITLE_QUERIES)

    if not queue or state.get("total_service_queries") != total_service:
        queue = [list(q) for q in SERVICE_QUERIES]
        random.shuffle(queue)
        label = (
            "initialised" if state.get("queue") is None
            else "reset (niche list changed)" if state.get("total_service_queries") != total_service
            else "reset after full cycle"
        )
        print(f"[Web Search] Service queue {label}: {len(queue)} combos.", file=sys.stderr)

    # ── Intitle query rotation queue ─────────────────────────────────────────
    # Separate pool of intitle:"contact" queries. Results are stored directly
    # as contact_page_url — extraction step skipped entirely.
    intitle_queue = state.get("intitle_queue", [])
    if not intitle_queue or state.get("total_intitle_queries") != total_intitle:
        intitle_queue = [list(q) for q in INTITLE_QUERIES]
        random.shuffle(intitle_queue)
        print(f"[Web Search] Intitle queue initialised/reset: {len(intitle_queue)} combos.", file=sys.stderr)

    # ── E-commerce intitle query rotation queue ──────────────────────────────
    # Added 2026-06-18. No city loop, so this pool is much smaller (20 combos)
    # than the service intitle pool — reshuffles/repeats far more often.
    total_ecom_intitle = len(ECOM_INTITLE_QUERIES)
    ecom_intitle_queue = state.get("ecom_intitle_queue", [])
    if not ecom_intitle_queue or state.get("total_ecom_intitle_queries") != total_ecom_intitle:
        ecom_intitle_queue = [list(q) for q in ECOM_INTITLE_QUERIES]
        random.shuffle(ecom_intitle_queue)
        print(f"[Web Search] E-commerce intitle queue initialised/reset: {len(ecom_intitle_queue)} combos.", file=sys.stderr)

    cycle = state.get("cycles_completed", 0)

    batch = queue[:service_sample]
    remaining_queue = queue[service_sample:]
    if not remaining_queue:
        cycle += 1
        print(f"[Web Search] Full service cycle complete ({cycle} total). Queue will reset next run.", file=sys.stderr)

    intitle_batch = intitle_queue[:intitle_sample]
    remaining_intitle = intitle_queue[intitle_sample:]

    ecom_intitle_batch = ecom_intitle_queue[:ecom_intitle_sample]
    remaining_ecom_intitle = ecom_intitle_queue[ecom_intitle_sample:]

    service_queries = [(q[0], q[1]) for q in batch]
    ecommerce_queries = random.sample(ECOMMERCE_QUERIES, min(ecommerce_sample, len(ECOMMERCE_QUERIES)))
    intitle_queries = [(q[0], q[1]) for q in intitle_batch]
    ecom_intitle_queries = [(q[0], q[1]) for q in ecom_intitle_batch]

    print(
        f"[Web Search] Running {len(service_queries)} service + {len(ecommerce_queries)} ecommerce "
        f"+ {len(intitle_queries)} intitle + {len(ecom_intitle_queries)} ecom intitle queries. "
        f"{len(remaining_queue)} service combos remaining in cycle.",
        file=sys.stderr,
    )

    leads = []
    seen_urls = set()
    snippet_email_count = 0
    intitle_contact_count = 0

    # ── Regular service + ecommerce queries ──────────────────────────────────
    for query, niche in service_queries + ecommerce_queries:
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

    # ── Intitle:"contact" queries — contact page URL known at search time ─────
    # Google matches the page's <title> tag, so results ARE the /contact page.
    # Store result URL as contact_page_url → skips extraction entirely.
    # Service and e-commerce intitle pools are merged here — same processing.
    for query, niche in intitle_queries + ecom_intitle_queries:
        print(f"\n[Web Search intitle] {query[:80]}", file=sys.stderr)
        results = _search(query, num=10)
        print(f"  {len(results)} URLs returned", file=sys.stderr)

        for result in results:
            contact_url = result["url"]
            base = _base_url(contact_url)

            # Skip if base domain is blocked or it's a directory
            if _should_skip(base):
                continue
            # Skip if the URL doesn't look like a contact page
            path = urlparse(contact_url).path.lower()
            if not any(kw in path for kw in ("contact", "reach", "get-in-touch", "connect", "book")):
                print(f"  [skip] no contact path: {contact_url[:70]}", file=sys.stderr)
                continue
            # Skip directory-platform profile pages (added 2026-06-18)
            if _is_directory_connect_path(contact_url):
                print(f"  [skip directory] {contact_url[:70]}", file=sys.stderr)
                continue

            if contact_url in seen_urls or base in seen_urls:
                continue
            seen_urls.add(contact_url)
            seen_urls.add(base)

            lead = {
                "source": "google",
                "owner_name": "",
                "shop_or_business_name": _extract_business_name(base),
                "website": base,
                "contact_page_url": contact_url,
                "outreach_type": "contact-form",
                "product_type": niche,
                "priority_score": 6,
                "status": "qualified",
                "notes": f"Contact page found via intitle search: {niche}",
            }
            leads.append(lead)
            intitle_contact_count += 1
            print(f"  + {contact_url}  [contact page direct]", file=sys.stderr)

        time.sleep(1.0)

    added = append_leads(leads)
    print(
        f"\n[Web Search] {added} new leads added "
        f"({snippet_email_count} email from snippet, {intitle_contact_count} contact page direct).",
        file=sys.stderr,
    )

    _save_state({
        "queue": remaining_queue,
        "intitle_queue": remaining_intitle,
        "ecom_intitle_queue": remaining_ecom_intitle,
        "total_service_queries": total_service,
        "total_intitle_queries": total_intitle,
        "total_ecom_intitle_queries": total_ecom_intitle,
        "cycles_completed": cycle,
        "runs_completed": state.get("runs_completed", 0) + 1,
        "last_run": __import__("datetime").date.today().isoformat(),
    })

    return added


if __name__ == "__main__":
    run()
