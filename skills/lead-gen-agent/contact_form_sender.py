"""
Contact Form Sender — submits outreach drafts via business website contact forms.

Uses Playwright (headless Chromium) to handle JS-rendered forms reliably.
Falls back gracefully if the form can't be found or submitted.

Usage:
    python3 contact_form_sender.py --limit 15
    python3 contact_form_sender.py --dry-run --limit 5
"""

import csv
import os
import re
import sys
import glob
import time
import argparse
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from lead_tracker import load_leads, update_lead, record_sent_email, _load_sent_emails, _is_sendable_email

DRAFTS_DIR = Path(__file__).resolve().parents[2] / "outputs" / "leads" / "outreach-drafts"
SENDER_NAME  = "Jane"
SENDER_EMAIL = os.getenv("GMAIL_ADDRESS", "hello@switzertemplates.com")

# Field name patterns to detect name / email / message inputs
_NAME_HINTS    = {"name", "your-name", "fullname", "full_name", "fname", "first_name",
                  "contact_name", "yourname", "author"}
_EMAIL_HINTS   = {"email", "your-email", "email_address", "mail", "e-mail",
                  "contact_email", "emailaddress"}
_MESSAGE_HINTS = {"message", "your-message", "msg", "comment", "comments", "body",
                  "content", "enquiry", "inquiry", "description", "text"}
_SUBJECT_HINTS = {"subject", "your-subject", "topic"}


def _load_draft(lead_id: str) -> str:
    """Return body text from a contact-form draft, or '' if not found."""
    pattern = str(DRAFTS_DIR / f"{lead_id}-*-contact-form.txt")
    matches = glob.glob(pattern)
    if not matches:
        return ""
    text = Path(matches[0]).read_text(encoding="utf-8")
    sep = "─" * 60
    return text.split(sep, 1)[1].strip() if sep in text else ""


def _get_contact_url(lead: dict) -> str:
    """Return the best URL to load for the contact form."""
    return (lead.get("contact_page_url") or "").strip()


def _field_combined(inp) -> tuple[str, str]:
    """Return (combined_string, itype) for an input element, including bracket-content from Shopify names."""
    name        = (inp.get_attribute("name")        or "").lower()
    itype       = (inp.get_attribute("type")        or "text").lower()
    placeholder = (inp.get_attribute("placeholder") or "").lower()
    id_attr     = (inp.get_attribute("id")          or "").lower()
    # Shopify uses contact[Name], contact[email], contact[Comment] — extract inner word
    bracket = ""
    m = re.search(r'\[([^\]]+)\]', name)
    if m:
        bracket = m.group(1).lower()
    combined = " ".join([name, placeholder, id_attr, bracket])
    return combined, itype


