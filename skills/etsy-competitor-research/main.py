"""
Switzertemplates — Etsy Competitor Research
Scrapes public Etsy pages via Apify rotating proxy for competitive intelligence.
Captures Bestseller and Popular Now badges. Digital listings only.

Usage:
  # Full multi-keyword analysis (recommended)
  python3 main.py analyze
  python3 main.py analyze --top 20

  # Single keyword (quick check)
  python3 main.py search "wix website template" --top 10

  # Specific listing URLs
  python3 main.py listings https://www.etsy.com/listing/123 ...
"""

import json
import re
import sys
import time
import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
import apify_client
import report_to_html

SWITZERTEMPLATES_SHOP = "switzertemplates"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "competitors"

SEED_KEYWORDS = [
    "wix website",
    "coach website",
    "wix website template",
    "website templates",
    "ecommerce website",
    "landing page",
    "branding kit",
    "branding package",
    "branding bundle",
    "branding template",
    "coaching templates",
    "coaching business",
    "coaching bundle",
    "social media templates",
]


# ── HTTP ──────────────────────────────────────────────────────────────────

def fetch(url):
    return apify_client.fetch(url)


# ── HTML helpers ──────────────────────────────────────────────────────────

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
    """
    Etsy embeds __INITIAL_STATE__ with rich listing data for every page.
    Uses json.JSONDecoder to find the end of the JSON object reliably.
    """
    match = re.search(r'__INITIAL_STATE__\s*=\s*', html)
    if not match:
        return {}
    try:
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(html, match.end())
        return data
    except (json.JSONDecodeError, ValueError):
        return {}


def find_badges(element):
    """
    Return set of badge keys found anywhere within a BeautifulSoup element.
    Checks text content for Etsy's badge labels.
    """
    badges = set()
    text = element.get_text(" ", strip=True)
    if re.search(r"\bBestseller\b", text, re.I):
        badges.add("bestseller")
    if re.search(r"\bPopular now\b", text, re.I):
        badges.add("popular_now")
    return badges


def is_digital(soup, ld):
    """
    Return True if the listing appears to be a digital product.
    Primary filtering is done at the search URL level (item_type=digital),
    so this is a light secondary check — only excludes obvious physical goods.
    """
    text = soup.get_text(" ", strip=True).lower()

    # Clear physical signals — skip these
    physical_signals = ("ships from", "ships to", "shipping from", "estimated arrival",
                        "ready to ship", "made to order")
    if any(sig in text for sig in physical_signals):
        return False

    # Positive digital signals — definitely include
    digital_signals = ("instant download", "digital download", "digital file",
                       "digital product", "digital item", "you'll get a downloadable",
                       "access link", "template link", "canva link", "wix link",
                       "download link", "pdf", "digital delivery")
    if any(sig in text for sig in digital_signals):
        return True

    # Trust the URL-level filter (item_type=digital) as the default
    return True


# ── Search page scraper ───────────────────────────────────────────────────

def scrape_search_page(keyword, top=15):
    """
    Fetch Etsy search results for keyword, filtered to digital listings.
    Parses listing cards to capture Bestseller and Popular Now badges
    before visiting individual pages.

    Returns list of dicts: {url, bestseller_badge, popular_now_badge}
    """
    query = keyword.replace(" ", "+")
    # item_type=digital filters to digital listings; locale=en-US ensures English results
    url = (
        f"https://www.etsy.com/search?q={query}"
        f"&item_type=digital&order=most_relevant&locale=en-US"
    )
    print(f"  Searching: {keyword!r}", file=sys.stderr)

    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_urls = set()

    # Primary strategy: find listing cards by data-listing-id attribute
    cards = soup.find_all(attrs={"data-listing-id": True})

    if cards:
        for card in cards:
            a = card.find("a", href=re.compile(r"/listing/"))
            if not a:
                continue
            href = a.get("href", "").split("?")[0]
            if not href or SWITZERTEMPLATES_SHOP.lower() in href.lower():
                continue
            if href in seen_urls:
                continue
            badges = find_badges(card)
            seen_urls.add(href)
            results.append({
                "url": href,
                "bestseller_badge": "bestseller" in badges,
                "popular_now_badge": "popular_now" in badges,
            })
            if len(results) >= top:
                break

    # Fallback: walk anchor tags, climb DOM to find card container
    if not results:
        for a in soup.find_all("a", href=re.compile(r"/listing/")):
            href = a.get("href", "").split("?")[0]
            if not href or SWITZERTEMPLATES_SHOP.lower() in href.lower():
                continue
            if href in seen_urls:
                continue
            # Walk up up to 6 levels to find the card container
            card = a
            for _ in range(6):
                if not card.parent:
                    break
                card = card.parent
                if card.name in ("li", "article"):
                    break
            badges = find_badges(card)
            seen_urls.add(href)
            results.append({
                "url": href,
                "bestseller_badge": "bestseller" in badges,
                "popular_now_badge": "popular_now" in badges,
            })
            if len(results) >= top:
                break

    time.sleep(1.5)
    return results


