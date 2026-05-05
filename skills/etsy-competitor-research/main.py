"""
Switzertemplates — Etsy Competitor Scraper
Scrapes public Etsy pages (no API needed) and outputs structured markdown
ready to feed into the bi-weekly intelligence report agent.

Usage:
  # Scrape specific competitor listings
  python3 main.py listings https://www.etsy.com/listing/123 https://www.etsy.com/listing/456

  # Search a keyword and scrape top N results
  python3 main.py search "wix website template" --top 5

  # Both
  python3 main.py search "branding kit canva" --top 5 --save
"""

import requests
import json
import re
import time
import argparse
import sys
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xhtml xml,*/*;q=0.8",
}

SWITZERTEMPLATES_SHOP = "switzertemplates"


# ── Helpers ────────────────────────────────────────────────────────────────

def fetch(url, retries=2):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(2)
            else:
                print(f"  [fetch error] {url} — {e}", file=sys.stderr)
                return None


def extract_json_ld(soup):
    """Pull structured data Etsy embeds in every listing page."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string)
            if isinstance(data, list):
                for item in data:
                    if item.get("@type") in ("Product", "ItemPage"):
                        return item
            elif data.get("@type") in ("Product", "ItemPage"):
                return data
        except (json.JSONDecodeError, AttributeError):
            continue
    return {}


def extract_initial_state(html):
    """Etsy injects __INITIAL_STATE__ with rich listing data."""
    match = re.search(r'__INITIAL_STATE__\s*=\s*(\{.+?\});\s*\n', html)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}
    return {}


# ── Listing scraper ────────────────────────────────────────────────────────

def scrape_listing(url):
    print(f"  Scraping: {url}", file=sys.stderr)
    html = fetch(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    ld = extract_json_ld(soup)
    result = {"url": url}

    # Title
    result["title"] = (
        ld.get("name")
        or (soup.find("h1") and soup.find("h1").get_text(strip=True))
        or "Unknown"
    )

    # Price
    price_tag = soup.find("p", {"data-buy-box-region": "price"})
    if not price_tag:
        price_tag = soup.select_one("[class*='wt-text-title-03']")
    result["price"] = price_tag.get_text(strip=True) if price_tag else (
        ld.get("offers", {}).get("price", "Unknown")
    )

    # Rating + reviews
    rating_el = soup.find("input", {"id": "rating-star-display"})
    result["rating"] = rating_el["value"] if rating_el else (
        ld.get("aggregateRating", {}).get("ratingValue", "Unknown")
    )
    review_count_el = soup.find("a", href=re.compile(r"#reviews"))
    result["review_count"] = (
        re.search(r"[\d,]+", review_count_el.get_text()).group()
        if review_count_el else
        ld.get("aggregateRating", {}).get("reviewCount", "Unknown")
    )

    # Sales (sometimes shown on listing page)
    sales_el = soup.find(string=re.compile(r"[\d,]+ sales"))
    result["sales"] = re.search(r"[\d,]+", sales_el).group() if sales_el else "Unknown"

    # Tags
    tag_section = soup.find("div", {"data-appears-component-name": "listing_page_tags"})
    if not tag_section:
        tag_section = soup.find("div", class_=re.compile(r"tags"))
    tags = []
    if tag_section:
        for a in tag_section.find_all("a"):
            text = a.get_text(strip=True)
            if text:
                tags.append(text)
    result["tags"] = tags

    # Description (first 400 chars is enough for the report)
    desc_el = soup.find("div", {"data-id": "description-text"})
    if not desc_el:
        desc_el = soup.find("p", class_=re.compile(r"description"))
    if not desc_el:
        desc_text = ld.get("description", "")
    else:
        desc_text = desc_el.get_text(" ", strip=True)
    result["description_preview"] = desc_text[:400] + ("..." if len(desc_text) > 400 else "")

    # Shop name
    shop_el = soup.find("a", {"data-appears-component-name": "shop_name_link"})
    if not shop_el:
        shop_el = soup.find("a", href=re.compile(r"/shop/"))
    result["shop"] = shop_el.get_text(strip=True) if shop_el else "Unknown"

    time.sleep(1.2)  # polite delay
    return result


# ── Search scraper ────────────────────────────────────────────────────────

def scrape_search(keyword, top=5):
    """Get top listing URLs for a keyword from Etsy search results."""
    query = keyword.replace(" ", "+")
    url = f"https://www.etsy.com/search?q={query}&order=most_relevant"
    print(f"  Searching: {keyword!r}", file=sys.stderr)

    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    listing_links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/listing/" in href and "etsy.com" in href:
            # Strip query params
            clean = href.split("?")[0]
            if clean not in listing_links:
                # Skip own shop
                if SWITZERTEMPLATES_SHOP.lower() not in clean.lower():
                    listing_links.append(clean)
        if len(listing_links) >= top:
            break

    time.sleep(1)
    return listing_links


# ── Markdown formatter ────────────────────────────────────────────────────

def format_report(listings, keyword=None):
    now = datetime.now().strftime("%d %b %Y")
    lines = []
    lines.append(f"## COMPETITOR ANALYSIS — {keyword or 'Direct Listings'}")
    lines.append(f"Generated: {now} | Listings scraped: {len(listings)}\n")

    for i, l in enumerate(listings, 1):
        if not l:
            continue
        lines.append(f"### {i}. {l['title'][:80]}{'...' if len(l['title']) > 80 else ''}")
        lines.append(f"**Shop:** {l['shop']}  |  **Price:** {l['price']}  |  "
                     f"**Rating:** {l['rating']} ({l['review_count']} reviews)  |  "
                     f"**Sales:** {l['sales']}")
        lines.append(f"**URL:** {l['url']}\n")

        if l.get("tags"):
            valid = [t for t in l["tags"] if len(t) <= 20]
            invalid = [t for t in l["tags"] if len(t) > 20]
            lines.append("**Tags:**")
            for t in valid:
                lines.append(f"- `{t}` ({len(t)} chars) ✓")
            for t in invalid:
                lines.append(f"- `{t}` ({len(t)} chars) ✗ too long")
            lines.append("")

        if l.get("description_preview"):
            lines.append(f"**Description preview:**")
            lines.append(f"> {l['description_preview']}\n")

        lines.append("---\n")

    # Summary: tag overlap analysis
    all_tags = []
    for l in listings:
        if l:
            all_tags.extend([t.lower() for t in l.get("tags", [])])

    from collections import Counter
    tag_counts = Counter(all_tags)
    common = [(t, c) for t, c in tag_counts.most_common(15) if c >= 2]

    if common:
        lines.append("### TAGS USED BY MULTIPLE COMPETITORS")
        lines.append("These appear across 2+ listings — signals what buyers search:\n")
        for tag, count in common:
            lines.append(f"- `{tag}` — used by {count} competitors")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Etsy competitor scraper")
    sub = parser.add_subparsers(dest="mode", required=True)

    # Mode 1: scrape specific URLs
    p_listings = sub.add_parser("listings", help="Scrape specific listing URLs")
    p_listings.add_argument("urls", nargs="+", help="Etsy listing URLs")
    p_listings.add_argument("--save", action="store_true")

    # Mode 2: search keyword then scrape top results
    p_search = sub.add_parser("search", help="Search a keyword and scrape top results")
    p_search.add_argument("keyword", help="Search keyword")
    p_search.add_argument("--top", type=int, default=5, help="Number of listings to scrape (default 5)")
    p_search.add_argument("--save", action="store_true")

    args = parser.parse_args()

    if args.mode == "listings":
        urls = args.urls
        keyword = None
    else:
        urls = scrape_search(args.keyword, top=args.top)
        keyword = args.keyword
        if not urls:
            print("No listings found. Check keyword or try again.", file=sys.stderr)
            sys.exit(1)
        print(f"  Found {len(urls)} listings to scrape", file=sys.stderr)

    listings = [scrape_listing(u) for u in urls]
    report = format_report([l for l in listings if l], keyword=keyword)

    print(report)

    if getattr(args, "save", False):
        slug = (keyword or "listings").replace(" ", "-")
        out = Path(f"competitor-{slug}-{datetime.now().strftime('%Y%m%d')}.md")
        out.write_text(report)
        print(f"\n[Saved: {out}]", file=sys.stderr)


if __name__ == "__main__":
    main()
