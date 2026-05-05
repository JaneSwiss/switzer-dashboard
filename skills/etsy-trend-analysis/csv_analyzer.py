"""
Everbee CSV parser for Switzertemplates.

Handles three Everbee export formats:
  1. Keyword Research  - Keyword, Volume, Competition, Keyword Score
  2. Own-shop Analysis - Product Name, Est. Sales, Est. Revenue, Conversion Rate, etc.
     (all rows from switzertemplates)
  3. Market Analysis   - same columns as own-shop but from competitor searches

Auto-detects format from column headers. Reads all CSVs in data/everbee-etsy/.
"""

import os
import glob
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "everbee-etsy"
OWN_SHOP = "switzertemplates"

# ── Everbee exact column names (case-insensitive match) ──────────────────────

KEYWORD_COLS = {
    "keyword":        ["keyword", "search term", "query", "term"],
    "search_volume":  ["volume", "search volume", "monthly searches", "searches"],
    "competition":    ["competition", "competition score", "comp score", "comp"],
    "keyword_score":  ["keyword score", "score", "opportunity score"],
}

LISTING_COLS = {
    "title":            ["product name", "title", "listing title", "product title"],
    "shop_name":        ["shop name", "shop", "seller", "store"],
    "price":            ["price", "listing price", "usd price"],
    "monthly_sales":    ["est. sales", "est sales", "monthly sales", "est. monthly sales", "sales"],
    "monthly_revenue":  ["est. revenue", "est revenue", "monthly revenue", "est. monthly revenue"],
    "total_sales":      ["est. total sales", "est total sales", "total sales", "all time sales"],
    "total_views":      ["total views", "views", "listing views"],
    "total_favorites":  ["total favorites", "total favourites", "favorites", "favourites", "hearts"],
    "conversion_rate":  ["conversion rate", "cvr", "conv rate", "conv. rate"],
    "visibility_score": ["visibility score", "visibility"],
    "listing_age":      ["listing age", "age", "age (months)"],
    "total_reviews":    ["total reviews", "reviews"],
    "tags":             ["tags", "listing tags", "tags used"],
}


def _match_col(df_cols, candidates):
    """Return the first matching actual column name (case-insensitive exact match)."""
    lower_map = {c.lower().strip(): c for c in df_cols}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


def _detect_format(df):
    """Return 'keyword', 'listing', or 'unknown'."""
    cols_lower = [c.lower().strip() for c in df.columns]

    kw_hits = sum(
        1 for candidates in KEYWORD_COLS.values()
        if any(c in cols_lower for c in candidates)
    )
    lst_hits = sum(
        1 for candidates in LISTING_COLS.values()
        if any(c in cols_lower for c in candidates)
    )

    if kw_hits >= 2 and "keyword" in cols_lower:
        return "keyword"
    if lst_hits >= 4:
        return "listing"
    return "unknown"


def _safe_float(val):
    try:
        cleaned = str(val).replace(",", "").replace("$", "").replace("%", "").strip()
        return float(cleaned) if cleaned not in ("", "nan", "-", "n/a", "none") else None
    except (ValueError, TypeError):
        return None


def _parse_keyword_csv(df, source_file):
    col = lambda key: _match_col(df.columns, KEYWORD_COLS[key])
    kw_col = col("keyword")
    if not kw_col:
        return pd.DataFrame()

    rows = []
    for _, row in df.iterrows():
        kw = str(row.get(kw_col, "")).strip().lower()
        if not kw or kw == "nan":
            continue

        c_vol  = col("search_volume")
        c_comp = col("competition")
        c_scr  = col("keyword_score")

        rows.append({
            "keyword":       kw,
            "search_volume": _safe_float(row[c_vol])  if c_vol  else None,
            "competition":   _safe_float(row[c_comp]) if c_comp else None,
            "keyword_score": _safe_float(row[c_scr])  if c_scr  else None,
            "source_file":   source_file,
        })
    return pd.DataFrame(rows)


