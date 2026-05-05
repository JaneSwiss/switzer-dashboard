"""
Switzertemplates — Everbee Keyword Preprocessor
Strips, deduplicates, and scores Everbee CSV exports before they hit the agent.
Usage: python3 main.py <path_to_everbee_csv> [--min-score 40] [--output markdown|csv]
"""

import pandas as pd
import argparse
import sys
from pathlib import Path

# Anomaly threshold — scores above this are likely Everbee data artifacts
ANOMALY_SCORE = 5000

def word_set(kw):
    return frozenset(kw.strip().lower().split())

def deduplicate(df):
    """Remove keywords that are just reorderings of the same words."""
    seen_sets = set()
    deduped = []
    for _, row in df.iterrows():
        ws = word_set(row['keyword'])
        if ws not in seen_sets:
            seen_sets.add(ws)
            deduped.append(row)
    return pd.DataFrame(deduped).reset_index(drop=True)

def preprocess(csv_path, min_score=40):
    df = pd.read_csv(csv_path)
    original_count = len(df)

    # Normalise columns
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
    rename_map = {}
    for col in df.columns:
        if 'keyword' in col and 'score' not in col:
            rename_map[col] = 'keyword'
        elif 'volume' in col:
            rename_map[col] = 'volume'
        elif 'competition' in col:
            rename_map[col] = 'competition'
        elif 'score' in col:
            rename_map[col] = 'score'
    df = df.rename(columns=rename_map)

    df['keyword'] = df['keyword'].str.strip().str.lower()
    df['score'] = pd.to_numeric(df['score'], errors='coerce').fillna(0)
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
    df['competition'] = pd.to_numeric(df['competition'], errors='coerce').fillna(0)

    # Flag and remove anomalies
    anomalies = df[df['score'] > ANOMALY_SCORE]
    df = df[df['score'] <= ANOMALY_SCORE]

    # Deduplicate
    df = deduplicate(df)

    # Filter by min score
    df = df[df['score'] >= min_score]

    # Add metadata
    df['chars'] = df['keyword'].str.len()
    df['valid_etsy_tag'] = df['chars'] <= 20
    df = df.sort_values('score', ascending=False).reset_index(drop=True)

    return df, anomalies, original_count

def format_markdown(df, anomalies, original_count, min_score):
    high = df[df['score'] >= 100]
    mid = df[(df['score'] >= min_score) & (df['score'] < 100)]

    lines = []
    lines.append("## KEYWORD DATA — Switzertemplates (Everbee Export)")
    lines.append(
        f"Processed: {len(df)} keywords | "
        f"Original: {original_count} | "
        f"Removed (dupes/low score): {original_count - len(df)}"
    )

    if len(anomalies) > 0:
        lines.append(
            f"\n⚠ {len(anomalies)} anomalous keywords skipped "
            f"(score >{ANOMALY_SCORE} — likely Everbee data artifacts): "
            + ", ".join(anomalies['keyword'].tolist())
        )

    lines.append(f"\n### HIGH OPPORTUNITY — score 100+ ({len(high)} keywords)")
    if len(high) == 0:
        lines.append("None found.")
    for _, r in high.iterrows():
        tag_flag = "✓ valid tag" if r['valid_etsy_tag'] else f"✗ {int(r['chars'])} chars — too long for tag"
        lines.append(
            f"- `{r['keyword']}` ({int(r['chars'])} chars) — "
            f"vol:{int(r['volume'])}, comp:{int(r['competition'])}, score:{int(r['score'])}  {tag_flag}"
        )

    lines.append(f"\n### MID OPPORTUNITY — score {min_score}-99 ({len(mid)} keywords)")
    if len(mid) == 0:
        lines.append("None found.")
    for _, r in mid.iterrows():
        tag_flag = "✓" if r['valid_etsy_tag'] else f"✗ too long ({int(r['chars'])} chars)"
        lines.append(
            f"- `{r['keyword']}` ({int(r['chars'])} chars) — "
            f"vol:{int(r['volume'])}, comp:{int(r['competition'])}, score:{int(r['score'])}  {tag_flag}"
        )

    lines.append(f"\n### VALID ETSY TAGS ONLY (≤20 chars, score {min_score}+)")
    valid = df[df['valid_etsy_tag']].head(15)
    for _, r in valid.iterrows():
        lines.append(
            f"- `{r['keyword']}` — score:{int(r['score'])}, vol:{int(r['volume'])}"
        )

    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Preprocess Everbee keyword CSV")
    parser.add_argument("csv_path", help="Path to Everbee CSV export")
    parser.add_argument("--min-score", type=int, default=40, help="Minimum keyword score to keep (default: 40)")
    parser.add_argument("--output", choices=["markdown", "csv", "both"], default="markdown")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(f"Error: file not found — {csv_path}", file=sys.stderr)
        sys.exit(1)

    df, anomalies, original_count = preprocess(csv_path, min_score=args.min_score)

    if args.output in ("markdown", "both"):
        md = format_markdown(df, anomalies, original_count, args.min_score)
        print(md)
        out_md = csv_path.with_suffix('.processed.md')
        out_md.write_text(md)
        print(f"\n[Saved: {out_md}]", file=sys.stderr)

    if args.output in ("csv", "both"):
        out_csv = csv_path.with_suffix('.processed.csv')
        df.to_csv(out_csv, index=False)
        print(f"[Saved: {out_csv}]", file=sys.stderr)

if __name__ == "__main__":
    main()
