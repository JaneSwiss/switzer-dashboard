"""
Switzertemplates — Etsy Listing Optimizer
Takes a listing's current title, description, and tags.
Rewrites them using keyword data for better SEO and conversion.

Usage:
  python3 main.py --listing data/listings/my-listing.json
  python3 main.py --interactive
"""

import anthropic
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

ROOT = Path(__file__).parent.parent.parent
REPORTS_DIR = ROOT / "reports" / "listing-optimizations"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Keyword loader ─────────────────────────────────────────────────────────

def load_keyword_data():
    """Load preprocessed keyword data if available."""
    data_dir = ROOT / "data" / "everbee-etsy"
    processed = sorted(data_dir.glob("*.processed.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if processed:
        return processed[0].read_text()
    # Fall back to raw CSV if processed version not found
    csvs = sorted(data_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if csvs:
        sys.path.insert(0, str(ROOT / "skills" / "keyword-preprocessor"))
        from main import preprocess, format_markdown
        df, anomalies, original_count = preprocess(csvs[0], min_score=40)
        return format_markdown(df, anomalies, original_count, min_score=40)
    return "No keyword data available."


# ── Prompt ─────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an Etsy SEO and conversion expert writing for Switzertemplates — a digital product business selling Wix website templates ($104 AUD), 3-in-1 business bundles ($129 AUD), and branding kits ($55 AUD) to female small business owners, coaches, and consultants. Shop has 27,700+ sales, 4.9 stars.

You will be given a listing's current title, description, and tags plus keyword opportunity data.

Output EXACTLY this structure — two bold numbered sections:

**2. TAGS**

Remove these [N] — [reason]:
- `tag name` — reason it should go

Replace with:
- `tag name` (N chars) — score [X], [reason]

Every tag must be ≤20 characters. Always show char count in brackets. Always show score if known. Verify every single tag is ≤20 chars before including it.

**3. DESCRIPTION**

[One sentence on the main problem with the current opening.]

Replace opening with:
"[Full rewritten opening — write the complete text, do not summarise or use placeholders]"

[Any other specific fixes on separate lines — price anchoring, structural changes, reframing. Each fix is one instruction followed by the exact replacement text in quotes.]

Also suggest a new title:

**New title:**
"[Full new title]"
Uses: [bullet each keyword with score and why it was chosen]

RULES:
- Never write anything before **2. TAGS**
- Never use: ensure, leverage, optimize, enhance, elevate
- Every tag must be verified ≤20 characters — count the characters yourself before suggesting
- Write the full rewritten description opening — not a summary of what to write
- Connect every change to either search volume, keyword score, or conversion logic
- Be specific. "Too generic" is not a reason. Explain exactly why it hurts and what replaces it"""


def build_prompt(listing, keyword_data):
    return f"""CURRENT LISTING:

Title: {listing['title']}

Tags: {', '.join(listing['tags'])}

Description:
{listing['description']}

KEYWORD DATA:
{keyword_data}

Analyze this listing and output the optimized tags, description, and title. Follow the exact format specified."""


# ── Interactive input ──────────────────────────────────────────────────────

def get_listing_interactive():
    print("\nPaste your listing details below.\n")

    title = input("Current title:\n> ").strip()
    print("\nCurrent tags (comma separated):")
    tags_raw = input("> ").strip()
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    print("\nCurrent description (paste it, then press Enter twice when done):")
    lines = []
    while True:
        line = input()
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)
    description = "\n".join(lines).strip()

    return {"title": title, "tags": tags, "description": description}


# ── Optimizer ──────────────────────────────────────────────────────────────

def optimize_listing(listing):
    keyword_data = load_keyword_data()

    print("\nSending to Claude...", file=sys.stderr)
    client = anthropic.Anthropic()

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": build_prompt(listing, keyword_data)
            }
        ]
    )

    result = message.content[0].text

    # Save output
    slug = listing["title"][:40].replace(" ", "-").lower()
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = REPORTS_DIR / f"{date_str}-{slug}.md"

    full_output = f"# Listing Optimization: {listing['title'][:60]}\n\n"
    full_output += f"**Original title:** {listing['title']}\n\n"
    full_output += f"**Original tags:** {', '.join(listing['tags'])}\n\n---\n\n"
    full_output += result

    out_path.write_text(full_output)
    print(f"\n[Saved: {out_path}]", file=sys.stderr)

    return result, out_path


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Optimize an Etsy listing")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--listing", help="Path to listing JSON file")
    group.add_argument("--interactive", action="store_true", help="Enter listing details manually")
    args = parser.parse_args()

    if args.interactive:
        listing = get_listing_interactive()
    else:
        path = Path(args.listing)
        if not path.exists():
            print(f"File not found: {path}", file=sys.stderr)
            sys.exit(1)
        listing = json.loads(path.read_text())

    result, path = optimize_listing(listing)
    print("\n" + result)


if __name__ == "__main__":
    main()
