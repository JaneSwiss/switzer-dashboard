"""
Switzertemplates — Etsy Growth Report Generator
Combines keyword data + competitor data + shop config,
sends to Claude, and saves the full report to /reports/

Run manually:   python3 main.py
Run with data:  python3 main.py --everbee path/to/export.csv
"""

import anthropic
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# ── Paths ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent.parent  # switzertemplates/
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

COMPETITOR_DIR = ROOT / "data" / "competitors"
COMPETITOR_DIR.mkdir(parents=True, exist_ok=True)

SHOP_CONFIG_PATH = ROOT / "context" / "shop-config.json"

# ── Shop config (static facts about the shop) ─────────────────────────────

DEFAULT_SHOP_CONFIG = {
    "shop_name": "Switzertemplates",
    "goal": "30 high-ticket sales per day ($50+ products)",
    "current_daily_sales": 11.9,
    "current_monthly_revenue_aud": 9514,
    "top_listings": [
        {
            "name": "Wix Website Template - Coaching",
            "monthly_views": 1389,
            "monthly_orders": 10.2,
            "cvr": "0.73%",
            "monthly_revenue_aud": 1061
        },
        {
            "name": "3-in-1 Coaching Business Bundle",
            "monthly_views": 279,
            "monthly_orders": 0.8,
            "cvr": "0.29%",
            "monthly_revenue_aud": 104
        },
        {
            "name": "1000 Branding Kit Templates",
            "monthly_views": 1171,
            "monthly_orders": 5.6,
            "cvr": "0.48%",
            "monthly_revenue_aud": 315
        }
    ],
    "products": [
        {"name": "3-in-1 Business Bundle", "price_aud": 129},
        {"name": "Premade Wix Website", "price_aud": 104},
        {"name": "1000+ Branding Kit", "price_aud": 55},
        {"name": "Instagram Template Pack", "price_aud": 14}
    ],
    "known_opportunities": [
        "digital marketer keyword (score 710) - no listing targeting this yet",
        "bold instagram post keyword (score 130) - no listing targeting this yet",
        "3-in-1 bundle CVR at 0.29% - worst in shop",
        "44 dead Wix listings needing niche-specific keyword rewrites"
    ]
}


def load_shop_config():
    if SHOP_CONFIG_PATH.exists():
        with open(SHOP_CONFIG_PATH) as f:
            return json.load(f)
    return DEFAULT_SHOP_CONFIG


# ── Data loaders ───────────────────────────────────────────────────────────

def load_keyword_data(everbee_csv_path=None):
    """Run preprocessor on Everbee CSV and return markdown output."""
    # Look for most recent Everbee CSV in data folder if not specified
    if not everbee_csv_path:
        data_dir = ROOT / "data" / "everbee-etsy"
        data_dir.mkdir(parents=True, exist_ok=True)
        csvs = sorted(data_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not csvs:
            return "No Everbee CSV found. Drop latest export into data/everbee-etsy/ folder."
        everbee_csv_path = csvs[0]
        print(f"  Using Everbee file: {everbee_csv_path.name}", file=sys.stderr)

    # Import and run preprocessor
    sys.path.insert(0, str(ROOT / "skills" / "keyword-preprocessor"))
    from main import preprocess, format_markdown
    df, anomalies, original_count = preprocess(everbee_csv_path, min_score=40)
    return format_markdown(df, anomalies, original_count, min_score=40)


def load_competitor_data():
    """Load most recent competitor report markdown files."""
    reports = sorted(COMPETITOR_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        return "No competitor data found. Run the competitor scraper first."

    # Load up to 3 most recent reports
    combined = []
    for r in reports[:3]:
        combined.append(f"### {r.stem}\n{r.read_text()}")
    return "\n\n".join(combined)


# ── Prompt builder ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Etsy growth strategist for Switzertemplates — a digital product business selling Wix website templates ($104 AUD), 3-in-1 business bundles ($129 AUD), and branding kits ($55 AUD) to female small business owners, coaches, and consultants.

You are writing the bi-weekly Etsy Growth Report. Your job is to analyse all the data provided and produce a clear, specific, actionable report.

Follow this EXACT structure:

---

## ETSY GROWTH REPORT
*[date range] | Generated [date]*

### SHOP SNAPSHOT
One line each — no padding:
- Daily sales: [current] → goal: 30/day (gap: [X]/day)
- Monthly revenue: AUD [X] → what's needed for goal: ~AUD [X]
- Biggest CVR problem: [specific listing and why]

### PRIORITY TASK LIST
Numbered 1-10. Ranked by revenue impact. Each task:
**[N]. [Task name]**
What: [exactly what to do — specific enough to action immediately]
Why: [the data behind it — one line]
Impact: [what this moves toward the 30/day goal]
Effort: Low / Medium / High

### KEYWORD OPPORTUNITIES
3-5 keywords worth acting on RIGHT NOW. For each:
- `keyword` (X chars) — score X, vol X — [one line on what to do with it]

### COMPETITOR INTELLIGENCE
What top competitors are doing that Switzertemplates isn't. Specific gaps to exploit. No padding.

### DEAD LISTINGS TO FIX OR CUT
Specific listings with high views but low sales. One line each: listing name — problem — fix or cut.

---

RULES:
- Never write generic advice. Every sentence must connect to specific data provided.
- Never use: ensure, leverage, optimize, enhance, elevate
- If data is missing, say so in one line and move on — don't pad
- Priority task list must always be ranked by revenue impact, not effort
- Be blunt. If something is losing sales every day, say so."""


def build_user_prompt(shop_config, keyword_data, competitor_data):
    today = datetime.now().strftime("%d %b %Y")
    return f"""Today's date: {today}

## SHOP DATA
{json.dumps(shop_config, indent=2)}

## KEYWORD DATA (from Everbee)
{keyword_data}

## COMPETITOR DATA
{competitor_data}

Generate the Etsy Growth Report now. Follow the exact structure specified. Be specific and blunt."""


# ── Report generator ───────────────────────────────────────────────────────

def generate_report(everbee_csv_path=None):
    print("Loading data...", file=sys.stderr)
    shop_config = load_shop_config()
    keyword_data = load_keyword_data(everbee_csv_path)
    competitor_data = load_competitor_data()

    print("Sending to Claude...", file=sys.stderr)
    client = anthropic.Anthropic()

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": build_user_prompt(shop_config, keyword_data, competitor_data)
            }
        ]
    )

    report = message.content[0].text

    # Save report
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = REPORTS_DIR / f"etsy-growth-report-{date_str}.md"
    out_path.write_text(report)

    # Also save as latest.md so the dashboard always knows where to look
    latest_path = REPORTS_DIR / "latest-etsy-report.md"
    latest_path.write_text(report)

    print(f"\n[Saved: {out_path}]", file=sys.stderr)
    print(f"[Also saved as: {latest_path}]", file=sys.stderr)

    return report, out_path


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate Etsy Growth Report")
    parser.add_argument("--everbee", help="Path to Everbee CSV export (optional — uses latest in data/everbee/ if not set)")
    args = parser.parse_args()

    report, path = generate_report(everbee_csv_path=args.everbee)
    print("\n" + report)


if __name__ == "__main__":
    main()
