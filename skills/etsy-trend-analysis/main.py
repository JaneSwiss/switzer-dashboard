"""
Switzertemplates - Etsy Trend Analysis
=======================================
Run: python3 skills/etsy-trend-analysis/main.py
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from csv_analyzer import load_all_csvs
from trend_engine import (
    analyze_own_shop,
    get_top_keywords,
    get_product_gaps,
    get_market_insights,
    get_market_product_opportunities,
)
from report_writer import write_report


def sep(label):
    print(f"\n{'─' * 52}")
    print(f"  {label}")
    print(f"{'─' * 52}")


def run():
    print("\n Switzertemplates — Etsy Trend Analysis")
    print("=" * 52)

    # ── Step 1: Load CSVs ─────────────────────────────
    sep("Step 1: Loading Everbee CSV data")
    keyword_df, own_shop_df, market_df = load_all_csvs()

    csv_files = []
    if not keyword_df.empty:
        csv_files += keyword_df["source_file"].unique().tolist()
        print(f"  Keywords:        {len(keyword_df)} rows")
    else:
        print("  Keywords:        none loaded")

    if not own_shop_df.empty:
        for f in own_shop_df["source_file"].unique():
            if f not in csv_files: csv_files.append(f)
        print(f"  Own shop data:   {len(own_shop_df)} listings")
    else:
        print("  Own shop data:   none loaded")

    if not market_df.empty:
        for f in market_df["source_file"].unique():
            if f not in csv_files: csv_files.append(f)
        print(f"  Market data:     {len(market_df)} competitor listings")
    else:
        print("  Market data:     none loaded")

    # ── Step 2: Analysis ──────────────────────────────
    sep("Step 2: Running analysis")

    print("  Analysing own shop performance...")
    shop_stats = analyze_own_shop(own_shop_df)
    if shop_stats:
        print(f"  → {shop_stats['total_listings']} listings | "
              f"{shop_stats['sales_per_day']} sales/day | "
              f"${shop_stats['total_revenue']:.0f}/month | "
              f"{shop_stats['pct_dead']:.0f}% listings with zero sales")

    print("  Scoring keywords...")
    top_keywords = get_top_keywords(keyword_df, top_n=20)
    print(f"  → {len(top_keywords)} keyword opportunities")

    print("  Finding product gaps...")
    product_gaps = get_product_gaps(keyword_df, own_shop_df)
    print(f"  → {len(product_gaps)} gaps identified")

    print("  Analysing market data...")
    market_insights = get_market_insights(market_df)
    comps = len(market_insights.get("top_competitors", []))
    print(f"  → {comps} top competitor listings surfaced")

    print("  Finding structural product opportunities...")
    market_opps = get_market_product_opportunities(own_shop_df, market_df)
    print(f"  → {len(market_opps)} market opportunities found")

    # ── Step 3: Write report ──────────────────────────
    sep("Step 3: Writing report")

    output_path = write_report(
        shop_stats=shop_stats,
        top_keywords=top_keywords,
        product_gaps=product_gaps,
        market_insights=market_insights,
        market_opps=market_opps,
        csv_files_used=csv_files,
    )

    # ── Summary ───────────────────────────────────────
    print(f"\n  Report saved:")
    print(f"  {output_path}")

    if shop_stats:
        spd  = shop_stats["sales_per_day"]
        gap  = 30 - spd
        mult = round(30 / spd, 1) if spd > 0 else "∞"
        print(f"\n{'=' * 52}")
        print(f" RESULT: {spd} sales/day → need {mult}x growth to hit 30/day")
        print(f"         Top action: fix {min(5, len(shop_stats.get('dead_high_view', [])))} "
              f"dead listings with high views")
        print(f"{'=' * 52}\n")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        traceback.print_exc()
        sys.exit(1)
