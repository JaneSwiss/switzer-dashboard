"""
Report Writer — General Manager

Two outputs, both text (no markdown report file is the primary deliverable anymore —
the GitHub issue and the completion email are):

  write_recommendation_issue() — Step 1's GitHub issue body. Leads with the North Star
  pace, then what's working, then the actual recommendation with reasoning, then FYI
  close-to-page-1 items. Ends with a plain-language ask.

  write_completion_email() — Step 2's email, after production finishes. Short: restates
  what was understood and produced, links, cost tally, failures surfaced prominently.

Both mirror skills/report-generator/main.py's existing pattern: gather data -> one Claude
call -> text. If the Claude call fails, fall back to a plain template built directly from
the raw data, so Jane always gets something either way.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

GITHUB_REPO = "JaneSwiss/switzer-dashboard"
MODEL = "claude-sonnet-4-6"  # data-summarization, matching report-generator's own choice


def _client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Step 1: recommendation issue ────────────────────────────────────────────────

def _fallback_recommendation(candidates, gsc_data, ga4_data, wix_data, pin_perf) -> str:
    north_star = (ga4_data or {}).get("north_star", {})
    lines = ["## Pace to 10,000/month", ""]
    if north_star:
        lines.append(
            f"{north_star.get('monthly_sessions', '?')} sessions in the last 30 days "
            f"({north_star.get('pct_to_goal', '?')}% of goal), "
            f"trend vs prior 30 days: {north_star.get('trend_pct', 'n/a')}%"
        )
    else:
        lines.append("(GA4 data unavailable this run.)")

    lines += ["", "## What's working", ""]
    if wix_data:
        lines.append(
            f"Wix (last {wix_data.get('start_date', '?')} to {wix_data.get('end_date', '?')}): "
            f"{wix_data.get('total_sessions', '?')} sessions, "
            f"{wix_data.get('total_sales', '?')} in sales, {wix_data.get('total_orders', '?')} orders."
        )
    rankings = (gsc_data or {}).get("rankings", [])
    if rankings:
        top = sorted(rankings, key=lambda r: r["avg_position"])[:5]
        lines.append("Best-ranking tracked keywords:")
        for r in top:
            lines.append(f"- {r['keyword']} — position {r['avg_position']}, {r['clicks']} clicks")

    lines += ["", "## This week's recommendation", ""]
    for c in candidates:
        lines.append(f"- **{c['keyword']}** — {c.get('reasoning', '')}")
    lines += [
        "",
        "Reply on this issue with what you want — approve some, reject others, or ask for "
        "something else entirely, in your own words. I'll get started once you weigh in.",
    ]

    close = (gsc_data or {}).get("close_to_page_one", [])
    if close:
        lines += ["", "## FYI — not for this round", "", "Close to page 1, worth strengthening later:"]
        for item in close[:8]:
            lines.append(f"- {item['label']} ({item['kind']}) — position {item['avg_position']} for \"{item['query']}\"")

    return "\n".join(lines)


def write_recommendation_issue(candidates, gsc_data, ga4_data, wix_data, pin_perf) -> "tuple[str, str]":
    title = f"General Manager — week of {date.today().isoformat()}: recommendation ready"

    try:
        client = _client()
        prompt = f"""Write this week's General Manager recommendation as a GitHub issue body \
(markdown). Audience: Jane, the business owner. Tone: practical, direct, no fluff — she's \
busy and just needs to know what's happening and what to decide.

Structure, in this order:
1. "Pace to 10,000/month" — the North Star number, gap to goal, trend. Lead with this.
2. "What's working" — ranking movement, GA4 sessions, Wix sales/orders, top pins, from the \
data below. Be specific with numbers, don't pad with generic commentary.
3. "This week's recommendation" — the candidate keywords with their reasoning, and a clear \
plain-language ask: reply on this issue with her decision, in her own words.
4. "FYI — not for this round" — close-to-page-1 posts/pages, informational only.

