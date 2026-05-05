# etsy-trend-analysis

Weekly Etsy trend report for Switzertemplates. Combines live Etsy API data with Everbee keyword exports to surface what's working, what isn't, and where the gaps are.

---

## What it produces

Report saved to `outputs/etsy-sales/etsy-trend-report-YYYY-MM-DD.md` with:

1. **Top trending keywords** - ranked by demand vs competition (opportunity score)
2. **Underperforming listings** - flagged with specific issues and fix recommendations
3. **Product gap opportunities** - high-demand keywords you have no listing for yet
4. **Competitor insights** - top performing competitor listings from your Everbee data
5. **Recommended actions** - prioritised list of what to do this week

---

## Setup

Install dependencies (from project root):

```bash
pip install -r skills/etsy-trend-analysis/requirements.txt
```

The `ETSY_API_KEY` in `.env` is used automatically.

---

## Running it

From the project root:

```bash
python skills/etsy-trend-analysis/main.py
```

---

## Adding Everbee data

Drop CSV exports from Everbee into `data/everbee-etsy/`. The script auto-detects:

- **Keyword research exports** - identifies trending keywords and opportunity scores
- **Listing analysis exports** - surfaces competitor performance and product gaps

Both formats are supported. You can add multiple files - they are all merged.

**Tip:** export a fresh Everbee keyword set for your top 3-5 niche terms each week before running the report.

---

## What the Etsy API provides

With the API key alone (no OAuth), the script fetches:
- Shop overview (listing count, reviews, favourites)
- All active listings with: title, tags, views, saves, price, days listed

Listing-level order counts require OAuth and are not currently fetched. Views-per-day and save rate are used as proxy signals for listing health.

---

## Output example

```
outputs/etsy-sales/etsy-trend-report-2026-04-21.md
```

Each run creates a new dated file - old reports are kept for comparison.