# ── Individual listing scraper ────────────────────────────────────────────

def scrape_listing(url, prefetch=None):
    """
    Scrape an individual listing page.
    Returns a dict or None if the listing is not digital.

    prefetch: badge data captured from the search card
              {bestseller_badge: bool, popular_now_badge: bool}
    """
    print(f"  Scraping: {url}", file=sys.stderr)
    html = fetch(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    ld = extract_json_ld(soup)

    # Digital check — skip physical products
    if not is_digital(soup, ld):
        print(f"  [skip] Not digital: {url}", file=sys.stderr)
        return None

    # Shop name — check early so we can skip own listings
    shop_el = soup.find("a", {"data-appears-component-name": "shop_name_link"})
    if not shop_el:
        shop_el = soup.find("a", href=re.compile(r"/shop/"))
    shop_name = shop_el.get_text(strip=True) if shop_el else ""

    if SWITZERTEMPLATES_SHOP.lower() in shop_name.lower():
        print(f"  [skip] Own listing: {url}", file=sys.stderr)
        return None

    result = {"url": url, "shop": shop_name}

    # Badges — prefer search card data (more reliable), fall back to page
    if prefetch:
        result["bestseller_badge"] = prefetch.get("bestseller_badge", False)
        result["popular_now_badge"] = prefetch.get("popular_now_badge", False)
    else:
        page_badges = find_badges(soup)
        result["bestseller_badge"] = "bestseller" in page_badges
        result["popular_now_badge"] = "popular_now" in page_badges

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
    result["price"] = (
        price_tag.get_text(strip=True) if price_tag
        else str(ld.get("offers", {}).get("price", "Unknown"))
    )

    # Rating + review count
    rating_el = soup.find("input", {"id": "rating-star-display"})
    result["rating"] = (
        rating_el["value"] if rating_el
        else ld.get("aggregateRating", {}).get("ratingValue", "Unknown")
    )
    review_el = soup.find("a", href=re.compile(r"#reviews"))
    result["review_count"] = (
        re.search(r"[\d,]+", review_el.get_text()).group() if review_el
        else ld.get("aggregateRating", {}).get("reviewCount", "Unknown")
    )

    # Sales count (shown on some listing pages)
    sales_el = soup.find(string=re.compile(r"[\d,]+ sales"))
    result["sales"] = (
        re.search(r"[\d,]+", sales_el).group() if sales_el else "Unknown"
    )

    # Description preview
    desc_el = soup.find("div", {"data-id": "description-text"})
    if not desc_el:
        desc_el = soup.find("p", class_=re.compile(r"description"))
    desc_text = (
        desc_el.get_text(" ", strip=True) if desc_el
        else ld.get("description", "")
    )
    result["description_preview"] = desc_text[:400] + ("..." if len(desc_text) > 400 else "")

    time.sleep(1.5)
    return result


# ── Title keyword extraction ──────────────────────────────────────────────

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "i", "in", "is", "it", "its", "of", "on", "or", "that",
    "the", "this", "to", "was", "with", "your", "you", "my", "our", "their",
    "will", "can", "get", "all", "new", "any", "more", "how", "do", "if",
    "so", "we", "not", "no", "up", "use", "used", "make", "made", "one",
    "two", "set", "full", "easy", "great", "best", "amp", "about", "also",
}


