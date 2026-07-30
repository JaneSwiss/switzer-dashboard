"""
GA4 client — General Manager

Uses the google-analytics-data package. Same service-account auth mechanism as
search_console_client.py — same credentials file, same service account — just a
different API scope (analytics.readonly) and a separate one-time access grant
(GA4 Admin -> Property Access Management -> add the service account email as Viewer).

Setup required in .env:
  GSC_SERVICE_ACCOUNT_JSON=/path/outside/the/repo/service-account.json   (shared w/ GSC)
  GA4_PROPERTY_ID=123456789   (numeric GA4 property ID, from GA4 Admin -> Property Settings)
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

GSC_SERVICE_ACCOUNT_JSON = os.getenv("GSC_SERVICE_ACCOUNT_JSON", "")
GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "")

NORTH_STAR_GOAL = 10_000  # visitors/month


def _get_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    if not GSC_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GSC_SERVICE_ACCOUNT_JSON not set in .env")
    if not GA4_PROPERTY_ID:
        raise RuntimeError("GA4_PROPERTY_ID not set in .env")

    return BetaAnalyticsDataClient.from_service_account_file(GSC_SERVICE_ACCOUNT_JSON)


def fetch_sessions_by_campaign(days: int = 7) -> "list[dict]":
    """
    Sessions (and conversions, if configured) per UTM campaign over the last `days` —
    joins against utm_campaign=slug from the CTA/pin tagging to attribute traffic back
    to specific posts/pins. totalRevenue isn't requested here since it depends on
    ecommerce events being configured on switzertemplates.com's own checkout, which
    isn't guaranteed — sessions/conversions degrade gracefully either way.
    """
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric,
    )

    client = _get_client()
    request = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        dimensions=[Dimension(name="sessionCampaignName"), Dimension(name="sessionSource")],
        metrics=[Metric(name="sessions"), Metric(name="conversions")],
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
    )
    response = client.run_report(request)

    results = []
    for row in response.rows:
        campaign = row.dimension_values[0].value
        source = row.dimension_values[1].value
        if campaign in ("(not set)", "(direct)", ""):
            continue  # not a UTM-tagged post/pin — irrelevant for per-post attribution
        results.append({
            "utm_campaign": campaign,
            "source": source,
            "sessions": int(row.metric_values[0].value),
            "conversions": float(row.metric_values[1].value),
        })
    return results


def fetch_north_star_pace() -> dict:
    """
    Total site sessions/users over the last 30 days, trended against the prior 30, vs
    the 10,000/month goal. No campaign filter — this is the whole-site number, not the
    GM's own attributable slice, since that's what "10k visitors/month" actually means.
    """
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Metric,
    )

    client = _get_client()
    request = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        metrics=[Metric(name="sessions"), Metric(name="totalUsers")],
        date_ranges=[
            DateRange(start_date="30daysAgo", end_date="today", name="current"),
            DateRange(start_date="60daysAgo", end_date="31daysAgo", name="previous"),
        ],
    )
    response = client.run_report(request)

    # With multiple named date_ranges and no other dimensions, GA4's Data API adds a
    # "dateRange" pseudo-dimension as the first (only) dimension in each row automatically,
    # carrying the range's `name` — this is documented API behavior, not guessed, but
    # worth a real-key smoke test on first use since it's the one thing here I couldn't
    # verify without live credentials (see Verification step in the plan for this client).
    current_sessions = previous_sessions = 0
    for row in response.rows:
        range_name = row.dimension_values[0].value if row.dimension_values else ""
        sessions = int(row.metric_values[0].value)
        if range_name == "current":
            current_sessions = sessions
        elif range_name == "previous":
            previous_sessions = sessions
        else:
            print(f"  Unexpected GA4 date-range label '{range_name}' — check fetch_north_star_pace()")

    pct_to_goal = round(current_sessions / NORTH_STAR_GOAL * 100, 1) if NORTH_STAR_GOAL else 0
    if previous_sessions:
        trend_pct = round((current_sessions - previous_sessions) / previous_sessions * 100, 1)
    else:
        trend_pct = None

    return {
        "monthly_sessions": current_sessions,
        "previous_period_sessions": previous_sessions,
        "goal": NORTH_STAR_GOAL,
        "pct_to_goal": pct_to_goal,
        "trend_pct": trend_pct,
        "as_of": date.today().isoformat(),
    }
