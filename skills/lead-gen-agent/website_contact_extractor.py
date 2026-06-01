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
    domain = urlparse(website).netloc.lower().lstrip("www.")
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
        if not html:
            time.sleep(1)
            continue

        emails = _extract_emails(html)
        if emails:
            updates["contact_email"] = emails[0]
            if len(emails) > 1:
                updates["notes"] = f"extra emails: {', '.join(emails[1:])}"
            break

        # Track contact page URL for manual follow-up even if no email found
        if not contact_page_found and page_url != website:
            contact_page_found = page_url

        # Check for Pinterest link on their site
        if _has_pinterest(html) and not lead.get("pinterest_url"):
            updates["pinterest_present"] = "Y"

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


def run():
    leads = get_leads_needing_contact_extraction()
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
    return updated


if __name__ == "__main__":
    run()