def extract_title_keywords(listings):
    """
    Extract single words and 2-word phrases from listing titles.
    Returns (word_counts, phrase_counts) — both Counter objects.
    """
    words = []
    phrases = []
    for l in listings:
        title = l.get("title", "")
        # Clean title: lowercase, split on non-alphanumeric except spaces
        clean = re.sub(r"[^a-z0-9 ]", " ", title.lower())
        tokens = [t for t in clean.split() if len(t) > 2 and t not in _STOP_WORDS]
        words.extend(tokens)
        # Bigrams
        for i in range(len(tokens) - 1):
            phrases.append(f"{tokens[i]} {tokens[i+1]}")

    return Counter(words), Counter(phrases)


# ── Keyword expansion ─────────────────────────────────────────────────────

def expand_keywords(all_listings, seed_keywords, max_new=20):
    """
    Extract the most frequent title words across all scraped listings.
    Return terms not already covered by seed keywords as additional search queries.
    """
    seed_lower = {k.lower() for k in seed_keywords}
    _, phrase_counts = extract_title_keywords(all_listings)

    new_kws = []
    for phrase, count in phrase_counts.most_common(200):
        if phrase not in seed_lower and count >= 3 and len(phrase) > 5:
            new_kws.append((phrase, count))
        if len(new_kws) >= max_new:
            break
    return new_kws


# ── Report formatter ──────────────────────────────────────────────────────

def format_full_report(results_by_keyword, expanded_keywords=None):
    """Generate the full multi-keyword competitive analysis report."""
    now = datetime.now().strftime("%d %b %Y %H:%M")
    all_listings = [l for ls in results_by_keyword.values() for l in ls]

    lines = []
    lines.append("# Etsy Competitive Intelligence Report — Switzertemplates")
    lines.append(f"Generated: {now}  |  Keywords: {len(results_by_keyword)}  "
                 f"|  Total digital listings: {len(all_listings)}\n")

    # ── Summary table ──────────────────────────────────────────────────
    lines.append("## Summary by Keyword\n")
    lines.append("| Keyword | Listings | Bestseller | Popular Now | Avg Price |")
    lines.append("|---------|----------|:----------:|:-----------:|-----------|")
    for kw, listings in results_by_keyword.items():
        bs = sum(1 for l in listings if l.get("bestseller_badge"))
        pn = sum(1 for l in listings if l.get("popular_now_badge"))
        prices = []
        for l in listings:
            m = re.search(r"[\d.]+", str(l.get("price", "")).replace(",", ""))
            if m:
                prices.append(float(m.group()))
        avg = f"${sum(prices)/len(prices):.2f}" if prices else "N/A"
        lines.append(f"| {kw} | {len(listings)} | {bs} | {pn} | {avg} |")
    lines.append("")

    # ── Bestseller listings ────────────────────────────────────────────
    bestsellers = [l for l in all_listings if l.get("bestseller_badge")]
    if bestsellers:
        lines.append(f"## Bestseller Listings ({len(bestsellers)} found)\n")
        for l in bestsellers:
            lines.append(f"### {l['title'][:80]}")
            lines.append(f"**Shop:** {l['shop']}  |  **Price:** {l['price']}  |  "
                         f"**Reviews:** {l['review_count']}  |  **Sales:** {l['sales']}")
            lines.append(f"**URL:** {l['url']}\n")
    else:
        lines.append("## Bestseller Listings\n_None found in this run._\n")

    # ── Popular Now listings ───────────────────────────────────────────
    popular = [l for l in all_listings if l.get("popular_now_badge")]
    if popular:
        lines.append(f"## Popular Now Listings ({len(popular)} found)\n")
        for l in popular:
            lines.append(f"### {l['title'][:80]}")
            lines.append(f"**Shop:** {l['shop']}  |  **Price:** {l['price']}  |  "
                         f"**Reviews:** {l['review_count']}  |  **Sales:** {l['sales']}")
            lines.append(f"**URL:** {l['url']}\n")
    else:
        lines.append("## Popular Now Listings\n_None found in this run._\n")

    # ── Per-keyword detail ─────────────────────────────────────────────
    lines.append("---\n## Full Listings by Keyword\n")
    for kw, listings in results_by_keyword.items():
        lines.append(f"### \"{kw}\" — {len(listings)} digital listings\n")
        if not listings:
            lines.append("_No digital listings captured._\n")
            continue
        for i, l in enumerate(listings, 1):
            badges = []
            if l.get("bestseller_badge"):
                badges.append("[BESTSELLER]")
            if l.get("popular_now_badge"):
                badges.append("[POPULAR NOW]")
            badge_str = "  " + "  ".join(badges) if badges else ""
            lines.append(f"**{i}. {l['title'][:70]}**{badge_str}")
            lines.append(
                f"Shop: {l['shop']}  |  Price: {l['price']}  |  "
                f"Reviews: {l['review_count']}  |  Sales: {l['sales']}"
            )
            lines.append(f"URL: {l['url']}\n")
        lines.append("---\n")

    # ── Title keyword analysis ─────────────────────────────────────────
    word_counts, phrase_counts = extract_title_keywords(all_listings)

    lines.append("## Most Common Words in Competitor Titles\n")
    lines.append("_Keywords competitors prioritise in their listing titles — "
                 "Etsy's #1 ranking factor. Cross-reference against your own titles._\n")
    lines.append("| Keyword | Appearances | Valid Etsy tag (≤20 chars) |")
    lines.append("|---------|:-----------:|:-------------------------:|")
    for word, count in word_counts.most_common(40):
        valid = "yes" if len(word) <= 20 else "no"
        lines.append(f"| {word} | {count} | {valid} |")
    lines.append("")

    lines.append("## Most Common 2-Word Phrases in Competitor Titles\n")
    lines.append("_High-frequency phrases reveal the exact keyword combinations buyers search for._\n")
    lines.append("| Phrase | Appearances | Valid Etsy tag (≤20 chars) |")
    lines.append("|--------|:-----------:|:-------------------------:|")
    for phrase, count in phrase_counts.most_common(30):
        if count >= 2:
            valid = "yes" if len(phrase) <= 20 else "no"
            lines.append(f"| {phrase} | {count} | {valid} |")
    lines.append("")

    # ── Keyword expansion suggestions ──────────────────────────────────
    if expanded_keywords:
        lines.append("## Keyword Expansion — Suggested Next Searches\n")
        lines.append("These 2-word phrases appeared frequently in competitor titles. "
                     "Use them as additional Etsy search queries to find more competitors:\n")
        for phrase, count in expanded_keywords[:20]:
            lines.append(f"- `{phrase}` — in {count} titles")
        lines.append("")

    return "\n".join(lines)


