"""
One-off script: apply web_search_finder URL-based filters to old leads that
predate today's filtering improvements (June 14 2026).

Filters applied (no HTTP calls — URL and business name only):
  - _should_skip(): SKIP_DOMAINS, .edu/.gov, domain signals, directory URL paths
  - _is_institutional(): using business name as proxy title (no snippet available)

Run: python3 skills/lead-gen-agent/retro_filter.py
"""

import os
import sys
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from web_search_finder import _should_skip, _is_institutional

TRACKER_PATH = Path(__file__).resolve().parents[2] / "outputs" / "leads" / "lead-tracker.csv"

# Leads added before today's filtering improvements
OLD_DATES = {"2026-06-01", "2026-06-09", "2026-06-10"}


def main():
    df = pd.read_csv(TRACKER_PATH)

    mask = (
        df["date_found"].isin(OLD_DATES)
        & df["website"].notna()
        & df["website"].str.strip().ne("")
        & (df["contact_email"].isna() | df["contact_email"].str.strip().eq(""))
        & (df["contact_page_url"].isna() | df["contact_page_url"].str.strip().eq(""))
        & ~df["status"].isin(["dead", "messaged", "paid"])
        & ~df["notes"].fillna("").str.contains("form-failed", na=False)
    )

    candidates = df[mask]
    print(f"Old leads to check: {len(candidates)}")

    killed = 0
    skip_domain_count = 0
    directory_url_count = 0
    institutional_count = 0

    for idx, row in candidates.iterrows():
        url = str(row["website"]).strip()
        business_name = str(row.get("shop_or_business_name", "")).strip()

        reason = None

        if _should_skip(url):
            # Distinguish sub-reasons for reporting
            from urllib.parse import urlparse
            from web_search_finder import _is_directory_url, SKIP_DOMAINS
            domain = urlparse(url).netloc.lower().lstrip("www.")
            if any(domain == s or domain.endswith("." + s) for s in SKIP_DOMAINS):
                reason = "retro-filter: known junk domain"
                skip_domain_count += 1
            else:
                reason = "retro-filter: directory URL path or domain signal"
                directory_url_count += 1
        elif _is_institutional(business_name, ""):
            reason = "retro-filter: institutional business name"
            institutional_count += 1

        if reason:
            df.at[idx, "status"] = "dead"
            existing = str(df.at[idx, "notes"]) if pd.notna(df.at[idx, "notes"]) else ""
            df.at[idx, "notes"] = f"{existing} | {reason}".lstrip(" |")
            killed += 1

    df.to_csv(TRACKER_PATH, index=False)

    print(f"\nMarked dead:  {killed} / {len(candidates)}")
    print(f"Still queued: {len(candidates) - killed}")
    print(f"\nBreakdown:")
    print(f"  {skip_domain_count:3d}  known junk domain (SKIP_DOMAINS)")
    print(f"  {directory_url_count:3d}  directory URL path or domain signal")
    print(f"  {institutional_count:3d}  institutional business name")


if __name__ == "__main__":
    main()
