"""
Daily Runner — automated end-to-end lead generation and email outreach pipeline.

Runs every step in sequence. Each step is isolated in its own try/except so a
failure in one (e.g. Hunter.io API down) does not abort later steps (e.g.
sending emails from already-drafted leads).

Schedule via Mac cron (run `crontab -e` and add):
  0 8 * * * /opt/homebrew/bin/python3 /Users/janeair/Documents/AI/switzertemplates/skills/lead-gen-agent/daily_runner.py >> /Users/janeair/Documents/AI/switzertemplates/outputs/leads/daily-runner.log 2>&1

Replace /opt/homebrew/bin/python3 with the output of `which python3`.

Also required:
  - System Settings → Privacy & Security → Full Disk Access → add /usr/sbin/cron
  - Mac must be awake at 8am (System Settings → Battery → Schedule or disable sleep)
"""

import os
import sys
import json
import argparse
import traceback
from datetime import date
from pathlib import Path

# Ensure the script's directory is on the path so imports work
sys.path.insert(0, str(Path(__file__).parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

PROJECT_ROOT   = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = PROJECT_ROOT / "dashboard_data.json"
LOG_PREFIX     = "[daily_runner]"


def _log(msg: str):
    import datetime
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts}  {msg}", flush=True)


def _section(title: str):
    _log(f"── {title} {'─' * max(0, 50 - len(title))}")


def _update_dashboard(sent_today: int):
    """Write lead gen stats to dashboard_data.json under the lead_gen_agent key."""
    try:
        from lead_tracker import load_leads
        leads = load_leads()

        total       = len(leads)
        contactable = sum(1 for l in leads if l.get("contact_email"))
        messaged    = sum(1 for l in leads if l.get("status") == "messaged")
        replied     = sum(1 for l in leads if l.get("status") in ("replied", "call", "paid"))

        data = {}
        if DASHBOARD_PATH.exists():
            try:
                data = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass

        data["lead_gen_agent"] = {
            "status":    "active",
            "last_run":  date.today().isoformat(),
            "stats": {
                "total_leads":  total,
                "contactable":  contactable,
                "messaged":     messaged,
                "replied":      replied,
                "sent_today":   sent_today,
            },
        }

        DASHBOARD_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _log(f"Dashboard updated — {total} leads, {contactable} contactable, {sent_today} sent today")
    except Exception as e:
        _log(f"[warn] Dashboard update failed: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-emails", action="store_true", help="Skip email draft generation and sending (forms only)")
    args = parser.parse_args()

    _log("═" * 60)
    _log("Daily lead gen run starting" + (" [emails skipped]" if args.skip_emails else ""))
    _log("═" * 60)

    sent_today = 0

    # ── Step 1 (disabled): Etsy Lead Finder — Apify Etsy actor broken ──────────

    # ── Step 2: Find new web / service-business leads ────────────────────────
    _section("Web Search Finder")
    try:
        import web_search_finder
        # 5 regular service (snippet emails) + 5 ecommerce + 65 intitle:contact = 75 queries total
        # intitle:contact returns the /contact page URL directly — skips extraction entirely
        # Directories (PT/Houzz/WW/Noomii) all blocked or JS-rendered — disabled 2026-06-16
        web_search_finder.run(service_sample=5, ecommerce_sample=5, intitle_sample=65)
    except Exception:
        _log("[error] Web Search Finder failed:")
        traceback.print_exc()

    # ── Step 3 (disabled): Directory Harvester ───────────────────────────────
    # PT/Houzz/WeddingWire/Noomii all blocked or JS-rendered — 0 leads on first run 2026-06-16.
    # intitle:contact search is the better approach for finding form-ready leads.

    # ── Step 4 (disabled): Website Contact Extractor ────────────────────────
    # intitle:contact gives us contact URLs directly — extraction is slow, costly,
    # and lower quality by comparison. Re-enable when needed for other lead sources.
    _log("Website Contact Extractor skipped (disabled — intitle:contact handles volume)")

    # ── Step 5: Hunter.io enrichment (only if enabled) ───────────────────────
    if os.getenv("HUNTER_ENRICHER_ENABLED", "false").lower() == "true":
        _section("Email Enricher (Hunter.io)")
        try:
            import email_enricher
            email_enricher.run()
        except Exception:
            _log("[error] Email Enricher failed:")
            traceback.print_exc()
    else:
        _log("Email Enricher skipped (set HUNTER_ENRICHER_ENABLED=true to enable)")

    # ── Step 6: Generate outreach drafts ─────────────────────────────────────
    _section("Outreach Generator — email")
    if args.skip_emails:
        _log("Email drafts skipped (--skip-emails)")
    else:
        try:
            import outreach_generator
            outreach_generator.run(limit=15, only_type="email")
        except Exception:
            _log("[error] Outreach Generator (email) failed:")
            traceback.print_exc()

    _section("Outreach Generator — contact forms")
    try:
        outreach_generator.run(limit=150, only_type="contact-form")
    except Exception:
        _log("[error] Outreach Generator (contact-form) failed:")
        traceback.print_exc()

    # ── Step 7: Send emails ───────────────────────────────────────────────────
    _section("Email Sender")
    if args.skip_emails:
        _log("Email sending skipped (--skip-emails)")
    else:
        try:
            import email_sender
            sent_today = email_sender.run(daily_limit=15)
        except Exception:
            _log("[error] Email Sender failed:")
            traceback.print_exc()

    # ── Step 8: Preview planned form submissions — Jane reviews before sending ─
    _section("Contact Form Preview (review before submitting)")
    try:
        import contact_form_sender
        from pathlib import Path as _Path
        planned = contact_form_sender.get_leads_for_contact_form(daily_limit=160)
        preview_path = PROJECT_ROOT / "outputs" / "leads" / f"planned-forms-{date.today().isoformat()}.txt"
        lines = [f"Planned form submissions — {date.today().isoformat()}", f"Total: {len(planned)}", ""]
        for i, lead in enumerate(planned, 1):
            domain = lead.get("website", "").replace("https://", "").replace("http://", "").rstrip("/")
            url    = lead.get("contact_page_url", "")
            niche  = lead.get("product_type", "")
            lines.append(f"{i:3}.  {domain}  |  {niche}  |  {url}")
        preview_path.write_text("\n".join(lines), encoding="utf-8")
        _log(f"Preview saved → {preview_path.name}  ({len(planned)} leads)")
        _log("Review the list, then tell me 'submit' to run the form sender.")
        for line in lines:
            _log(line)
    except Exception:
        _log("[error] Contact Form Preview failed:")
        traceback.print_exc()

    # ── Step 9: Update dashboard ──────────────────────────────────────────────
    _section("Dashboard Update")
    _update_dashboard(sent_today)

    _log("═" * 60)
    _log(f"Daily run complete — {sent_today} emails sent today")
    _log("═" * 60)


if __name__ == "__main__":
    main()