def format_single_report(listings, keyword=None):
    """Backward-compatible single-keyword markdown report."""
    now = datetime.now().strftime("%d %b %Y")
    lines = []
    lines.append(f"## COMPETITOR ANALYSIS — {keyword or 'Direct Listings'}")
    lines.append(f"Generated: {now}  |  Listings: {len(listings)}\n")

    for i, l in enumerate(listings, 1):
        badges = []
        if l.get("bestseller_badge"):
            badges.append("[BESTSELLER]")
        if l.get("popular_now_badge"):
            badges.append("[POPULAR NOW]")
        badge_str = "  " + "  ".join(badges) if badges else ""
        lines.append(f"### {i}. {l['title'][:80]}{badge_str}")
        lines.append(
            f"**Shop:** {l['shop']}  |  **Price:** {l['price']}  |  "
            f"**Rating:** {l['rating']} ({l['review_count']} reviews)  |  "
            f"**Sales:** {l['sales']}"
        )
        lines.append(f"**URL:** {l['url']}\n")
        if l.get("description_preview"):
            lines.append(f"**Description preview:**\n> {l['description_preview']}\n")
        lines.append("---\n")

    word_counts, phrase_counts = extract_title_keywords(listings)
    common_words = [(w, c) for w, c in word_counts.most_common(15) if c >= 2]
    if common_words:
        lines.append("### TOP TITLE KEYWORDS ACROSS COMPETITORS")
        lines.append("_Signals what buyers search for:_\n")
        for word, count in common_words:
            lines.append(f"- `{word}` — {count} listings")

    return "\n".join(lines)


# ── Run modes ─────────────────────────────────────────────────────────────

