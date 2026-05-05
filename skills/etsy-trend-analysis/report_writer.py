"""
Report writer for Switzertemplates Etsy Trend Analysis.
Saves to outputs/etsy-sales/etsy-trend-report-YYYY-MM-DD.md
"""

from datetime import date
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs" / "etsy-sales"

TARGET_SALES_PER_DAY = 30


def _p(val, decimals=2):
    if val is None: return "n/a"
    return f"${val:.{decimals}f}"

def _n(val):
    if val is None: return "n/a"
    return f"{int(val):,}"

def _cvr(val):
    if val is None: return "n/a"
    return f"{val:.2f}%"


def write_report(
    shop_stats: dict,
    top_keywords: list[dict],
    product_gaps: list[dict],
    market_insights: dict,
    market_opps: list[dict],
    csv_files_used: list[str],
) -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    output_path = OUTPUT_DIR / f"etsy-trend-report-{today}.md"

    L = []
    a = L.append

    # ── HEADER ──────────────────────────────────────────────────────────────
    a(f"# Etsy Trend Report — {today}")
    a(f"**Target:** {TARGET_SALES_PER_DAY} sales/day")
    if csv_files_used:
        a(f"**Data sources:** {', '.join(csv_files_used)}")
    a("")

    # ── SECTION 1: SHOP HEALTH ───────────────────────────────────────────────
    a("---")
    a("")
    a("## 1. Shop Health Overview")
    a("")

    if not shop_stats:
        a("No own-shop Everbee data found. Drop a shop analytics export into `data/everbee-etsy/`.")
        a("")
    else:
        s = shop_stats
        current_spd = s["sales_per_day"]
        gap         = TARGET_SALES_PER_DAY - current_spd
        multiplier  = round(TARGET_SALES_PER_DAY / current_spd, 1) if current_spd > 0 else "∞"

        a(f"| Metric | Value |")
        a(f"|--------|-------|")
        a(f"| Total active listings | {_n(s['total_listings'])} |")
        a(f"| Listings with 1+ sale this month | {_n(s['earners_count'])} ({100 - s['pct_dead']:.0f}% of shop) |")
        a(f"| Listings with ZERO sales | **{_n(s['zero_sales_count'])} ({s['pct_dead']:.0f}%)** |")
        a(f"| Est. monthly sales | {_n(s['total_sales_month'])} |")
        a(f"| Est. sales per day | **{current_spd}** |")
        a(f"| Est. monthly revenue | {_p(s['total_revenue'], 0)} |")
        a(f"| Average shop conversion rate | {_cvr(s['avg_shop_cvr'])} |")
        a("")
        a(f"**Current pace:** {current_spd} sales/day — **{gap:.1f} sales/day short of the 30/day target.**")
        a(f"You need to **{multiplier}x your current sales volume** to hit that goal.")
        a("")

        # Price tier breakdown
        a("### Revenue by price tier")
        a("")
        a("| Price tier | Listings | Monthly sales | Monthly revenue | Avg CVR |")
        a("|-----------|----------|---------------|-----------------|---------|")
        for t in s["price_tiers"]:
            a(f"| {t['label']} | {t['listing_count']} | {_n(t['monthly_sales'])} | {_p(t['monthly_revenue'], 0)} | {_cvr(t['avg_conversion'])} |")
        a("")
        # Flag the insight
        tiers = s["price_tiers"]
        cheap = next((t for t in tiers if t["label"] == "Under $15"), None)
        mid   = next((t for t in tiers if t["label"] == "$15-40"), None)
        prem  = next((t for t in tiers if t["label"] == "$80+"), None)
        if cheap and prem:
            a(f"**Key insight:** Your {cheap['listing_count']} sub-$15 listings generate "
              f"{_p(cheap['monthly_revenue'], 0)}/month. Your {prem['listing_count']} "
              f"$80+ listings generate {_p(prem['monthly_revenue'], 0)}/month — roughly "
              f"the same revenue from far fewer products. More high-ticket listings = "
              f"more revenue without more transactions.")
        if mid:
            a(f"Your $15-40 tier ({mid['listing_count']} listings) is your weakest: "
              f"only {_n(mid['monthly_sales'])} sales/month. This price point is a dead "
              f"zone for your shop - products here need to move up or down.")
        a("")

    # ── SECTION 2: TOP EARNERS ───────────────────────────────────────────────
    a("---")
    a("")
    a("## 2. Your Top-Earning Listings")
    a("")

    if shop_stats and shop_stats.get("top_earners"):
        a("| Sales/mo | Revenue | CVR | Price | Title |")
        a("|----------|---------|-----|-------|-------|")
        for e in shop_stats["top_earners"]:
            title_s = e["title"][:65] + "..." if len(e["title"]) > 65 else e["title"]
            a(f"| {_n(e['monthly_sales'])} | {_p(e['monthly_revenue'], 0)} | "
              f"{_cvr(e['conversion_rate'])} | {_p(e['price'], 0)} | {title_s} |")
        a("")
        a("**Pattern:** Your Wix website listings ($150) and flagship branding bundles ($79) "
          "drive the most revenue per transaction. These are your core products — prioritise "
          "adding more listings at these price points over adding more $14 template packs.")
        a("")
    else:
        a("No shop data available.")
        a("")

    # ── SECTION 3: DEAD LISTINGS (HIGH VIEWS, ZERO SALES) ───────────────────
    a("---")
    a("")
    a("## 3. Critical: Listings Wasting Traffic")
    a("")

    if shop_stats and shop_stats.get("dead_high_view"):
        dead = shop_stats["dead_high_view"]
        total_wasted_views = sum(d["total_views"] for d in dead)
        a(f"These {len(dead)} listings had **{_n(total_wasted_views)} total views** and made "
          f"**zero sales last month.** This is your biggest short-term opportunity - "
          f"fixing even 3-4 of these could meaningfully move your daily sales.")
        a("")
        a("| Views | Favs | Price | Vis. Score | Title |")
        a("|-------|------|-------|-----------|-------|")
        for d in dead:
            title_s = d["title"][:60] + "..." if len(d["title"]) > 60 else d["title"]
            a(f"| {_n(d['total_views'])} | {_n(d['total_favorites'])} | "
              f"{_p(d['price'], 0)} | {d['visibility_score']} | {title_s} |")
        a("")
        a("**Why this happens:** High views with zero conversions means buyers are clicking "
          "through (title/thumbnail works) but leaving without buying. The most common causes:")
        a("")
        a("- Main listing image doesn't show enough of what they get")
        a("- Price feels high relative to what the preview shows")
        a("- Description doesn't address the buyer's hesitation")
        a("- No social proof visible in the listing (reviews, download count)")
        a("")
        a("**What to do first:** Pick the 3 listings with the most views. Update the main "
          "image to show a mockup or preview that clearly communicates scale and quality. "
          "Add the review count and a strong 'what's included' summary above the fold in the description.")
        a("")

        if shop_stats.get("dead_low_vis_count", 0) > 0:
            a(f"Additionally, **{_n(shop_stats['dead_low_vis_count'])} listings** have low "
              f"visibility scores (under 30) AND zero sales - these are buried in search. "
              f"They need a full title and tag rewrite using keywords from Section 5.")
            a("")
    else:
        a("No high-traffic dead listings found.")
        a("")

    # ── SECTION 4: UNDERPERFORMERS (SELLING BUT LOW CVR) ────────────────────
    a("---")
    a("")
    a("## 4. Underperforming Active Listings")
    a("")

    if shop_stats and shop_stats.get("underperformers"):
        ups = shop_stats["underperformers"]
        avg_cvr = shop_stats["avg_shop_cvr"]
        a(f"These listings are making sales but converting at less than half your shop "
          f"average ({_cvr(avg_cvr)}). They have traffic - the opportunity is there.")
        a("")
        a("| Sales/mo | Revenue | CVR | Views | Price | Title |")
        a("|----------|---------|-----|-------|-------|-------|")
        for u in ups:
            title_s = u["title"][:55] + "..." if len(u["title"]) > 55 else u["title"]
            a(f"| {_n(u['monthly_sales'])} | {_p(u['monthly_revenue'], 0)} | "
              f"{_cvr(u['conversion_rate'])} | {_n(u['total_views'])} | "
              f"{_p(u['price'], 0)} | {title_s} |")
        a("")
        a("**For each of these:** check the main image, price vs competitors, and "
          "whether the description opens with a strong benefit statement.")
        a("")
    else:
        a("No underperformers with meaningful traffic identified.")
        a("")

    # ── SECTION 5: TOP KEYWORDS ──────────────────────────────────────────────
    a("---")
    a("")
    a("## 5. Top Trending Keywords in Your Niche")
    a("")

    if not top_keywords:
        a("No keyword data loaded. Drop an Everbee keyword research export into `data/everbee-etsy/`.")
        a("")
    else:
        a("Ranked by Everbee Keyword Score (higher = better demand/competition ratio).")
        a("")
        a("| # | Keyword | Monthly searches | Competing listings | Score |")
        a("|---|---------|-----------------|-------------------|-------|")
        for i, kw in enumerate(top_keywords, 1):
            comp_str = f"{kw['competition']:,}" if kw['competition'] else "n/a"
            vol_str  = f"{kw['search_volume']:,}" if kw['search_volume'] else "n/a"
            a(f"| {i} | **{kw['keyword']}** | {vol_str} | {comp_str} | {kw['keyword_score']} |")
        a("")
        a("**How to use this list:** Add the top 5-8 keywords as tags on your highest-earning "
          "listings, and use them naturally in listing titles. Check which ones you're already "
          "using in your tags - if you're missing the top keywords, that's costing you traffic today.")
        a("")

    # ── SECTION 6: PRODUCT GAPS ──────────────────────────────────────────────
    a("---")
    a("")
    a("## 6. Product Gap Opportunities")
    a("")

    if not product_gaps:
        a("No gaps identified (or keyword + shop data both needed).")
        a("")
    else:
        a(f"{len(product_gaps)} keyword opportunities where you have no listing currently targeting them:")
        a("")
        for i, gap in enumerate(product_gaps[:12], 1):
            vol_str  = f"{gap['search_volume']:,}" if gap['search_volume'] else "n/a"
            comp_str = f"{gap['competition']:,}"   if gap['competition']   else "n/a"
            a(f"### {i}. `{gap['keyword']}`")
            a(f"- **Searches/month:** {vol_str}  |  **Competing listings:** {comp_str}  |  **Opportunity score:** {gap['keyword_score']}")
            a(f"- **Action:** {gap['recommendation']}")
            a("")

    # ── SECTION 7: MARKET INTELLIGENCE ──────────────────────────────────────
    a("---")
    a("")
    a("## 7. What Competitors Are Selling")
    a("")

    if market_insights:
        top_comps = market_insights.get("top_competitors", [])
        mkt_tiers = market_insights.get("market_tiers", [])

        if mkt_tiers:
            a("### Market price tier performance")
            a("")
            a("| Price range | Listings sampled | Avg sales/mo | Avg revenue/mo | Avg CVR |")
            a("|-------------|-----------------|-------------|---------------|---------|")
            for t in mkt_tiers:
                a(f"| {t['label']} | {t['listings']} | {t['avg_sales']} | {_p(t['avg_revenue'], 0)} | {_cvr(t['avg_cvr'])} |")
            a("")

        if top_comps:
            a("### Top competitor listings in your niche")
            a("")
            a("| Shop | Sales/mo | Revenue | Price | CVR | Title |")
            a("|------|----------|---------|-------|-----|-------|")
            for c in top_comps:
                title_s = c["title"][:50] + "..." if len(c["title"]) > 50 else c["title"]
                a(f"| {c['shop_name'][:16]} | {_n(c['monthly_sales'])} | "
                  f"{_p(c['monthly_revenue'], 0)} | {_p(c['price'], 0)} | "
                  f"{_cvr(c['conversion_rate'])} | {title_s} |")
            a("")
    else:
        a("No competitor market data loaded.")
        a("")

    # ── SECTION 7b: STRUCTURAL PRODUCT OPPORTUNITIES ────────────────────────
    if market_opps:
        a("---")
        a("")
        a("## 7b. Structural Product Opportunities")
        a("")
        a("Based on your shop data vs market performance, these are the highest-leverage structural changes:")
        a("")
        for i, opp in enumerate(market_opps, 1):
            priority_label = " ⚡ HIGH PRIORITY" if opp.get("priority") == "high" else ""
            a(f"### {i}. {opp['title']}{priority_label}")
            a(opp["detail"])
            a("")

    # ── SECTION 8: ACTION PLAN ───────────────────────────────────────────────
    a("---")
    a("")
    a("## 8. Action Plan: Getting to 30 Sales/Day")
    a("")

    actions = _build_action_plan(shop_stats, top_keywords, product_gaps, market_insights, market_opps)
    for i, (title, body) in enumerate(actions, 1):
        a(f"### Action {i}: {title}")
        a(body)
        a("")

    # ── FOOTER ──────────────────────────────────────────────────────────────
    a("---")
    a("")
    a(f"*Generated {today} — Switzertemplates Etsy Trend Analysis*")
    a(f"*Run again: `python3 skills/etsy-trend-analysis/main.py`*")

    content = "\n".join(L)
    output_path.write_text(content, encoding="utf-8")
    return str(output_path)


