"""
Trend analysis engine for Switzertemplates.

Input: keyword_df, own_shop_df (Jane's listings), market_df (competitor listings)
Output: structured findings for the report writer.
"""

import re
import math
import pandas as pd
from typing import Optional

OWN_SHOP = "switzertemplates"

# Niche terms relevant to Switzertemplates products
NICHE_TERMS = {
    "branding", "brand kit", "brand bundle", "brand template", "brand package",
    "logo", "wix", "wix website", "wix template", "website template", "landing page",
    "canva", "canva template", "instagram template", "social media template",
    "coach", "coaching", "consultant", "therapist", "wellness", "beauty",
    "small business", "business owner", "entrepreneur", "service provider",
    "template pack", "ebook template", "business card", "flyer",
    "marketing bundle", "business bundle", "digital", "premade",
    "etsy shop", "etsy banner", "etsy branding", "personal brand",
    "digital marketer", "social media manager", "smm", "content creator",
    "pinterest", "carousel", "instagram post", "instagram bundle",
    "ios core", "aesthetic instagram", "bold instagram",
}


# ── Shop health overview ─────────────────────────────────────────────────────

def analyze_own_shop(own_df: pd.DataFrame) -> dict:
    """
    Full performance analysis of Jane's own shop listings.
    Returns a dict with: summary stats, top earners, dead listings,
    price tier breakdown, conversion problem listings.
    """
    if own_df.empty:
        return {}

    df = own_df.copy()
    for col in ["monthly_sales", "monthly_revenue", "total_views", "total_favorites",
                "conversion_rate", "visibility_score", "price", "total_reviews"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    total = len(df)
    total_sales   = df["monthly_sales"].sum()
    total_revenue = df["monthly_revenue"].sum()
    zero_sales    = (df["monthly_sales"] == 0).sum()
    earners       = total - zero_sales

    # Top earners by monthly revenue
    top_earners = []
    for _, row in df.nlargest(15, "monthly_revenue").iterrows():
        if row["monthly_revenue"] > 0:
            top_earners.append({
                "title":           row["title"],
                "price":           row["price"],
                "monthly_sales":   int(row["monthly_sales"]),
                "monthly_revenue": row["monthly_revenue"],
                "conversion_rate": row["conversion_rate"],
                "total_views":     int(row["total_views"]),
                "visibility_score": int(row["visibility_score"]),
                "listing_age":     row["listing_age"],
                "tags":            row["tags"],
            })

    # Dead listings with high views (conversion problem - worst waste)
    high_view_dead = df[(df["monthly_sales"] == 0) & (df["total_views"] > 5000)].copy()
    high_view_dead = high_view_dead.nlargest(15, "total_views")
    dead_high_view = []
    for _, row in high_view_dead.iterrows():
        dead_high_view.append({
            "title":           row["title"],
            "price":           row["price"],
            "total_views":     int(row["total_views"]),
            "total_favorites": int(row["total_favorites"]),
            "conversion_rate": row["conversion_rate"],
            "visibility_score": int(row["visibility_score"]),
            "listing_age":     row["listing_age"],
            "tags":            row["tags"],
        })

    # Dead listings with low views (discovery problem)
    low_vis_dead = df[
        (df["monthly_sales"] == 0) &
        (df["total_views"] < 500) &
        (df["visibility_score"] < 30)
    ]

    # Price tier breakdown
    tiers = [
        (0,   15,  "Under $15"),
        (15,  40,  "$15-40"),
        (40,  80,  "$40-80"),
        (80,  999, "$80+"),
    ]
    price_tiers = []
    for lo, hi, label in tiers:
        sub = df[(df["price"] >= lo) & (df["price"] < hi)]
        price_tiers.append({
            "label":           label,
            "listing_count":   len(sub),
            "monthly_sales":   int(sub["monthly_sales"].sum()),
            "monthly_revenue": round(sub["monthly_revenue"].sum(), 2),
            "avg_conversion":  round(sub["conversion_rate"].mean(), 2) if len(sub) else 0,
        })

    # Underperformers: have some views, low CVR vs peers
    avg_cvr = df[df["monthly_sales"] > 0]["conversion_rate"].mean()
    underperformers = []
    for _, row in df[
        (df["monthly_sales"] > 0) &
        (df["conversion_rate"] < avg_cvr * 0.5) &
        (df["total_views"] > 1000)
    ].nlargest(10, "total_views").iterrows():
        underperformers.append({
            "title":            row["title"],
            "price":            row["price"],
            "monthly_sales":    int(row["monthly_sales"]),
            "monthly_revenue":  row["monthly_revenue"],
            "total_views":      int(row["total_views"]),
            "conversion_rate":  row["conversion_rate"],
            "avg_shop_cvr":     round(avg_cvr, 2),
            "tags":             row["tags"],
        })

    return {
        "total_listings":   total,
        "total_sales_month": int(total_sales),
        "sales_per_day":    round(total_sales / 30, 1),
        "total_revenue":    round(total_revenue, 2),
        "zero_sales_count": int(zero_sales),
        "earners_count":    int(earners),
        "pct_dead":         round(zero_sales / total * 100, 1) if total else 0,
        "avg_shop_cvr":     round(avg_cvr, 2) if earners > 0 else 0,
        "top_earners":      top_earners,
        "dead_high_view":   dead_high_view,
        "dead_low_vis_count": int(len(low_vis_dead)),
        "price_tiers":      price_tiers,
        "underperformers":  underperformers,
    }


# ── Keyword opportunities ────────────────────────────────────────────────────

def get_top_keywords(keyword_df: pd.DataFrame, top_n: int = 20) -> list[dict]:
    """
    Rank keywords using Everbee's Keyword Score as primary signal.
    Higher score = better opportunity (Everbee pre-calculates volume/competition ratio).
    Filter to niche-relevant keywords only.
    """
    if keyword_df.empty:
        return []

    df = keyword_df.copy()
    df["search_volume"]  = pd.to_numeric(df["search_volume"],  errors="coerce").fillna(0)
    df["competition"]    = pd.to_numeric(df["competition"],    errors="coerce").fillna(999999)
    df["keyword_score"]  = pd.to_numeric(df["keyword_score"],  errors="coerce").fillna(0)

    # Filter to niche-relevant
    niche_mask = df["keyword"].apply(
        lambda kw: any(term in kw.lower() for term in NICHE_TERMS)
    )
    df_niche = df[niche_mask].copy()
    if df_niche.empty:
        df_niche = df.copy()

    # Primary sort: keyword_score (Everbee's own opportunity metric)
    # Secondary: search_volume
    df_niche = df_niche[df_niche["keyword_score"] > 0].sort_values(
        ["keyword_score", "search_volume"], ascending=[False, False]
    )

    results = []
    for _, row in df_niche.head(top_n).iterrows():
        results.append({
            "keyword":       row["keyword"],
            "search_volume": int(row["search_volume"]) if row["search_volume"] > 0 else None,
            "competition":   int(row["competition"])   if row["competition"]   < 999999 else None,
            "keyword_score": int(row["keyword_score"]),
            "source_file":   row.get("source_file", ""),
        })
    return results


# ── Product gap analysis ─────────────────────────────────────────────────────

def get_product_gaps(
    keyword_df: pd.DataFrame,
    own_shop_df: pd.DataFrame,
    top_n: int = 15,
) -> list[dict]:
    """
    Find high-opportunity keywords where no listing has this keyword as a TAG
    (exact phrase) or clearly in the title (exact phrase match).
    Uses strict matching to avoid false "covered" results on broad keyword overlap.
    """
    if keyword_df.empty:
        return []

    top_kws = get_top_keywords(keyword_df, top_n=80)

    # Build exact-match lookup sets from Jane's tags and titles
    own_tags_set  = set()
    own_title_set = set()
    if not own_shop_df.empty:
        for _, row in own_shop_df.iterrows():
            title_lower = str(row.get("title", "")).lower()
            tags_lower  = str(row.get("tags",  "")).lower()
            own_title_set.add(title_lower)
            # Individual tags are comma-separated
            for tag in tags_lower.split(","):
                own_tags_set.add(tag.strip())

    def is_covered(keyword: str) -> bool:
        kw = keyword.lower().strip()
        # Exact tag match
        if kw in own_tags_set:
            return True
        # Exact phrase anywhere in a listing title (whole-word boundary)
        pattern = re.compile(r"\b" + re.escape(kw) + r"\b")
        for title in own_title_set:
            if pattern.search(title):
                return True
        return False

    gaps = []
    for kw_data in top_kws:
        keyword = kw_data["keyword"]
        if not is_covered(keyword):
            gaps.append({
                "keyword":        keyword,
                "search_volume":  kw_data["search_volume"],
                "competition":    kw_data["competition"],
                "keyword_score":  kw_data["keyword_score"],
                "recommendation": _gap_rec(keyword, kw_data),
            })

    gaps.sort(key=lambda x: x["keyword_score"], reverse=True)
    return gaps[:top_n]


def get_market_product_opportunities(
    own_shop_df: pd.DataFrame,
    market_df: pd.DataFrame,
) -> list[dict]:
    """
    Compare Jane's price point distribution vs market performance to surface
    structural product opportunities (e.g. bundling, new price tiers, missing categories).
    """
    if market_df.empty or own_shop_df.empty:
        return []

    for df in [own_shop_df, market_df]:
        for col in ["monthly_revenue", "monthly_sales", "price"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    opps = []

    # ── Opportunity 1: Instagram bundle price gap ────────────────────────────
    own_ig_cheap = own_shop_df[
        own_shop_df["title"].str.lower().str.contains("instagram", na=False) &
        (own_shop_df["price"] < 20)
    ]
    mkt_ig_mid = market_df[
        market_df["title"].str.lower().str.contains("instagram", na=False) &
        (market_df["price"] >= 35) & (market_df["price"] <= 100)
    ]
    if len(own_ig_cheap) > 10 and len(mkt_ig_mid) > 5:
        avg_mkt_rev = mkt_ig_mid["monthly_revenue"].mean()
        opps.append({
            "type":           "price_gap",
            "title":          "Bundle your Instagram templates at $35-80",
            "detail":         (
                f"You have {len(own_ig_cheap)} Instagram template listings under $20. "
                f"The market has {len(mkt_ig_mid)} Instagram bundles at $35-100 averaging "
                f"${avg_mkt_rev:.0f}/month each. Consolidating 3-4 of your packs into a "
                f"'complete Instagram bundle' at $38-45 could 3x your revenue per transaction "
                f"without creating new content."
            ),
            "priority": "high",
        })

    # ── Opportunity 2: Wix listings not earning ──────────────────────────────
    own_wix = own_shop_df[own_shop_df["title"].str.lower().str.contains("wix", na=False)].copy()
    own_wix["monthly_sales"] = pd.to_numeric(own_wix["monthly_sales"], errors="coerce").fillna(0)
    wix_total  = len(own_wix)
    wix_dead   = int((own_wix["monthly_sales"] == 0).sum())
    wix_earners = wix_total - wix_dead
    wix_rev    = own_wix["monthly_revenue"].sum()
    if wix_total > 0 and wix_dead > wix_earners:
        opps.append({
            "type":    "dead_product_type",
            "title":   f"Fix {wix_dead} non-earning Wix website listings",
            "detail":  (
                f"You have {wix_total} Wix website listings. Only {wix_earners} made a sale "
                f"last month — {wix_dead} generated zero. Your active Wix listings bring in "
                f"${wix_rev:.0f}/month total. If the dead ones each converted at even 50% of "
                f"your best Wix listing's rate, you'd add 10-15 sales/month from this "
                f"product type alone. These need title/tag rewrites targeting niche-specific "
                f"search terms (therapist website, beauty salon website, coach website, etc.)."
            ),
            "priority": "high",
        })

    # ── Opportunity 3: Digital marketer / SMM bundle ─────────────────────────
    own_dm = own_shop_df[
        own_shop_df["title"].str.lower().str.contains("digital marketer|smm bundle|social media manager bundle", na=False)
    ]
    mkt_dm = market_df[
        market_df["title"].str.lower().str.contains("digital marketer|social media manager bundle", na=False) &
        (market_df["price"] < 300)
    ]
    if len(own_dm) == 0 and len(mkt_dm) > 0:
        avg_rev = mkt_dm["monthly_revenue"].mean()
        top_rev = mkt_dm["monthly_revenue"].max()
        opps.append({
            "type":    "missing_category",
            "title":   "Create a 'Digital Marketer' template bundle",
            "detail":  (
                f"Your keyword data shows 'digital marketer' as the highest-score keyword "
                f"(score 710, 1,111 searches/month). You have no product specifically targeting "
                f"this search. Competitors selling 'digital marketer templates' or 'SMM bundles' "
                f"average ${avg_rev:.0f}/month (top: ${top_rev:.0f}/month). "
                f"This could be a repackaging of your existing social media manager / coaching "
                f"templates as a 'digital marketer bundle' at $38-55 with new title/tags."
            ),
            "priority": "high",
        })

    # ── Opportunity 4: Price the $15-40 dead zone ────────────────────────────
    own_mid = own_shop_df[
        (own_shop_df["price"] >= 15) & (own_shop_df["price"] < 40)
    ].copy()
    own_mid["monthly_sales"] = pd.to_numeric(own_mid["monthly_sales"], errors="coerce").fillna(0)
    mid_zero = int((own_mid["monthly_sales"] == 0).sum())
    if mid_zero > 30:
        opps.append({
            "type":    "price_zone",
            "title":   f"Escape the $15-40 price dead zone",
            "detail":  (
                f"You have {len(own_mid)} listings priced $15-40, and {mid_zero} of them "
                f"made zero sales last month. This is your worst-performing price tier by "
                f"conversion rate. Products here are priced too high to impulse-buy but "
                f"too low to feel premium. Either drop them below $15 (to increase volume) "
                f"or restructure them as larger bundles at $38+ (to improve perceived value "
                f"and revenue per transaction)."
            ),
            "priority": "medium",
        })

    return opps


def _gap_rec(keyword: str, kw: dict) -> str:
    kw_lower = keyword.lower()
    vol      = kw.get("search_volume") or 0
    score    = kw.get("keyword_score") or 0

    if "wix" in kw_lower:
        base = "New Wix website listing targeting this keyword"
    elif "digital marketer" in kw_lower or "smm" in kw_lower:
        base = "New social media manager / digital marketer template pack"
    elif "personal brand" in kw_lower:
        base = "New personal branding kit or bundle targeting this keyword"
    elif "pinterest" in kw_lower:
        base = "New Pinterest template pack or Pinterest-branded branding kit"
    elif "etsy" in kw_lower:
        base = "New Etsy shop branding kit or banner template"
    elif "brand" in kw_lower or "branding" in kw_lower:
        base = "New branding kit listing targeting this keyword"
    elif "canva" in kw_lower and "coach" in kw_lower:
        base = "New Canva coaching template pack"
    elif "instagram" in kw_lower or "carousel" in kw_lower or "ig " in kw_lower:
        base = "New Instagram template pack targeting this keyword"
    elif "bundle" in kw_lower:
        base = "New bundle listing targeting this keyword"
    else:
        base = "New listing targeting this keyword"

    if score >= 200:
        base += " - high priority (top Everbee score)"
    elif score >= 100:
        base += " - strong opportunity"

    if vol and vol > 1000:
        base += f" ({vol:,} searches/mo)"

    return base


# ── Market intelligence ──────────────────────────────────────────────────────

def get_market_insights(market_df: pd.DataFrame) -> dict:
    """
    Analyse competitor listing data to find:
    - Top earners by niche (filtered to relevant products)
    - Price tier performance in the market
    - Product types doing well that Jane isn't selling
    """
    if market_df.empty:
        return {}

    df = market_df.copy()
    for col in ["monthly_sales", "monthly_revenue", "price", "conversion_rate", "total_views"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Filter to niche-relevant titles
    def is_relevant(title):
        t = title.lower()
        return any(term in t for term in NICHE_TERMS)

    df_niche = df[df["title"].apply(is_relevant)].copy()
    # Also exclude very high-ticket custom services
    df_niche = df_niche[df_niche["price"] < 400]

    if df_niche.empty:
        df_niche = df[df["price"] < 400].copy()

    # Top competitor listings by revenue
    top_comps = []
    for _, row in df_niche.nlargest(12, "monthly_revenue").iterrows():
        top_comps.append({
            "title":           row["title"],
            "shop_name":       row.get("shop_name", ""),
            "price":           row["price"],
            "monthly_sales":   int(row["monthly_sales"]),
            "monthly_revenue": round(row["monthly_revenue"], 0),
            "conversion_rate": row["conversion_rate"],
            "source_file":     row.get("source_file", ""),
        })

    # Price tier performance across the market
    tiers = [(0,20,"Under $20"),(20,50,"$20-50"),(50,100,"$50-100"),(100,400,"$100-400")]
    mkt_tiers = []
    for lo, hi, label in tiers:
        sub = df_niche[(df_niche["price"] >= lo) & (df_niche["price"] < hi)]
        if len(sub) > 5:
            mkt_tiers.append({
                "label":         label,
                "listings":      len(sub),
                "avg_sales":     round(sub["monthly_sales"].mean(), 1),
                "avg_revenue":   round(sub["monthly_revenue"].mean(), 0),
                "avg_cvr":       round(sub["conversion_rate"].mean(), 2),
            })

    return {
        "top_competitors": top_comps,
        "market_tiers":    mkt_tiers,
    }
