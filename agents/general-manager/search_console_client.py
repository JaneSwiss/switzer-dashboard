"""
Google Search Console client — General Manager

Auth via a service account (no browser OAuth consent flow — what unattended automation
needs). One searchanalytics().query() call per run pulls the full result set (dimensions
query + page), then everything else — rankings, new keyword opportunities, close-to-page-1
posts/pages, trending detection — is computed locally in Python from that one pull.

Setup required in .env:
  GSC_SERVICE_ACCOUNT_JSON=/path/outside/the/repo/service-account.json
  GSC_SITE_URL=https://www.switzertemplates.com/   (or sc-domain:switzertemplates.com —
                                                       must match the actual GSC property type)
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = Path(__file__).resolve().parent
KEYWORDS_FILE = ROOT / "agents" / "blog-seo-agent" / "keywords" / "switzertemplates_keyword_masterlist.csv"
POSTS_DIR = ROOT / "posts"
HISTORY_FILE = AGENT_DIR / "logs" / "search_console_history.json"

load_dotenv(ROOT / ".env")
GSC_SERVICE_ACCOUNT_JSON = os.getenv("GSC_SERVICE_ACCOUNT_JSON", "")
GSC_SITE_URL = os.getenv("GSC_SITE_URL", "https://www.switzertemplates.com/")

# The known product/service pages hardcoded in blog_seo_agent.py's CTA MAPPING — used to
# label a close-to-page-1 result as a "page" rather than a "post".
KNOWN_PAGES = {
    "/premade-wix-website-templates-for-sale": "Premade Wix Websites",
    "/branding-packages": "Branding Packages",
    "/business-template-bundles": "3-in-1 Business Bundles",
}
KNOWN_PAGE_HOST_PATH = "pinterest.switzertemplates.com"

TRENDING_GROWTH_THRESHOLD = 0.30   # 30% week-over-week impressions growth
TRENDING_MIN_IMPRESSIONS = 15      # floor, so tiny numbers don't read as "trending"

CLOSE_TO_PAGE_ONE_MIN = 11
CLOSE_TO_PAGE_ONE_MAX = 20


def _get_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    if not GSC_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GSC_SERVICE_ACCOUNT_JSON not set in .env")

    creds = service_account.Credentials.from_service_account_file(
        GSC_SERVICE_ACCOUNT_JSON,
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
    )
    return build("searchconsole", "v1", credentials=creds)


def _fetch_raw_rows(days: int = 28) -> "list[dict]":
    service = _get_service()
    request = {
        "startDate": (date.today() - timedelta(days=days)).isoformat(),
        "endDate": date.today().isoformat(),
        "dimensions": ["query", "page"],
        "rowLimit": 25000,
    }
    response = service.searchanalytics().query(siteUrl=GSC_SITE_URL, body=request).execute()
    return response.get("rows", [])


def _load_masterlist() -> "list[dict]":
    import csv
    if not KEYWORDS_FILE.exists():
        return []
    with KEYWORDS_FILE.open(newline="", encoding="utf-8-sig") as f:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def _get_written_slugs() -> "set[str]":
    return {p.stem for p in POSTS_DIR.glob("*.html")}


def _slugify(text: str) -> str:
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def _page_label(page_url: str) -> "tuple[str, str]":
    """Returns (label, kind) — kind is 'post' or 'page'."""
    for path, name in KNOWN_PAGES.items():
        if path in page_url:
            return name, "page"
    if KNOWN_PAGE_HOST_PATH in page_url:
        return "Pinterest service page", "page"
    if "/post/" in page_url:
        slug = page_url.rstrip("/").rsplit("/", 1)[-1]
        return slug, "post"
    return page_url, "page"


def fetch_rankings(days: int = 28) -> dict:
    """
    One GSC pull -> rankings for tracked keywords, new keyword opportunities, and
    close-to-page-1 posts/pages. Also updates the week-over-week history file used by
    get_trending_unwritten_keywords().
    """
    rows = _fetch_raw_rows(days=days)
    masterlist = _load_masterlist()
    masterlist_keywords = {row.get("Keyword", "").strip().lower() for row in masterlist if row.get("Keyword")}
    written_slugs = _get_written_slugs()

    # Aggregate impressions per bare query (across pages) for trending detection,
    # and keep the best (lowest-position) row per query for everything else.
    best_row_per_query: dict[str, dict] = {}
    impressions_per_query: dict[str, int] = {}
    for row in rows:
        query = row["keys"][0].lower().strip()
        page = row["keys"][1]
        impressions_per_query[query] = impressions_per_query.get(query, 0) + row.get("impressions", 0)
        current_best = best_row_per_query.get(query)
        if current_best is None or row.get("position", 999) < current_best["position"]:
            best_row_per_query[query] = {
                "query": query, "page": page, "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0), "ctr": row.get("ctr", 0),
                "position": row.get("position", 999),
            }

    rankings = []
    for kw in masterlist_keywords:
        r = best_row_per_query.get(kw)
        if r:
            rankings.append({
                "keyword": kw, "clicks": r["clicks"], "impressions": r["impressions"],
                "ctr": round(r["ctr"], 4), "avg_position": round(r["position"], 1),
            })

    new_opportunities = []
    for query, r in best_row_per_query.items():
        if query in masterlist_keywords:
            continue
        if r["impressions"] < TRENDING_MIN_IMPRESSIONS or r["position"] <= 10:
            continue
        new_opportunities.append({
            "query": query, "impressions": r["impressions"], "avg_position": round(r["position"], 1),
        })
    new_opportunities.sort(key=lambda x: -x["impressions"])

    close_to_page_one = []
    for query, r in best_row_per_query.items():
        if not (CLOSE_TO_PAGE_ONE_MIN <= r["position"] <= CLOSE_TO_PAGE_ONE_MAX):
            continue
        label, kind = _page_label(r["page"])
        if kind == "post" and label not in written_slugs:
            continue  # only flag posts that actually exist
        close_to_page_one.append({
            "label": label, "kind": kind, "query": query,
            "avg_position": round(r["position"], 1), "url": r["page"],
        })

    _update_history(impressions_per_query)

    return {
        "rankings": rankings,
        "new_opportunities": new_opportunities[:20],
        "close_to_page_one": close_to_page_one[:15],
        "pulled_days": days,
    }


def _load_history() -> "list[dict]":
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _update_history(impressions_per_query: "dict[str, int]") -> None:
    history = _load_history()
    history.append({"date": date.today().isoformat(), "impressions": impressions_per_query})
    # Keep a reasonable window — no need to grow this file forever.
    history = history[-12:]
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")


def get_trending_unwritten_keywords() -> "list[str]":
    """
    Compares this week's impressions (already in history after fetch_rankings() runs)
    against the previous snapshot. Returns masterlist keywords, not yet written, whose
    impressions grew meaningfully week-over-week — ordered by growth. Often empty —
    that's expected, not a failure.

    Must be called AFTER fetch_rankings() in the same run, since it reads the history
    file fetch_rankings() just updated.
    """
    history = _load_history()
    if len(history) < 2:
        return []  # no prior snapshot yet to compare against

    current = history[-1]["impressions"]
    previous = history[-2]["impressions"]

    masterlist = _load_masterlist()
    written_slugs = _get_written_slugs()
    unwritten = [
        row for row in masterlist
        if row.get("Keyword") and _slugify(row["Keyword"]) not in written_slugs
    ]

    trending = []
    for row in unwritten:
        kw = row["Keyword"].strip().lower()
        now_impr = current.get(kw, 0)
        prev_impr = previous.get(kw, 0)
        if now_impr < TRENDING_MIN_IMPRESSIONS:
            continue
        if prev_impr == 0:
            continue  # brand new this week — one data point isn't a trend yet
        growth = (now_impr - prev_impr) / prev_impr
        if growth >= TRENDING_GROWTH_THRESHOLD:
            trending.append((row["Keyword"], growth))

    trending.sort(key=lambda x: -x[1])
    return [kw for kw, _ in trending]