def _submit_form(page, body: str) -> str:
    """
    Find and fill the contact form on the current page, then submit.

    Returns:
      "success"     — form found, filled, and submitted
      "no-form"     — no usable form on the page (Type 1 — not worth manual attempt)
      "fill-failed" — form found but couldn't be filled/submitted (Type 2 — worth manual attempt)
    """
    try:
        page.wait_for_selector("form", state="attached", timeout=12000)
    except Exception:
        print("    [form] No <form> element found on page", file=sys.stderr)
        return "no-form"

    forms = page.query_selector_all("form")
    if not forms:
        return "no-form"

    best_form  = None
    best_score = 0
    for form in forms:
        inputs = form.query_selector_all("input, textarea, select")
        score  = 0
        for inp in inputs:
            combined, itype = _field_combined(inp)
            if any(h in combined for h in _MESSAGE_HINTS): score += 3
            if any(h in combined for h in _EMAIL_HINTS):   score += 2
            if any(h in combined for h in _NAME_HINTS):    score += 1
            if itype == "email":                            score += 2
            if itype == "submit":                           score -= 1
        if score > best_score:
            best_score = score
            best_form  = form

    if not best_form or best_score < 1:
        print(f"    [form] Best score was {best_score} — no suitable contact form found", file=sys.stderr)
        return "no-form"

    filled_message = False
    inputs = best_form.query_selector_all("input, textarea, select")
    for inp in inputs:
        combined, itype = _field_combined(inp)

        if itype in ("submit", "button", "hidden", "checkbox", "radio"):
            continue
        if itype == "file":
            continue

        tag = "INPUT"
        try:
            tag = inp.evaluate("el => el.tagName")
        except Exception:
            pass

        def _fill(el, value):
            try:
                el.fill(value)
                return True
            except Exception:
                try:
                    el.evaluate(
                        "(el, v) => { el.value = v; "
                        "el.dispatchEvent(new Event('input', {bubbles:true})); "
                        "el.dispatchEvent(new Event('change', {bubbles:true})); }",
                        value,
                    )
                    return True
                except Exception:
                    return False

        if any(h in combined for h in _NAME_HINTS) and not filled_message:
            if not any(h in combined for h in _MESSAGE_HINTS):
                _fill(inp, SENDER_NAME)
        elif any(h in combined for h in _EMAIL_HINTS) or itype == "email":
            _fill(inp, SENDER_EMAIL)
        elif (any(h in combined for h in _MESSAGE_HINTS) or tag == "TEXTAREA") \
                and "recaptcha" not in combined:
            if _fill(inp, body):
                filled_message = True
        elif any(h in combined for h in _SUBJECT_HINTS):
            _fill(inp, "Pinterest strategy for your business")
        elif any(h in combined for h in _NAME_HINTS):
            _fill(inp, SENDER_NAME)

    if not filled_message:
        textarea = best_form.query_selector("textarea:not([name*='recaptcha']):not([name*='g-recaptcha'])")
        if textarea:
            try:
                textarea.fill(body)
                filled_message = True
            except Exception:
                pass

    if not filled_message:
        print("    [form] Form found but could not fill message field", file=sys.stderr)
        return "fill-failed"

    try:
        best_form.evaluate("f => f.requestSubmit()")
    except Exception:
        submit_btn = best_form.query_selector("button[type=submit], input[type=submit], button:not([type])")
        if submit_btn:
            try:
                submit_btn.click(force=True)
            except Exception:
                best_form.evaluate("f => f.submit()")
        else:
            best_form.evaluate("f => f.submit()")

    time.sleep(2)
    return "success"


def _is_bad_contact_domain(url: str) -> bool:
    from lead_tracker import _BAD_EMAIL_DOMAINS
    from urllib.parse import urlparse
    if not url:
        return True
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return any(domain == d or domain.endswith("." + d) for d in _BAD_EMAIL_DOMAINS)
    except Exception:
        return True


MANUAL_FORMS_CSV = Path(__file__).resolve().parents[2] / "outputs" / "leads" / "manual-forms.csv"
_MANUAL_FIELDNAMES = ["lead_id", "business_name", "niche", "website", "contact_form_url", "draft_file"]


