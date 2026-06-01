"""
Email Sender — sends personalised cold outreach emails via Gmail SMTP.

Reads draft files from outputs/leads/outreach-drafts/*-email.txt, parses
subject line and body, sends via Gmail App Password auth, then marks the
lead as messaged in the tracker.

Limits: 20 emails/day max, 30s delay between sends — safe for Gmail.

Setup required in .env:
  GMAIL_ADDRESS=jane@youremail.com
  GMAIL_APP_PASSWORD=abcdefghijklmnop   (16-char App Password, no spaces)
"""

import os
import sys
import time
import glob
import smtplib
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from lead_tracker import get_leads_for_email_sending, update_lead

GMAIL_ADDRESS      = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
SMTP_HOST          = "smtp.gmail.com"
SMTP_PORT          = 587
DAILY_LIMIT        = 20
SEND_DELAY_SECS    = 30
DRAFTS_DIR         = Path(__file__).resolve().parents[2] / "outputs" / "leads" / "outreach-drafts"


def _load_draft(lead_id: str) -> tuple:
    """
    Find the email draft file for this lead and parse subject + body.
    Returns (subject, body) or ("", "") if not found.
    """
    pattern = str(DRAFTS_DIR / f"{lead_id}-*-email.txt")
    matches = glob.glob(pattern)
    if not matches:
        return "", ""

    text = Path(matches[0]).read_text(encoding="utf-8")

    # Parse subject from header block (line starting with "Subject:")
    subject = ""
    for line in text.splitlines():
        if line.startswith("Subject:"):
            subject = line.split("Subject:", 1)[1].strip()
            break

    # Body is everything after the ─── separator line
    separator = "─" * 60
    if separator in text:
        body = text.split(separator, 1)[1].strip()
    else:
        body = ""

    return subject, body


def _send_one(to_addr: str, subject: str, body: str, dry_run: bool = False) -> bool:
    """
    Send a single email. Each call opens and closes its own SMTP connection
    so long delays between sends don't cause timeouts.
    Returns True on success, False on error.
    """
    if dry_run:
        print(f"    [dry-run] Would send to: {to_addr}", file=sys.stderr)
        print(f"    [dry-run] Subject: {subject}", file=sys.stderr)
        print(f"    [dry-run] Body preview: {body[:80]}...", file=sys.stderr)
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, to_addr, msg.as_string())
        return True
    except smtplib.SMTPAuthenticationError:
        print("  [Gmail] Authentication failed — check GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [Gmail] Send error to {to_addr}: {e}", file=sys.stderr)
        return False


def run(daily_limit: int = DAILY_LIMIT, dry_run: bool = False):
    if not dry_run:
        if not GMAIL_ADDRESS:
            print("[Email Sender] GMAIL_ADDRESS not set in .env — aborting.", file=sys.stderr)
            return 0
        if not GMAIL_APP_PASSWORD:
            print("[Email Sender] GMAIL_APP_PASSWORD not set in .env — aborting.", file=sys.stderr)
            return 0

    leads = get_leads_for_email_sending(daily_limit=daily_limit)
    if not leads:
        print("[Email Sender] No leads ready to email.", file=sys.stderr)
        return 0

    print(f"\n[Email Sender] {len(leads)} emails to send (limit: {daily_limit})", file=sys.stderr)
    if dry_run:
        print("  [DRY RUN — no emails will be sent]", file=sys.stderr)

    sent_count = 0
    for i, lead in enumerate(leads):
        lead_id  = lead["lead_id"]
        to_addr  = lead["contact_email"]
        business = lead.get("shop_or_business_name") or lead_id

        subject, body = _load_draft(lead_id)
        if not subject or not body:
            print(f"  Skip {business} — no email draft found", file=sys.stderr)
            continue

        print(f"  Sending to {to_addr} ({business})", file=sys.stderr)
        success = _send_one(to_addr, subject, body, dry_run=dry_run)

        if success:
            if not dry_run:
                update_lead(lead_id, {
                    "status":        "messaged",
                    "outreach_date": date.today().isoformat(),
                    "outreach_type": "email",
                })
            sent_count += 1
            print(f"    ✓ Sent", file=sys.stderr)
        else:
            print(f"    ✗ Failed", file=sys.stderr)

        # Delay between sends (skip after last one)
        if i < len(leads) - 1 and not dry_run:
            time.sleep(SEND_DELAY_SECS)

    print(f"\n[Email Sender] {sent_count} emails sent.", file=sys.stderr)
    return sent_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be sent without actually sending")
    parser.add_argument("--limit", type=int, default=DAILY_LIMIT,
                        help=f"Max emails to send (default: {DAILY_LIMIT})")
    args = parser.parse_args()
    run(daily_limit=args.limit, dry_run=args.dry_run)