def _parse_listing_csv(df, source_file):
    col = lambda key: _match_col(df.columns, LISTING_COLS[key])
    title_col = col("title")
    if not title_col:
        return pd.DataFrame(), "unknown"

    shop_col  = col("shop_name")
    tags_col  = col("tags")

    rows = []
    for _, row in df.iterrows():
        title = str(row.get(title_col, "")).strip()
        if not title or title == "nan":
            continue

        def sf(key):
            c = col(key)
            return _safe_float(row[c]) if c else None

        rows.append({
            "title":            title,
            "shop_name":        str(row[shop_col]).strip() if shop_col else "",
            "price":            sf("price"),
            "monthly_sales":    sf("monthly_sales"),
            "monthly_revenue":  sf("monthly_revenue"),
            "total_sales":      sf("total_sales"),
            "total_views":      sf("total_views"),
            "total_favorites":  sf("total_favorites"),
            "conversion_rate":  sf("conversion_rate"),
            "visibility_score": sf("visibility_score"),
            "listing_age":      str(row[col("listing_age")]).strip() if col("listing_age") else "",
            "total_reviews":    sf("total_reviews"),
            "tags":             str(row[tags_col]).strip() if tags_col else "",
            "source_file":      source_file,
        })

    result = pd.DataFrame(rows)

    # Determine if this is own-shop data or market data
    if not result.empty and "shop_name" in result.columns:
        unique_shops = result["shop_name"].str.lower().str.strip().unique()
        is_own_shop = (
            len(unique_shops) == 1 and
            any(OWN_SHOP.lower() in s for s in unique_shops)
        )
        data_type = "own_shop" if is_own_shop else "market"
    else:
        data_type = "market"

    return result, data_type


def load_all_csvs():
    """
    Scan data/everbee-etsy/ for all CSV files.
    Returns: (keyword_df, own_shop_df, market_df)
    """
    csv_files = glob.glob(str(DATA_DIR / "*.csv"))
    if not csv_files:
        print(f"  No CSV files found in {DATA_DIR}")
        return _empty_kw(), _empty_listing(), _empty_listing()

    kw_frames, own_frames, market_frames = [], [], []
    skipped = []

    for filepath in sorted(csv_files):
        filename = os.path.basename(filepath)
        try:
            df = pd.read_csv(filepath, encoding="utf-8-sig")
            df.columns = df.columns.str.strip()
            fmt = _detect_format(df)

            if fmt == "keyword":
                parsed = _parse_keyword_csv(df, filename)
                if not parsed.empty:
                    kw_frames.append(parsed)
                    print(f"  [keyword] {filename} - {len(parsed)} keywords")
                else:
                    skipped.append(filename)

            elif fmt == "listing":
                parsed, data_type = _parse_listing_csv(df, filename)
                if not parsed.empty:
                    if data_type == "own_shop":
                        own_frames.append(parsed)
                        print(f"  [own_shop] {filename} - {len(parsed)} listings")
                    else:
                        market_frames.append(parsed)
                        print(f"  [market] {filename} - {len(parsed)} listings")
                else:
                    skipped.append(filename)
            else:
                skipped.append(filename)
                print(f"  [skipped] {filename} - format not recognised")

        except Exception as e:
            print(f"  [error] {filename} - {e}")

    if skipped:
        print(f"  Note: {len(skipped)} file(s) skipped")

    keyword_df  = pd.concat(kw_frames,     ignore_index=True) if kw_frames     else _empty_kw()
    own_shop_df = pd.concat(own_frames,    ignore_index=True) if own_frames     else _empty_listing()
    market_df   = pd.concat(market_frames, ignore_index=True) if market_frames  else _empty_listing()

    # Deduplicate keywords - keep highest score
    if not keyword_df.empty:
        keyword_df = (
            keyword_df.sort_values("keyword_score", ascending=False, na_position="last")
            .drop_duplicates(subset=["keyword"])
            .reset_index(drop=True)
        )

    return keyword_df, own_shop_df, market_df


def _empty_kw():
    return pd.DataFrame(columns=["keyword", "search_volume", "competition", "keyword_score", "source_file"])


def _empty_listing():
    return pd.DataFrame(columns=[
        "title", "shop_name", "price", "monthly_sales", "monthly_revenue",
        "total_sales", "total_views", "total_favorites", "conversion_rate",
        "visibility_score", "listing_age", "total_reviews", "tags", "source_file",
    ])