def run_analyze(args):
    """Full multi-keyword competitive analysis across all seed keywords."""
    top = args.top
    do_expand = not args.no_expand

    print(f"\n=== Etsy Competitive Analysis ===", file=sys.stderr)
    print(f"Seed keywords: {len(SEED_KEYWORDS)}  |  Max per keyword: {top}\n",
          file=sys.stderr)

    results_by_keyword = {}
    all_listing_dicts = []

    for kw in SEED_KEYWORDS:
        search_cards = scrape_search_page(kw, top=top)
        if not search_cards:
            print(f"  [skip] No search results for {kw!r}\n", file=sys.stderr)
            continue
        listings = []
        for card in search_cards:
            listing = scrape_listing(card["url"], prefetch=card)
            if listing:
                listing["keyword"] = kw
                listings.append(listing)
                all_listing_dicts.append(listing)
        results_by_keyword[kw] = listings
        print(f"  -> {len(listings)} digital listings captured\n", file=sys.stderr)

    # Keyword expansion pass
    expanded = []
    if do_expand and all_listing_dicts:
        expanded = expand_keywords(all_listing_dicts, SEED_KEYWORDS)
        if expanded:
            print(f"\n=== Keyword Expansion: {len(expanded)} new terms found ===",
                  file=sys.stderr)
            print("Running top 10 expansion keywords...\n", file=sys.stderr)
            for tag, count in expanded[:10]:
                search_cards = scrape_search_page(tag, top=min(top, 10))
                listings = []
                for card in search_cards:
                    listing = scrape_listing(card["url"], prefetch=card)
                    if listing:
                        listing["keyword"] = f"{tag} (expanded)"
                        listings.append(listing)
                        all_listing_dicts.append(listing)
                key = f"{tag} (expanded)"
                results_by_keyword[key] = listings
                print(f"  -> {len(listings)} listings for '{tag}'\n", file=sys.stderr)

    report = format_full_report(results_by_keyword, expanded_keywords=expanded)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = datetime.now().strftime("%Y%m%d-%H%M")
    out_md   = OUTPUT_DIR / f"competitor-analysis-{slug}.md"
    out_html = OUTPUT_DIR / f"competitor-analysis-{slug}.html"

    out_md.write_text(report)
    print(f"\n[Saved markdown: {out_md}]", file=sys.stderr)

    # Generate HTML report
    report_to_html.generate(results_by_keyword, out_html, expanded_keywords=expanded)
    print(f"[Saved HTML:     {out_html}]", file=sys.stderr)

    import subprocess
    subprocess.Popen(["open", str(out_html)])
    print("[Opened HTML in browser]", file=sys.stderr)


def run_search(args):
    """Single keyword search — quick competitive check."""
    search_cards = scrape_search_page(args.keyword, top=args.top)
    if not search_cards:
        print("No results found.", file=sys.stderr)
        sys.exit(1)

    listings = []
    for card in search_cards:
        listing = scrape_listing(card["url"], prefetch=card)
        if listing:
            listings.append(listing)

    report = format_single_report(listings, keyword=args.keyword)
    print(report)

    if args.save:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = args.keyword.replace(" ", "-")
        out = OUTPUT_DIR / f"competitor-{slug}-{datetime.now().strftime('%Y%m%d')}.md"
        out.write_text(report)
        print(f"\n[Saved: {out}]", file=sys.stderr)


def run_listings(args):
    """Scrape specific listing URLs."""
    listings = []
    for url in args.urls:
        listing = scrape_listing(url)
        if listing:
            listings.append(listing)

    report = format_single_report(listings)
    print(report)

    if args.save:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUTPUT_DIR / f"competitor-listings-{datetime.now().strftime('%Y%m%d')}.md"
        out.write_text(report)
        print(f"\n[Saved: {out}]", file=sys.stderr)


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Etsy competitive research — digital listings only, with badge detection"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_analyze = sub.add_parser("analyze", help="Full multi-keyword analysis (recommended)")
    p_analyze.add_argument("--top", type=int, default=15,
                           help="Max listings per keyword (default: 15)")
    p_analyze.add_argument("--no-expand", action="store_true",
                           help="Skip the keyword expansion pass")

    p_search = sub.add_parser("search", help="Quick single-keyword search")
    p_search.add_argument("keyword")
    p_search.add_argument("--top", type=int, default=10)
    p_search.add_argument("--save", action="store_true")

    p_listings = sub.add_parser("listings", help="Scrape specific listing URLs")
    p_listings.add_argument("urls", nargs="+")
    p_listings.add_argument("--save", action="store_true")

    args = parser.parse_args()

    if args.mode == "analyze":
        run_analyze(args)
    elif args.mode == "search":
        run_search(args)
    elif args.mode == "listings":
        run_listings(args)


if __name__ == "__main__":
    main()
