"""
Pinterest Audit Client — main entry point.

Usage:
  python3 skills/pinterest-audit-client/main.py
  python3 skills/pinterest-audit-client/main.py \\
    --niche "wellness coaching branding" \\
    --products "branding kits, Wix websites, Canva templates" \\
    --competitors "designpixiestore saffronavenue" \\
    --keywords 15
"""

from __future__ import annotations
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone


# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
dotenv_path = PROJECT_ROOT / ".env"
if dotenv_path.exists():
    with open(dotenv_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

sys.path.insert(0, str(Path(__file__).parent))

from keyword_research import run_keyword_research
from niche_research import research_niche_overview
from reddit_research import run_reddit_research
from trend_research import run_trend_research
from report_builder import assemble_report, save_report
from html_export import save_html
from pdf_export import export_pdf


def parse_args():
    parser = argparse.ArgumentParser(description="Pinterest Client Niche Audit")
    parser.add_argument("--niche", type=str, help="Client niche description")
    parser.add_argument("--products", type=str, help="Client products or services")
    parser.add_argument("--client", type=str, help="Client business name (used in report header, e.g. 'SwitzerTemplates')")
    parser.add_argument("--competitors", type=str, help="Known competitor handles (space-separated)")
    parser.add_argument("--keywords", type=int, default=15, help="Number of top keywords (default: 15)")
    parser.add_argument("--seed-keywords", type=str, help="Comma-separated seed keywords (optional)")
    return parser.parse_args()


def prompt_input(label: str) -> str:
    return input(f"{label}: ").strip()


def main():
    args = parse_args()

    print("\n" + "=" * 60)
    print("  PINTEREST CLIENT AUDIT")
    print("=" * 60)

    if args.niche:
        niche = args.niche
        products = args.products or niche
        client_name = args.client or ""
        manual_competitors = args.competitors.split() if args.competitors else []
        seed_keywords = [k.strip() for k in args.seed_keywords.split(",")] if args.seed_keywords else None
    else:
        print("\nInteractive mode.\n")
        niche = prompt_input("Client niche (e.g. 'wellness coaching branding')")
        products = prompt_input("Client products/services") or niche
        client_name = prompt_input("Client business name for report header (e.g. 'SwitzerTemplates', or leave blank)")
        competitors_raw = prompt_input("Known competitor handles (space-separated, or leave blank)")
        manual_competitors = competitors_raw.split() if competitors_raw else []
        seed_raw = prompt_input("Seed keywords (comma-separated, or leave blank for auto-generation)")
        seed_keywords = [k.strip() for k in seed_raw.split(",")] if seed_raw else None

    if not niche:
        print("Error: niche is required.")
        sys.exit(1)

    print(f"\nNiche: {niche}")
    print(f"Products: {products}")
    print(f"Manual competitors: {manual_competitors or 'none — will auto-discover'}\n")

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Phase 1 — Keyword research
    keywords = run_keyword_research(niche, products, seed_keywords)

    # Phase 2 — Niche overview
    niche_overview = research_niche_overview(niche, products, keywords)

    # Phase 3 — Reddit/Quora
    questions = run_reddit_research(niche, products)

    # Phase 4 — Trends + 2026 strategy
    trend_content = run_trend_research(niche, products, keywords)

    # Phase 5 — Report assembly
    report = assemble_report(
        niche=niche,
        products=products,
        keywords=keywords,
        questions=questions,
        trend_content=trend_content,
        niche_overview=niche_overview,
        run_date=run_date,
    )

    output_path = save_report(report, niche)
    html_path = save_html(output_path, client_name=client_name)
    pdf_path = export_pdf(Path(output_path))

    print("\n" + "=" * 60)
    print("  AUDIT COMPLETE")
    print("=" * 60)
    print(f"\nMarkdown: {output_path}")
    print(f"HTML:     {html_path}")
    print(f"PDF:      {pdf_path}\n")
    print(f"Keywords researched: {len([k for k in keywords if (k.get('volume') or 0) > 0])}")
    print(f"Reddit/Quora questions: {len(questions)}")
    print()


if __name__ == "__main__":
    main()