DATA:
Candidates: {candidates}
Search Console: {gsc_data}
GA4: {ga4_data}
Wix Analytics: {wix_data}
Pin performance: {pin_perf}

Return ONLY the markdown body — no preamble, no meta-commentary."""

        response = client.messages.create(
            model=MODEL, max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        body = response.content[0].text.strip()
    except Exception as e:
        print(f"  Recommendation write via Claude failed ({e}) — using plain template.")
        body = _fallback_recommendation(candidates, gsc_data, ga4_data, wix_data, pin_perf)

    return title, body


# ── Step 2: completion email ────────────────────────────────────────────────────

def _fallback_completion(decision, run_summary) -> str:
    lines = [f"You approved: {', '.join(decision.get('approved', []) + decision.get('new_requests', [])) or '(nothing)'}"]
    if decision.get("rejected"):
        lines.append(f"You skipped: {', '.join(decision['rejected'])}")
    lines.append("")

    total_cost = 0.0
    for post in run_summary:
        title = post.get("title", post.get("keyword", "?"))
        lines.append(f"## {title}")
        if post.get("wix_ok"):
            lines.append(f"- Pushed to Wix as a draft")
        else:
            lines.append(f"- ⚠️ Wix draft failed — check logs")
        if post.get("push_ok") and post.get("slug"):
            lines.append(
                f"- Photos: https://github.com/{GITHUB_REPO}/tree/main/posts/images/{post['slug']}"
            )
        elif not post.get("push_ok"):
            lines.append("- ⚠️ Photo folder not confirmed pushed to GitHub yet — link omitted")
        lines.append(f"- Newsletter draft: {'ready' if post.get('newsletter_ok') else '⚠️ failed'}")
        lines.append(f"- Pins: {post.get('pin_message', 'unknown')}")
        if post.get("image_cost"):
            total_cost += post["image_cost"]
        if post.get("errors"):
            lines.append(f"- ⚠️ Issues: {'; '.join(post['errors'])}")
        lines.append("")

    if total_cost:
        lines.append(f"Estimated image cost this run: ${total_cost:.2f}")

    return "\n".join(lines)


def write_completion_email(decision, run_summary) -> "tuple[str, str]":
    subject = f"General Manager — this week's posts are ready ({date.today().isoformat()})"

    # Compute the real photo-folder URL in code, not left to the model to construct —
    # it must appear verbatim and correctly or it's useless to Jane.
    enriched = []
    for post in run_summary:
        post = dict(post)
        if post.get("push_ok") and post.get("slug"):
            post["photo_folder_url"] = f"https://github.com/{GITHUB_REPO}/tree/main/posts/images/{post['slug']}"
        else:
            post["photo_folder_url"] = None
        enriched.append(post)

    try:
        client = _client()
        prompt = f"""Write a short completion email to Jane summarizing what the General \
Manager just produced, based on her decision and the run results below. Tone: practical, \
direct, brief — this is a status update, not a report.

Open by restating exactly what you understood her to have decided (so she can catch a \
misread immediately). Then per post: its title, whether the Wix draft succeeded, the \
photo_folder_url field COPIED VERBATIM AND IN FULL if it is not null (this is a real \
clickable link Jane needs — never paraphrase, shorten, or omit it when present; if it is \
null, say the photo folder isn't confirmed pushed yet), newsletter status (it is always a \
DRAFT waiting for her review — nothing sends automatically, never say "sent"), pin status \
(also always drafts, never say "published" or "scheduled"). End with the total estimated \
image cost and any failures called out clearly, not buried.

DECISION: {decision}
RUN RESULTS: {enriched}

Return ONLY the email body, plain text (no markdown headers, this is an email) — no \
preamble."""

        response = client.messages.create(
            model=MODEL, max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        body = response.content[0].text.strip()
    except Exception as e:
        print(f"  Completion email write via Claude failed ({e}) — using plain template.")
        body = _fallback_completion(decision, run_summary)

    return subject, body
