"""
Email Enricher — uses Hunter.io domain-search API to find business email addresses
for leads that have a website but no contact_email yet.

Runs after website_contact_extractor.py as a second-pass fallback. Only active
when HUNTER_ENRICHER_ENABLED=true in .env (set this after upgrading to paid tier).

Free tier: 25 domain searches/month — enough to test before committing.
Paid (Starter): 500/month at $49/month.
"""

import os
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
from lead_tracker import get_leads_needing_enrichment, update_lead

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")
HUNTER_BASE    = "https://api.hunter.io/v2"

# Job titles that suggest the email belongs to the owner/decision-maker
_OWNER_TITLES = {"owner", "founder", "director", "ceo", "manager", "principal", "partner"}


def _extract_domain(url: str) -> str:
    """Extract bare domain from a URL, e.g. 'https://www.mybiz.com/about' → 'mybiz.com'."""
    try:
        netloc = urlparse(url).netloc.lower()
        domain = netloc.lstrip("www.")
        return domain if "." in domain else ""
    except Exception:
        return ""


def _search_domain(domain: str) -> list:
    """
    Call Hunter.io domain-search and return list of email result dicts.
    Each dict has: value, confidence, first_name, last_name, position.
    Returns [] on any error.
    """
    if not HUNTER_API_KEY:
        print("[warn] HUNTER_API_KEY not set — skipping enrichment", file=sys.stderr)
        return []
    try:
        resp = requests.get(
            f"{HUNTER_BASE}/domain-search",
            params={"domain": domain, "api_key": HUNTER_API_KEY, "limit": 10},
            timeout=15,
        )
        if resp.status_code == 401:
            print("  [Hunter.io] Invalid API key", file=sys.stderr)
            return []
        if resp.status_code == 429:
            print("  [Hunter.io] Rate limit hit — pausing 60s", file=sys.stderr)
            time.sleep(60)
            return []
        if resp.status_code != 200:
            print(f"  [Hunter.io] {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            return []
        return resp.json().get("data", {}).get("emails", [])
    except Exception as e:
        print(f"  [Hunter.io] Error: {e}", file=sys.stderr)
        return []


def _best_email(emails: list) -> tuple:
    """
    Pick the best email from Hunter.io results.
    Prefers owner/founder/director titles; falls back to highest confidence.
    Returns (email_address, owner_name) or ("", "").
    """
    confident = [e for e in emails if (e.get("confidence") or 0) >= 50]
    if not confident:
        return "", ""

    # Prefer owner-level contacts
    for e in confident:
        position = (e.get("position") or "").lower()
        if any(t in position for t in _OWNER_TITLES):
            name = " ".join(filter(None, [e.get("first_name"), e.get("last_name")])).strip()
            return e["value"], name

    # Fall back to highest-confidence email
    best = max(confident, key=lambda e: e.get("confidence", 0))
    name = " ".join(filter(None, [best.get("first_name"), best.get("last_name")])).strip()
    return best["value"], name


def run(limit=50):
    if not HUNTER_API_KEY:
        print("[Email Enricher] HUNTER_API_KEY not set — skipping.", file=sys.stderr)
        return 0

    leads = get_leads_needing_enrichment()
    if not leads:
        print("[Email Enricher] No leads need enrichment.", file=sys.stderr)
        return 0

    leads = leads[:limit]
    print(f"\n[Email Enricher] Processing {len(leads)} leads via Hunter.io", file=sys.stderr)

    enriched_count = 0
    for lead in leads:
        domain = _extract_domain(lead.get("website", ""))
        if not domain:
            continue

        business = lead.get("shop_or_business_name") or domain
        print(f"  {business} → {domain}", file=sys.stderr)

        emails = _search_domain(domain)
        email, owner_name = _best_email(emails)

        if email:
            updates = {"contact_email": email, "outreach_type": "email"}
            if owner_name and not lead.get("owner_name"):
                updates["owner_name"] = owner_name
            update_lead(lead["lead_id"], updates)
            print(f"    ✓ {email} (confidence: {next((e['confidence'] for e in emails if e['value'] == email), '?')}%)", file=sys.stderr)
            enriched_count += 1
        else:
            print(f"    — no email found", file=sys.stderr)

        time.sleep(1.5)

    print(f"\n[Email Enricher] {enriched_count} emails found.", file=sys.stderr)
    return enriched_count


if __name__ == "__main__":
    run()
