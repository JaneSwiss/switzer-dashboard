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
    _log("═" * 60)
    _log("Daily lead gen run starting")
    _log("═" * 60)

    sent_today = 0

    # ── Step 1: Find new Etsy leads ───────────────────────────────────────────
    _section("Etsy Lead Finder")
    try:
        import etsy_lead_finder
        etsy_lead_finder.run()
    except Exception:
        _log("[error] Etsy Lead Finder failed:")
        traceback.print_exc()

    # ── Step 2: Find new Instagram leads ─────────────────────────────────────
    _section("Instagram Lead Finder")
    try:
        import instagram_lead_finder
        instagram_lead_finder.run()
    except Exception:
        _log("[error] Instagram Lead Finder failed:")
        traceback.print_exc()

    # ── Step 3: Find new web / service-business leads ────────────────────────
    _section("Web Search Finder")
    try:
        import web_search_finder
        web_search_finder.run()
    except Exception:
        _log("[error] Web Search Finder failed:")
        traceback.print_exc()

    # ── Step 4: Scrape websites for contact emails ───────────────────────────
    _section("Website Contact Extractor")
    try:
        import website_contact_extractor
        website_contact_extractor.run()
    except Exception:
        _log("[error] Website Contact Extractor failed:")
        traceback.print_exc()

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
    _section("Outreach Generator")
    try:
        import outreach_generator
        outreach_generator.run(limit=30)
    except Exception:
        _log("[error] Outreach Generator failed:")
        traceback.print_exc()

    # ── Step 7: Send emails ───────────────────────────────────────────────────
    _section("Email Sender")
    try:
        import email_sender
        sent_today = email_sender.run(daily_limit=15)
    except Exception:
        _log("[error] Email Sender failed:")
        traceback.print_exc()

    # ── Step 8: Update dashboard ──────────────────────────────────────────────
    _section("Dashboard Update")
    _update_dashboard(sent_today)

    _log("═" * 60)
    _log(f"Daily run complete — {sent_today} emails sent today")
    _log("═" * 60)


if __name__ == "__main__":
    main()
