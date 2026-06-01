"""
Lead Gen Agent — main orchestrator.

Usage:
  python3 skills/lead-gen-agent/main.py --etsy-only      # find Etsy leads
  python3 skills/lead-gen-agent/main.py --ig-only        # find Instagram leads
  python3 skills/lead-gen-agent/main.py --web-only       # find web/Google leads
  python3 skills/lead-gen-agent/main.py --outreach       # write outreach messages for all leads
  python3 skills/lead-gen-agent/main.py --extract-only   # extract emails from websites
  python3 skills/lead-gen-agent/main.py --enrich         # Hunter.io email enrichment
  python3 skills/lead-gen-agent/main.py --send-emails    # send outreach emails via Gmail
  python3 skills/lead-gen-agent/main.py --serve          # open interactive tracker (mark as sent)
  python3 skills/lead-gen-agent/main.py                  # full run: find + extract + write messages

Run from project root:
  python3 skills/lead-gen-agent/main.py --etsy-only
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def open_report():
    from lead_tracker import load_leads
    import report
    leads = load_leads()
    if not leads:
        print("No leads yet.")
        return
    path = report.generate(leads, open_browser=True)
    print(f"\n[Report] Opened in browser: {path.name}")


def cmd_find(etsy=True, instagram=True, web=True):
    if etsy:
        print("\n── Etsy Lead Finder ─────────────────────────────")
        import etsy_lead_finder
        etsy_lead_finder.run()

    if instagram:
        print("\n── Instagram Lead Finder ────────────────────────")
        import instagram_lead_finder
        instagram_lead_finder.run()

    if web:
        print("\n── Web Search Finder ────────────────────────────")
        import web_search_finder
        web_search_finder.run()

    print("\n── Website Contact Extractor ────────────────────")
    import website_contact_extractor
    website_contact_extractor.run()

    print("\n── Email Enricher (Hunter.io) ───────────────────")
    import email_enricher
    email_enricher.run()


def cmd_extract():
    print("\n── Website Contact Extractor ────────────────────")
    import website_contact_extractor
    website_contact_extractor.run()


def cmd_enrich():
    print("\n── Email Enricher (Hunter.io) ───────────────────")
    import email_enricher
    email_enricher.run()


def cmd_send_emails(limit=20):
    print(f"\n── Email Sender (up to {limit} emails) ──────────")
    import email_sender
    email_sender.run(daily_limit=limit)


def cmd_outreach(limit=20):
    print(f"\n── Outreach Generator (top {limit} leads) ────────")
    import outreach_generator
    outreach_generator.run(limit=limit)


def main():
    parser = argparse.ArgumentParser(
        description="Switzertemplates Lead Gen Agent — find and contact Pinterest service leads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("--outreach", action="store_true",
                        help="Generate personalised outreach drafts for top leads")
    parser.add_argument("--limit", type=int, default=20,
                        help="Number of leads to generate outreach for (default: 20)")
    parser.add_argument("--etsy-only", action="store_true", help="Run Etsy finder only")
    parser.add_argument("--ig-only", action="store_true", help="Run Instagram finder only")
    parser.add_argument("--web-only", action="store_true", help="Run web search finder only")
    parser.add_argument("--extract-only", action="store_true",
                        help="Run website contact extractor only (on existing leads)")
    parser.add_argument("--enrich", action="store_true",
                        help="Run Hunter.io email enricher on leads with websites but no email")
    parser.add_argument("--send-emails", action="store_true",
                        help="Send outreach emails via Gmail to leads with contact_email (max 20/day)")
    parser.add_argument("--stats", action="store_true", help="Open static lead report")
    parser.add_argument("--serve", action="store_true",
                        help="Start interactive tracker on localhost:8765 (mark leads as sent)")

    args = parser.parse_args()

    if args.serve or args.stats:
        import report_server
        report_server.serve()
        return

    if args.outreach:
        cmd_outreach(limit=args.limit)
        open_report()
        return

    if args.extract_only:
        cmd_extract()
        open_report()
        return

    if args.enrich:
        cmd_enrich()
        open_report()
        return

    if args.send_emails:
        cmd_send_emails(limit=args.limit)
        open_report()
        return

    if args.etsy_only:
        cmd_find(etsy=True, instagram=False, web=False)
        open_report()
        return

    if args.ig_only:
        cmd_find(etsy=False, instagram=True, web=False)
        open_report()
        return

    if args.web_only:
        cmd_find(etsy=False, instagram=False, web=True)
        open_report()
        return

    # Default: full run
    cmd_find(etsy=True, instagram=True, web=True)
    open_report()


if __name__ == "__main__":
    main()