def _write_manual_csv(lead: dict):
    """Append a Type-2 failure (form found, fill failed) to the manual submission CSV."""
    draft_files = glob.glob(str(DRAFTS_DIR / f"{lead['lead_id']}-*-contact-form.txt"))
    row = {
        "lead_id":          lead["lead_id"],
        "business_name":    lead.get("shop_or_business_name", ""),
        "niche":            lead.get("product_type", ""),
        "website":          lead.get("website", ""),
        "contact_form_url": lead.get("contact_page_url", ""),
        "draft_file":       draft_files[0] if draft_files else "",
    }
    existing_ids = set()
    write_header = not MANUAL_FORMS_CSV.exists()
    if MANUAL_FORMS_CSV.exists():
        with open(MANUAL_FORMS_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existing_ids.add(r.get("lead_id", ""))
    if row["lead_id"] in existing_ids:
        return  # already logged
    with open(MANUAL_FORMS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_MANUAL_FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def get_leads_for_contact_form(daily_limit: int = 20):
    """Return leads with a contact_page_url, not yet contacted, sorted by priority."""
    sent_log = Path(Path(__file__).resolve().parents[2] / "outputs/leads/sent-emails.log")
    sent_ids = set()
    if sent_log.exists():
        for line in sent_log.read_text(encoding="utf-8").splitlines():
            parts = line.split("|")
            if len(parts) >= 2:
                sent_ids.add(parts[1])

    leads = load_leads()
    eligible = [
        l for l in leads
        if l.get("contact_page_url")
        and not _is_bad_contact_domain(l.get("contact_page_url", ""))
        and not l.get("contact_email")
        and l.get("status") not in ("messaged", "replied", "paid", "dead")
        and not l.get("outreach_date")
        and "form-failed" not in (l.get("notes") or "")
        and l["lead_id"] not in sent_ids
        and glob.glob(str(DRAFTS_DIR / f"{l['lead_id']}-*-contact-form.txt"))
    ]
    eligible.sort(key=lambda l: float(l.get("priority_score") or 0), reverse=True)
    return eligible[:daily_limit]


def run(daily_limit: int = 20, dry_run: bool = False):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[Contact Form Sender] Playwright not installed. Run: pip3 install playwright && python3 -m playwright install chromium", file=sys.stderr)
        return 0

    leads = get_leads_for_contact_form(daily_limit=daily_limit)
    if not leads:
        print("[Contact Form Sender] No leads ready for contact form outreach.", file=sys.stderr)
        return 0

    print(f"\n[Contact Form Sender] {len(leads)} forms to submit (limit: {daily_limit})", file=sys.stderr)
    if dry_run:
        print("  [DRY RUN — no forms will be submitted]", file=sys.stderr)

    sent_count = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        # Hide the webdriver flag — prevents Cloudflare and other bot detectors from blocking
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        for i, lead in enumerate(leads):
            lead_id  = lead["lead_id"]
            business = lead.get("shop_or_business_name") or lead_id
            url      = _get_contact_url(lead)
            body     = _load_draft(lead_id)

            if not url or not body:
                print(f"  Skip {business} — missing contact URL or draft", file=sys.stderr)
                continue

            print(f"  Submitting to {business} ({url})", file=sys.stderr)

            if dry_run:
                print(f"    [dry-run] Would submit form at: {url}", file=sys.stderr)
                print(f"    [dry-run] Body preview: {body[:80]}...", file=sys.stderr)
                sent_count += 1
                continue

            try:
                page = context.new_page()
                page.goto(url, timeout=20000, wait_until="domcontentloaded")
                # Wait for JS to finish rendering forms (Wix, Squarespace, etc.)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                result = _submit_form(page, body)
                page.close()
            except Exception as e:
                print(f"    ✗ Error: {e}", file=sys.stderr)
                result = "no-form"

            if result == "success":
                record_sent_email(f"form:{lead_id}", lead_id, business)
                update_lead(lead_id, {
                    "status":        "messaged",
                    "outreach_date": date.today().isoformat(),
                    "outreach_type": "contact-form",
                })
                sent_count += 1
                print(f"    ✓ Submitted", file=sys.stderr)
            elif result == "fill-failed":
                # Type 2 — form exists but couldn't fill: add to manual CSV for Jane
                _write_manual_csv(lead)
                existing_notes = lead.get("notes") or ""
                if "form-failed" not in existing_notes:
                    update_lead(lead_id, {"notes": (existing_notes + " form-failed").strip()})
                print(f"    ✗ Added to manual-forms.csv", file=sys.stderr)
            else:
                # Type 1 — no form on page: mark failed, skip in future
                existing_notes = lead.get("notes") or ""
                if "form-failed" not in existing_notes:
                    update_lead(lead_id, {"notes": (existing_notes + " form-failed").strip()})
                print(f"    ✗ No form found", file=sys.stderr)

            if i < len(leads) - 1:
                time.sleep(3)

        browser.close()

    print(f"\n[Contact Form Sender] {sent_count} forms submitted.", file=sys.stderr)
    try:
        from export_contacts import run as export_contacts
        export_contacts()
    except Exception as e:
        print(f"[Contacts Book] Export skipped: {e}", file=sys.stderr)
    return sent_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    run(daily_limit=args.limit, dry_run=args.dry_run)
