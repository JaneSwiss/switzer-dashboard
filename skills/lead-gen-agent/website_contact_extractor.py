"""
Website Contact Extractor — finds email addresses and contact pages
from business websites discovered by the Etsy and Instagram finders.

For each lead with a website URL but no email yet:
  - Fetches homepage, /contact, /about pages via Apify Proxy
  - Extracts email addresses via regex and mailto links
  - Finds the contact page URL if no direct email is found
  - Updates the pinterest_present flag if a Pinterest link is found on site
"""

import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
import apify_fetch
from lead_tracker import load_leads, update_lead, get_leads_needing_contact_extraction

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Domains to ignore in extracted emails (generic / not personal)
SKIP_EMAIL_DOMAINS = {
    "example.com", "sentry.io", "wix.com", "squarespace.com",
    "shopify.com", "wordpress.com", "godaddy.com", "mailchimp.com",
    "flodesk.com", "klaviyo.com", "google.com", "facebook.com",
    "instagram.com", "pinterest.com", "twitter.com", "etsy.com",
    "lingying.com", "olamexican.com.au",
}

# Non-business website domains to skip entirely (don't bother fetching)
SKIP_WEBSITE_DOMAINS = {
    "bing.com", "google.com", "linkedin.com", "linktr.ee", "benable.com",
    "threads.net", "snapchat.com", "bio.site", "beacons.ai", "later.com",
    "amazon.com", "ebay.com", "youtube.com", "tiktok.com", "twitter.com",
    "x.com", "reddit.com", "tumblr.com", "pinterest.com",
}

CONTACT_PATH_HINTS = ["/contact", "/contact-us", "/get-in-touch", "/about", "/about-us", "/reach-us"]

# E-commerce niches that are already Pinterest-heavy — skip if Pinterest detected
ECOMMERCE_NICHES = {
    "handmade jewelry", "handmade skincare", "handmade candles",
    "ceramic pottery", "print on demand",
}


def _clean_email(email: str):
    email = email.strip().lower()
    domain = email.split("@")[-1]
    if domain in SKIP_EMAIL_DOMAINS:
        return None
    # Skip image filenames, CSS values, etc.
    if any(email.endswith(ext) for ext in [".png", ".jpg", ".gif", ".css", ".js"]):
        return None
    return email


