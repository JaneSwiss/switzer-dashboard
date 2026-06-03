"""
Lead tracker — shared CSV read/write utility for all lead-gen scripts.
All scripts append to the same outputs/leads/lead-tracker.csv.
"""

import csv
import os
import uuid
from datetime import date
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "outputs" / "leads"
TRACKER_PATH = OUTPUT_DIR / "lead-tracker.csv"

COLUMNS = [
    "lead_id",
    "date_found",
    "source",           # etsy / instagram / google / bing
    "owner_name",
    "shop_or_business_name",
    "etsy_url",
    "website",
    "instagram_handle",
    "facebook",
    "other_social",
    "contact_email",
    "contact_page_url",
    "pinterest_present",   # Y / N
    "pinterest_url",
    "product_type",
    "sales_count",         # Etsy only
    "follower_count",      # Instagram only
    "priority_score",
    "outreach_type",       # DM / email / contact-form
    "outreach_date",
    "response",            # Y / N / pending
    "status",              # found / qualified / messaged / replied / call / paid
    "notes",
]


def _ensure_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _write_header():
    with open(TRACKER_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()


def load_leads():
    """Return all leads as a list of dicts. Creates file if missing."""
    _ensure_dir()
    if not TRACKER_PATH.exists():
        _write_header()
        return []
    with open(TRACKER_PATH, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_leads(leads):
    """Overwrite the tracker with the given list of lead dicts."""
    _ensure_dir()
    with open(TRACKER_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(leads)


def append_leads(new_leads):
    """
    Append new leads to the tracker, skipping duplicates.
    Deduplication: same etsy_url OR same instagram_handle OR same contact_email.
    Returns count of actually appended leads.
    """
    existing = load_leads()

    existing_etsy = {r["etsy_url"] for r in existing if r.get("etsy_url")}
    existing_ig   = {r["instagram_handle"] for r in existing if r.get("instagram_handle")}
    existing_email = {r["contact_email"] for r in existing if r.get("contact_email")}

    added = 0
    for lead in new_leads:
        etsy_url = lead.get("etsy_url", "")
        ig       = lead.get("instagram_handle", "")
        email    = lead.get("contact_email", "")

        if (etsy_url and etsy_url in existing_etsy) or \
           (ig and ig in existing_ig) or \
           (email and email in existing_email):
            continue

        # Fill in defaults
        lead.setdefault("lead_id", str(uuid.uuid4())[:8])
        lead.setdefault("date_found", date.today().isoformat())
        lead.setdefault("status", "found")
        lead.setdefault("response", "pending")
        lead.setdefault("priority_score", "")

        # Normalise all columns
        row = {col: lead.get(col, "") for col in COLUMNS}
        existing.append(row)

        if etsy_url:
            existing_etsy.add(etsy_url)
        if ig:
            existing_ig.add(ig)
        if email:
            existing_email.add(email)

        added += 1

    save_leads(existing)
    return added


def update_lead(lead_id, updates: dict):
    """Update fields on a single lead by lead_id."""
    leads = load_leads()
    for lead in leads:
        if lead.get("lead_id") == lead_id:
            lead.update(updates)
            break
    save_leads(leads)


def get_leads_needing_contact_extraction():
    """Return leads that have a website URL but no email and no contact page yet."""
    leads = load_leads()
    return [
        l for l in leads
        if l.get("website")
        and not l.get("contact_email")
        and not l.get("contact_page_url")
    ]


def get_leads_for_outreach(limit=200):
    """Return leads ready for outreach that don't have a draft file yet, sorted by priority."""
    from pathlib import Path
    drafts_dir = OUTPUT_DIR / "outreach-drafts"
    existing_drafts = set()
    if drafts_dir.exists():
        for f in drafts_dir.iterdir():
            lead_id = f.name.split("-")[0]
            existing_drafts.add(lead_id)

    leads = load_leads()
    eligible = [
        l for l in leads
        if l.get("status") in ("found", "qualified")
        and not l.get("outreach_date")
        and l.get("lead_id") not in existing_drafts
    ]
    eligible.sort(key=lambda l: float(l.get("priority_score") or 0), reverse=True)
    return eligible[:limit]


def get_leads_needing_enrichment():
    """Return leads with a website but no contact_email — Hunter.io targets."""
    leads = load_leads()
    return [
        l for l in leads
        if l.get("website")
        and not l.get("contact_email")
    ]


_BAD_EMAIL_PREFIXES = {
    "hiring", "jobs", "recruitment", "careers", "noreply", "no-reply",
    "board", "support", "info.board", "medicalrecords", "billing",
    "frontdesk", "reception.desk",
}

_BAD_EMAIL_DOMAINS = {
    # Directories and booking platforms
    "psychologytoday.com", "therapyden.com", "therapytribe.com", "getfyt.com",
    "fresha.com", "aedit.com", "noomii.com", "zencare.co", "healthprofs.com",
    "zocdoc.com", "yellowpages.com", "yelp.com", "thumbtack.com", "bark.com",
    "weddingwire.com", "theknot.com", "lessons.com", "mentalhealthmatch.com",
    "booksy.com", "naturaltherapypages.com.au",
    # Corporate chains and large organisations
    "wellbridge.com", "thriveworks.com", "dalecarnegie.com",
    "ymca.org", "ymcasd.org", "ymcacnm.org", "ymcanyc.org",
    "facefoundrie.com", "oasisfacebar.com", "heydayskincare.com",
    "actioncoach.com", "actioncoach.co.uk", "actioncoach.us",
    "polsky.uchicago.edu", "lifestance.com",
    # Nonprofits and community orgs
    "cclconnect.org", "altarcommunity.com",
    # Fake / placeholder
    "mailservice.com", "example.com",
}


def _is_sendable_email(email: str) -> bool:
    """Return True if the email looks like a real business owner inbox."""
    if not email:
        return False
    # Clean URL-encoded or stray characters sometimes scraped from mailto links
    email = email.strip().lstrip("%20").lstrip(":").lstrip("%20%20")
    if "@" not in email:
        return False
    prefix, domain = email.rsplit("@", 1)
    domain = domain.lower().strip()
    prefix = prefix.lower().strip()

    # Skip university and government addresses
    if domain.endswith(".edu") or domain.endswith(".gov"):
        return False

    # Skip known bad prefixes (handle "bbht.board" by checking last segment too)
    prefix_last = prefix.split(".")[-1]
    if prefix in _BAD_EMAIL_PREFIXES or prefix_last in _BAD_EMAIL_PREFIXES:
        return False

    # Skip known directory/platform domains
    if any(domain == d or domain.endswith("." + d) for d in _BAD_EMAIL_DOMAINS):
        return False

    return True


SENT_LOG_PATH = OUTPUT_DIR / "sent-emails.log"


def _load_sent_emails() -> set:
    """Return set of all email addresses that have ever been sent to (append-only log)."""
    if not SENT_LOG_PATH.exists():
        return set()
    lines = SENT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    return {line.split("|")[0].strip().lower() for line in lines if line.strip()}


def record_sent_email(email: str, lead_id: str, business: str):
    """Append one line to the sent log. Never overwrites — safe against CSV race conditions."""
    _ensure_dir()
    from datetime import date
    line = f"{email.lower()}|{lead_id}|{business}|{date.today().isoformat()}\n"
    with open(SENT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)


def get_leads_for_email_sending(daily_limit=20):
    """Return leads with a sendable contact_email not yet sent to, sorted by priority."""
    already_sent = _load_sent_emails()
    leads = load_leads()
    eligible = [
        l for l in leads
        if _is_sendable_email(l.get("contact_email", ""))
        and l.get("status") not in ("messaged", "replied", "paid")
        and not l.get("outreach_date")
        and l.get("contact_email", "").lower() not in already_sent
    ]
    eligible.sort(key=lambda l: float(l.get("priority_score") or 0), reverse=True)
    return eligible[:daily_limit]
