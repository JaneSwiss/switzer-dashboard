"""
Contacts Book Export — generates a clean, human-readable CSV of all qualified leads.

A "qualified lead" is any lead with a real email address OR a contact form URL.
This file is your permanent contacts record — open it in Google Sheets or Excel
to browse, search, filter, or export for manual outreach or email list building.

Output: outputs/leads/contacts-book.csv
Run after any session where new leads were added or messaged.

Usage:
    python3 skills/lead-gen-agent/export_contacts.py
"""

import sys
import csv
from pathlib import Path
from datetime import date

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from lead_tracker import load_leads, _is_sendable_email

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "outputs" / "leads" / "contacts-book.csv"

COLUMNS = [
    "business_name",
    "owner_name",
    "niche",
    "website",
    "email",
    "contact_form_url",
    "source",
    "messaged",
    "date_messaged",
    "response",
]


def _clean(val):
    return str(val).strip() if val and str(val).strip() not in ("", "nan") else ""


def run():
    leads = load_leads()

    rows = []
    for lead in leads:
        email       = _clean(lead.get("contact_email"))
        contact_url = _clean(lead.get("contact_page_url"))

        # Only include leads with real contact info
        if not email and not contact_url:
            continue

        # Skip generic/junk email addresses
        if email and not _is_sendable_email(email):
            email = ""

        # If nothing usable left, skip
        if not email and not contact_url:
            continue

        rows.append({
            "business_name":   _clean(lead.get("shop_or_business_name")) or _clean(lead.get("lead_id")),
            "owner_name":      _clean(lead.get("owner_name")),
            "niche":           _clean(lead.get("product_type")),
            "website":         _clean(lead.get("website")),
            "email":           email,
            "contact_form_url": contact_url,
            "source":          _clean(lead.get("source")),
            "messaged":        "yes" if lead.get("status") == "messaged" else "no",
            "date_messaged":   _clean(lead.get("outreach_date")),
            "response":        _clean(lead.get("response")),
        })

    # Sort: messaged first (most useful for follow-up context), then by niche
    rows.sort(key=lambda r: (r["messaged"] == "no", r["niche"], r["business_name"]))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    messaged = sum(1 for r in rows if r["messaged"] == "yes")
    not_yet  = sum(1 for r in rows if r["messaged"] == "no")
    has_email = sum(1 for r in rows if r["email"])
    has_form  = sum(1 for r in rows if r["contact_form_url"])

    print(f"\n[Contacts Book] {len(rows)} contacts exported to {OUTPUT_PATH}")
    print(f"  Already messaged: {messaged}")
    print(f"  Not yet contacted: {not_yet}")
    print(f"  Have email: {has_email}")
    print(f"  Have contact form URL: {has_form}")
    print(f"\n  Open in Google Sheets: File → Import → {OUTPUT_PATH.name}")


if __name__ == "__main__":
    run()