def _extract_emails(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")

    emails = set()

    # mailto links are most reliable
    for a in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
        raw = a["href"].replace("mailto:", "").split("?")[0].strip()
        cleaned = _clean_email(raw)
        if cleaned:
            emails.add(cleaned)

    # Visible text scan
    for m in EMAIL_RE.finditer(soup.get_text(" ")):
        cleaned = _clean_email(m.group())
        if cleaned:
            emails.add(cleaned)

    return sorted(emails)


def _find_contact_page_url(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(hint in href for hint in ["contact", "get-in-touch", "reach"]):
            return urljoin(base_url, a["href"])
    return ""


def _has_pinterest(html: str) -> bool:
    return bool(re.search(r"pinterest\.com", html, re.I))


def _is_wix_site(html: str) -> bool:
    """Wix contact forms are JS-rendered and can't be submitted by Playwright reliably."""
    return "static.wixstatic.com" in html or "wix-code" in html or "_wixCssModule" in html


def _has_contact_form(html: str) -> bool:
    """
    Check if static HTML contains a fillable contact form — a <form> with at least
    a textarea or a text input (not just a search or login form).
    """
    soup = BeautifulSoup(html, "html.parser")
    for form in soup.find_all("form"):
        if form.find("textarea"):
            return True
        for inp in form.find_all("input"):
            itype = (inp.get("type") or "text").lower()
            if itype in ("text", "email") and not any(
                kw in (inp.get("name") or inp.get("placeholder") or inp.get("id") or "").lower()
                for kw in ("search", "login", "username", "password", "zip", "postal", "coupon")
            ):
                return True
    return False


def _base_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def process_lead(lead: dict) -> dict:
    """
    Fetch a lead's website and extract contact info.
    Returns a dict of fields to update on the lead.
    """
    website = lead.get("website", "").strip()
    if not website:
        return {}

    # Skip non-business sites
    from urllib.parse import urlparse
    domain = urlparse(website).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if any(domain == d or domain.endswith("." + d) for d in SKIP_WEBSITE_DOMAINS):
        print(f"    Skipping non-business site: {domain}", file=sys.stderr)
        return {"website": ""}  # clear the junk URL

    updates = {}
    base = _base_url(website)

    # Pages to try in order: homepage, then common contact paths
    pages_to_try = [website] + [base + path for path in CONTACT_PATH_HINTS]
    contact_page_found = ""

    for page_url in pages_to_try:
        print(f"    Fetching: {page_url}", file=sys.stderr)
        html = apify_fetch.fetch(page_url, timeout=30)
        if html == "BLOCKED":
            if page_url == website:
                # Whole domain is blocked — no point trying any other paths
                break
            time.sleep(1)
            continue
        if not html:
            time.sleep(1)
            continue

        emails = _extract_emails(html)
        if emails:
            updates["contact_email"] = emails[0]
            if len(emails) > 1:
                updates["notes"] = f"extra emails: {', '.join(emails[1:])}"
            break

        # Pinterest check — e-commerce leads already on Pinterest aren't worth pitching
        if _has_pinterest(html):
            niche = lead.get("product_type", "")
            if niche in ECOMMERCE_NICHES:
                print(f"    → skip: e-commerce lead already has Pinterest", file=sys.stderr)
                return {"status": "dead", "notes": "already on Pinterest"}
            updates["pinterest_present"] = "Y"

        # Wix sites: forms are JS-only, Playwright can't submit them — skip contact URL
        if page_url == website and _is_wix_site(html):
            print(f"    → Wix site detected — email only, skipping contact form path", file=sys.stderr)
            break

        # Only store a contact page URL if a real fillable form exists in the HTML
        if not contact_page_found and page_url != website:
            if _has_contact_form(html):
                contact_page_found = page_url
            # If no form in static HTML, log but don't store — avoids wasted Playwright sessions

        # Find the contact page URL from homepage to try next
        if page_url == website and not contact_page_found:
            found = _find_contact_page_url(html, base)
            if found and found not in pages_to_try:
                pages_to_try.insert(1, found)

        time.sleep(1.0)

    if not updates.get("contact_email") and contact_page_found:
        updates["contact_page_url"] = contact_page_found
        updates["outreach_type"] = "contact-form"
    elif updates.get("contact_email"):
        updates["outreach_type"] = "email"

    return updates


def run(limit=None):
    from lead_tracker import _BAD_EMAIL_DOMAINS
    leads = get_leads_needing_contact_extraction()

    # Skip leads whose website is a known directory/platform domain
    def _is_bad_domain(url: str) -> bool:
        if not url:
            return False
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            if domain.endswith(".edu") or domain.endswith(".gov"):
                return True
            return any(domain == d or domain.endswith("." + d) for d in _BAD_EMAIL_DOMAINS)
        except Exception:
            return False

    leads = [l for l in leads if not _is_bad_domain(l.get("website", ""))]
    if limit:
        leads = leads[:limit]
    print(f"\n[Website Extractor] {len(leads)} leads to process", file=sys.stderr)

    updated = 0
    for lead in leads:
        business = lead.get("shop_or_business_name") or lead.get("website")
        print(f"  Processing: {business}", file=sys.stderr)
        updates = process_lead(lead)
        if updates:
            update_lead(lead["lead_id"], updates)
            updated += 1
            result = updates.get("contact_email") or updates.get("contact_page_url") or "no contact found"
            print(f"    → {result}", file=sys.stderr)
        time.sleep(1.5)

    print(f"\n[Website Extractor] Updated {updated}/{len(leads)} leads.", file=sys.stderr)
    try:
        from export_contacts import run as export_contacts
        export_contacts()
    except Exception as e:
        print(f"[Contacts Book] Export skipped: {e}", file=sys.stderr)
    return updated


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Max leads to process (default: all)")
    args = parser.parse_args()
    run(limit=args.limit)
