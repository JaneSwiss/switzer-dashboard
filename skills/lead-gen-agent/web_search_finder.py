"""
Web Search Lead Finder — discovers businesses not on Etsy using ValueSERP (Google)
and Bing API. Targets wedding photographers, interior designers, travel agencies,
florists, and other visual service businesses with their own websites.

Found website URLs are added to the lead tracker and then picked up by
website_contact_extractor.py on the next run.
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
from lead_tracker import append_leads

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# ── Location-based search queries ────────────────────────────────────────────
# Queries are generated from niches × locations and sampled randomly each run.

NICHES = [
    ("personal trainer",    "personal training"),
    ("life coach",          "life coaching"),
    ("nutritionist",        "nutrition coaching"),
    ("esthetician",         "esthetics"),
    ("massage therapist",   "massage therapy"),
    ("reformer pilates studio", "pilates"),
    ("interior designer",   "interior design"),
    ("wedding photographer","wedding photography"),
    ("event planner",       "event planning"),
    ("therapist",           "therapy"),
    ("business coach",      "business coaching"),
    ("florist",             "floristry"),
]

# US — mid-size cities (primary focus)
US_CITIES = [
    "Seattle", "Portland", "Denver", "Austin", "Nashville", "Charlotte",
    "San Diego", "Boston", "Miami", "Atlanta", "Minneapolis", "New Orleans",
    "Tampa", "Raleigh", "Phoenix", "Scottsdale", "Charleston", "Savannah",
    "Boulder", "Asheville", "Boise", "Salt Lake City", "Kansas City",
    "Louisville", "Indianapolis", "Columbus Ohio", "Pittsburgh", "Richmond Virginia",
    "Tucson", "Albuquerque", "Spokane", "Bozeman", "Fort Collins",
]

# US — big city neighbourhoods
US_NEIGHBOURHOODS = [
    "Brooklyn New York", "Santa Monica", "Silver Lake Los Angeles",
    "Lincoln Park Chicago", "Wicker Park Chicago", "West Village New York",
    "Georgetown Washington DC", "Dupont Circle Washington DC",
    "Pasadena California", "Hoboken New Jersey", "Park Slope Brooklyn",
    "Capitol Hill Seattle", "Highland Park Dallas", "South End Boston",
]

# International — secondary pool (UK + Australia)
INTL_CITIES = [
    "Notting Hill London", "Clapham London", "Edinburgh", "Bristol",
    "Brighton", "Manchester", "Bondi Sydney", "Newtown Sydney",
    "Fitzroy Melbourne", "St Kilda Melbourne", "Brisbane", "Perth Australia",
]

# Build full query list: niche × location → (query_string, niche_label)
def _build_queries():
    queries = []
    for niche_term, niche_label in NICHES:
        for city in US_CITIES + US_NEIGHBOURHOODS:
            queries.append((f"{niche_term} in {city}", niche_label))
        for city in INTL_CITIES:
            queries.append((f"{niche_term} in {city}", niche_label))
    return queries

QUERIES = _build_queries()

# Domains to skip — large directories, marketplaces, social networks
SKIP_DOMAINS = {
    "etsy.com", "amazon.com", "yelp.com", "tripadvisor.com", "pinterest.com",
    "instagram.com", "facebook.com", "twitter.com", "linkedin.com", "youtube.com",
    "tiktok.com", "google.com", "bing.com", "indeed.com", "thumbtack.com",
    "houzz.com", "theknot.com", "weddingwire.com", "zola.com", "bark.com",
    "angieslist.com", "angi.com", "nextdoor.com", "groupon.com", "thumbtack.com",
    "wikipedia.org", "reddit.com", "quora.com",
}


def _should_skip(url: str) -> bool:
    domain = urlparse(url).netloc.lower().lstrip("www.")
    return any(skip in domain for skip in SKIP_DOMAINS)


# ── Serper.dev (Google Search API — 2,500 free searches) ─────────────────────

def _search(query: str, num: int = 10) -> list[str]:
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
        items = resp.json().get("organic", [])
        return [i["link"] for i in items if i.get("link") and not _should_skip(i["link"])]
    except Exception as e:
        print(f"  [Serper error] {e}", file=sys.stderr)
        return []


def _extract_business_name(url: str) -> str:
    """Best-effort business name from domain."""
    domain = urlparse(url).netloc.lower().lstrip("www.")
    name = domain.split(".")[0]
    # Convert hyphens/underscores to spaces and title-case
    return name.replace("-", " ").replace("_", " ").title()


def run(queries=None, results_per_query=10, daily_sample=25):
    import random
    all_queries = queries or QUERIES
    # Pick a random batch each run so we cover different cities/niches daily
    search_queries = random.sample(all_queries, min(daily_sample, len(all_queries)))
    leads = []
    seen_urls = set()

    for query, niche in search_queries:
        print(f"\n[Web Search] {query[:60]}...", file=sys.stderr)
        urls = _search(query, num=results_per_query)
        print(f"  Found {len(urls)} URLs", file=sys.stderr)

        for url in urls:
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
                "status": "found",
                "notes": f"Found via web search: {niche}",
            }
            leads.append(lead)
            print(f"  + {url}", file=sys.stderr)

        time.sleep(1.0)

    added = append_leads(leads)
    print(f"\n[Web Search] {added} new leads added to tracker.", file=sys.stderr)
    return added


if __name__ == "__main__":
    run()