def _build_action_plan(shop_stats, top_keywords, product_gaps, market_insights, market_opps=None) -> list[tuple]:
    actions = []

    s = shop_stats or {}
    current_spd = s.get("sales_per_day", 0)

    # ── Action 1: Fix the dead listings ─────────────────────────────────────
    dead = s.get("dead_high_view", [])
    if dead:
        top3 = dead[:3]
        titles = "\n".join(f"  - {d['title'][:70]}" for d in top3)
        actions.append((
            "Fix your highest-traffic dead listings first (this week)",
            f"These 3 listings had the most views with zero sales last month:\n{titles}\n\n"
            f"For each one: update the first listing image to clearly show what's included "
            f"(a grid mockup works well). Rewrite the first 2 sentences of the description "
            f"to lead with the outcome. Check if the price is above market rate for similar products.\n\n"
            f"If even 2 of these convert at 1%, you add 2-3 sales/day immediately."
        ))

    # ── Action 2: Add more high-ticket listings ──────────────────────────────
    tiers = s.get("price_tiers", [])
    prem_tier = next((t for t in tiers if t["label"] == "$80+"), None)
    wix_earners = [
        e for e in s.get("top_earners", [])
        if "wix" in e["title"].lower() and e["monthly_revenue"] > 500
    ]
    if prem_tier and len(wix_earners) > 0:
        actions.append((
            "Add 5 more Wix website listings (biggest revenue lever)",
            f"Your {len(wix_earners)} Wix website listing(s) at $150 are your top revenue drivers. "
            f"You have very few of them relative to your total shop size. "
            f"Each new Wix listing that performs like your best ones adds $1,200-1,500/month.\n\n"
            f"Create 5 new Wix website listings targeting different niches from your keyword data: "
            f"therapists, nutritionists, beauty professionals, virtual assistants, course creators. "
            f"One listing per niche. Use the keyword data in Section 5 for titles and tags.\n\n"
            f"Impact: 5 new Wix listings averaging 8 sales/month = +40 sales/month (+1.3/day)."
        ))

    # ── Action 3: Price up cheap Instagram packs ─────────────────────────────
    cheap_tier = next((t for t in tiers if t["label"] == "Under $15"), None)
    if cheap_tier and cheap_tier["listing_count"] > 50:
        actions.append((
            "Bundle and reprice your $14 Instagram template packs",
            f"You have {cheap_tier['listing_count']} listings under $15 generating "
            f"{_p(cheap_tier['monthly_revenue'], 0)}/month. The market data shows "
            f"Instagram template bundles selling for $35-80 with similar or better conversion rates.\n\n"
            f"Test this: combine 3-4 of your template packs into a new 'Instagram Bundle' "
            f"listing at $38-45. Keep the individual packs live. If the bundle converts at "
            f"even 50% of your current rate, you make 3x the revenue per transaction.\n\n"
            f"Start with your best-selling $14 pack — create a 'complete pack' version at $35 "
            f"that includes more slides/templates and test it for 30 days."
        ))

    # ── Action 4: Target top keyword gaps ────────────────────────────────────
    if product_gaps:
        top3_gaps = product_gaps[:3]
        gap_list = "\n".join(
            f"  - `{g['keyword']}` (score {g['keyword_score']}, {g.get('search_volume') or 'n/a'} searches/mo)"
            for g in top3_gaps
        )
        actions.append((
            "Create new listings for your top 3 keyword gaps",
            f"These keywords have real demand and no current listing from you:\n{gap_list}\n\n"
            f"You don't need to build a new product for each one. Often an existing product "
            f"can be re-listed with a title and tags specifically targeting the gap keyword. "
            f"Create 1 new listing per gap keyword — keep the product the same, change the "
            f"title/tags/thumbnail to speak directly to that search.\n\n"
            f"This takes 1-2 hours and can start generating traffic within days."
        ))

    # ── Action 5: Reactivate dormant listings with tag rewrites ─────────────
    low_vis = s.get("dead_low_vis_count", 0)
    if low_vis > 30:
        kw_examples = " | ".join(kw["keyword"] for kw in top_keywords[:5]) if top_keywords else "your top keywords"
        actions.append((
            f"Batch-update tags on {_n(low_vis)} buried listings",
            f"{_n(low_vis)} listings have low visibility scores and zero sales — "
            f"they're effectively invisible in search.\n\n"
            f"You don't need to fix all of them. Pick 20-30 that are closest to your "
            f"best-selling product types and rewrite their titles and tags using this week's "
            f"top keywords: {kw_examples}.\n\n"
            f"Focus on listings where the product itself is good but the SEO is weak. "
            f"A tag rewrite on a buried listing costs nothing and can bring it back to life."
        ))

    # ── Fallback ─────────────────────────────────────────────────────────────
    if not actions:
        actions.append((
            "Load more Everbee data",
            "Drop your shop analytics CSV and keyword research CSV into `data/everbee-etsy/` "
            "and re-run for a full personalised action plan."
        ))

    return actions


def _p(val, decimals=2):
    if val is None: return "n/a"
    return f"${val:.{decimals}f}"

def _n(val):
    if val is None: return "n/a"
    return f"{int(val):,}"

def _cvr(val):
    if val is None: return "n/a"
    return f"{val:.2f}%"
