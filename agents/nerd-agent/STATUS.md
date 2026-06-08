# Nerd Agent — Status

*A living file. Update it at the end of any session where we build/change something
meaningful on this agent — overwrite stale sections, don't just append.*

**Last updated:** 2026-06-08 (later session — fixed shallow-extraction bug, re-ingested all sources at depth, added 3 more videos, rewrote summary/checklist/dashboard with per-point source links)

---

## What it does

Ingests external research (YouTube videos, Substack/blog articles, pasted newsletter
text, plain `.txt` notes), extracts key points + business ideas via Claude, and writes
synthesized topic insight files to `context/nerd-insights/` for other agents to reuse.
Also maintains a `nerd_agent` tab in the main dashboard (`dashboard_data.json`).

Run from project root: `python3 agents/nerd-agent/nerd_agent.py <command> ...`
Commands: `learn`, `report`, `list`, `share` — see the module docstring for full usage.

## Confirmed working

- `learn --url <youtube/substack/article URL>` — fetches, extracts insights, stores entry,
  updates topic insight file + dashboard
- `learn --text "..." --source "title"` — ingest pasted text directly
- `learn --batch <file>` — ingest a list of URLs
- `report --status` / `report --all` / `report --topic <t>` — regenerate insight files
- `list`, `list --topic`, `list --id` — browse the knowledge base
- `share` — write insight files to `context/` and refresh dashboard

## Changed this session (2026-06-08)

**Removed PDF + image-description (vision) support entirely.** A prior session had
added `fetch_pdf` plus a vision sub-pipeline (extract embedded images → filter/dedupe/
downsize → caption with a cheap model → fold into the text). It was half-wired (the
`client` was never actually passed through, so it was dead code) and added real
complexity (PyMuPDF + Pillow deps, a second model in the loop, an image-description cache).

**Why it's gone:** we'd been hitting the "approaching 1M-token context window" wall while
testing PDF ingestion. That ceiling is about *the Claude Code session's* context, not the
agent's own API calls (those are capped at `MAX_TEXT_CHARS = 15_000` chars/source and run
as isolated requests) — it was almost certainly caused by large/scanned PDFs being read
directly into the chat session while debugging extraction. Still, the PDF path was the
most fragile, highest-maintenance part of the agent for a feature Jane doesn't strictly
need — she can already extract PDF text via ChatGPT reliably.

**Replacement: `learn --txt <path/to/file.txt>`** — reads a plain text file off disk and
routes it through the existing pasted-text pipeline (`_learn_text`). New workflow:
1. Feed the PDF to ChatGPT, have it extract/summarize the text
2. Save that as a `.txt` file
3. `python3 agents/nerd-agent/nerd_agent.py learn --txt "/path/to/notes.txt" --topics "pinterest-marketing"`

## Resolved earlier this session — sample data cleared

The dashboard's `nerd_agent` section had previously shown "2 sources processed" (fake
"Tony Hill — Pinterest traffic" email entries, IDs `f9949a8d`/`7f692708`) and there was a
fully-written `context/nerd-insights/pinterest-marketing.md` to match — but the real
`knowledge/sources.json` / `knowledge/entries/` / `logs/ingested.json` were all empty, and
those entry IDs existed nowhere else on disk. Jane confirmed (2026-06-08): **it was sample/
placeholder data**, hand-written to mock up the dashboard tab — never a real ingest.

Cleared it properly using the agent's own code paths (not hand-edited) — ran
`update_dashboard()` / `write_insights_index()` against the real empty `sources.json`,
and overwrote the fabricated `pinterest-marketing.md` with a short note explaining it
was cleared placeholder text.

## Changed later this session — extraction rewritten to stop inventing content

Jane flagged that the agent was sometimes producing "his own assumptions or irrelevant
ideas" instead of faithfully reporting what a source actually says. Looking at the code,
the cause was structural: `extract_insights` asked Claude to generate `business_ideas`
and `actionable_steps` *while* reading each individual source — i.e. invent business
applications in the same breath as summarising, often from a single source in isolation.
That's where "fantasy instead of fidelity" was coming from.

**Fix — split learning from suggesting into two clearly separate stages:**
- `extract_insights` (per-source): now asks ONLY for `topics`, `key_points`, and
  `summary` — explicitly instructed to stay strictly grounded in what the source says,
  no interpretation/generalisation/business advice/assumptions, and to say so honestly
  if a source is thin rather than padding it out. `business_ideas`/`actionable_steps`
  fields removed entirely (also dropped from `store_entry`'s `entry_data`).
- `write_topic_report` (cross-source synthesis): rewritten so the generated markdown has
  two clearly labelled, separated sections — **"What We Learned"** (faithful synthesis of
  key points + summaries actually captured from sources) and **"Implementation Suggestions
  for Switzertemplates"** (explicitly framed as the agent's own proposals, each one tied
  back to a specific learning, generated only after and based on Part 1 — not from outside
  assumptions). Old "Business Ideas" / "Actionable Steps" sections removed.
- Dashboard's per-topic stats now track `key_points_captured` instead of `actionable_steps`.

Confirmed working end-to-end on real data (see below) — "What We Learned" sections read as
faithful, source-traceable accounts; "Implementation Suggestions" cite exactly which source/
learning each proposal builds on.

## First real ingest — knowledge base now populated (2026-06-08)

Jane dropped source files into `agents/nerd-agent/source-files/`:
- `Tony-Hills-Newsletters.txt` — Pinterest strategy newsletter notes (ingested via `--txt`)
- `Youtube-links.pdf` — a PDF of 6 YouTube links (the agent has no PDF support by design;
  extracted the underlying URLs from the PDF's link annotations via `strings <file> | grep http`,
  wrote them to a batch file, ran `learn --batch`)

**7 sources ingested, 0 errors:**
1. Tony Hills Newsletters (email) — `pinterest-marketing`
2. How To Use Pinterest In 2026 - Step by Step Guide (youtube) — `pinterest-marketing, content-creation`
3. The Pinterest Strategy Etsy Sellers Should Be Using in 2026 | Jenna Kutcher & Dylan Jahraus (youtube) — `pinterest-marketing, business-strategy, content-creation`
4. How to Grow on Pinterest in 2026 (Try these NEW tools!) (youtube) — `pinterest-marketing, content-creation`
5. The Pinterest Strategy That's Actually Working for Me in 2026 (youtube, `v=TfOhKeciZpU`) — `pinterest-marketing, content-creation`
6. How to Get Started with Pinterest in 2026 (Important Updates) (youtube) — `pinterest-marketing, content-creation`
7. The Pinterest Strategy That's Actually Working for Me in 2026 (youtube, `v=m9vnKPnVocA` — different video, same title as #5) — `pinterest-marketing, content-creation`

Topic insight files regenerated for real: `context/nerd-insights/pinterest-marketing.md`,
`content-creation.md`, `business-strategy.md`, plus `_index.md`. Dashboard `nerd_agent`
section reflects the real 7-source state (`total_sources_processed: 7`,
`sources_by_type: {youtube: 6, email: 1}`).

## Fixed a major bug — extraction was truncating long videos to ~20% (2026-06-08)

Jane reviewed the dashboard's Pinterest summary and called it out directly: *"extremely
short and not specific at all... general bullshit... not everything that's in these
YouTube videos."* She was right — root cause was structural, not a prompting nuance:

- `MAX_TEXT_CHARS` was `15_000`. The agent computed `word_count` on the **full** transcript
  but then **truncated `text` to 15K chars before sending it to Claude**. A 41-88 minute
  video runs 5,000-11,000+ words / ~30,000-69,000 characters — so Claude was only ever
  seeing the **first ~20-30%** of each long source. Combined with a prompt that asked for
  just "3-8 key points" and a "2-3 paragraph" summary at `max_tokens=2000`, the result was
  exactly what Jane described: thin, generic, front-loaded summaries.

**Fix, applied at the root:**
- `MAX_TEXT_CHARS`: `15_000` → `100_000` (covers even the longest transcripts whole)
- `extract_insights` prompt: now explicitly instructs Claude to "read this {type} closely
  AND COMPLETELY"; `key_points` raised from "3-8 specific points" to **"8-20 specific
  points... spanning the source's whole runtime/length, not just its opening minutes"**;
  `summary` raised from "2-3 paragraphs" to **"4-6 paragraphs... preserving specific names,
  numbers, tools, and step-by-step detail rather than flattening into generalities"**, plus
  an explicit rule against compressing concrete claims into vague generalities
- `max_tokens`: `2000` → `6000` (so the richer output has room to land)

**Verified empirically** — re-running all sources with `--force` produced **zero
truncation-warning messages** (vs. routine truncation before) and **17-20 key points per
source** (vs. 7-9 before): roughly **2x the captured detail per source**, now spanning
each video's full runtime rather than its opening third.

## Re-ingested everything + added 3 more videos — 10 sources total (2026-06-08)

Re-ran `learn --batch ... --force` on the original 6 YouTube sources plus the 1 newsletter
(all re-extracted at the new depth), then Jane supplied 3 more video URLs (with Pinterest
tracking params `&pp=...` — the existing video-ID regex `(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})`
handled them with no code changes needed) and those were ingested fresh:

8. How I'm Growing my Blog with Pinterest in 2026 (youtube, `v=I_MbkHhAeF4`)
9. Why Your Pinterest Traffic Isn't Growing in 2026 (Fix This First) (youtube, `v=zE0d-LA2yOI`)
10. (youtube, `v=QkXSH_cLPQ4`) — `og:title` scrape returned nothing usable, so this entry
    is stored with its raw video ID as the title (pre-existing graceful-degradation
    behaviour, not a new bug); the transcript itself fetched and analysed fine (1,595
    words, 17 key points)

`knowledge/sources.json` and `knowledge/entries/*.json` now hold all 10. Topic insight
files regenerated: `pinterest-marketing.md` (10 sources), `content-creation.md` (9),
`business-strategy.md` (1).

## Rewrote the consolidated Pinterest summary with per-point source links (2026-06-08)

Jane added a standing requirement on top of the depth fix: *"each important point of the
summary should be backed up with the link to the source."* Rewrote
`context/nerd-insights/pinterest-summary.md` from scratch around the richer 10-source
material — every claim now carries an inline link back to its exact YouTube URL (or a
plain "(Tony Hills Newsletters)" citation for the one text-based source, since it has no
public URL). The new summary surfaces the specifics that were getting lost before: named
tools (PinClicks, Tailwind's keyword tool + Turbo Pin, Pin Generator, Interest Explorer),
named techniques (fresh pins, alphabet soup method, the two concrete pinning "recipes,"
the 6-cause traffic-stall framework), and exact figures (600M MAU, 96% unbranded searches,
45 followers → 1M impressions, 180,000 clicks in 90 days, 2:3 / 1000×1500px spec, etc.).

Also updated `pinterest-action-checklist.md` to reference the same named tools/techniques/
framework (added a new "Diagnosing & troubleshooting" section based on the 6-cause model),
and replaced the embedded Pinterest summary prose inside `switzer_ai_dashboard.html`'s
"Pinterest" card (~lines 387-394) with matching source-linked paragraphs (`[source]` links
styled in `var(--choc)`), and bumped the "Based on 7 sources" footer line to 10.

## Next steps

1. Jane to review the rewritten `pinterest-summary.md`, `pinterest-action-checklist.md`,
   and the dashboard Nerd tab — confirm the new depth + per-point source links read the
   way she wants
2. `.claude/settings.local.json` had unrelated permission entries (incl. a live Netlify
   token typed in plain text) mixed into an earlier diff — cleaned up; **the Netlify
   token (`nfp_TuZK1wZunkFhrvUhx8DJMGitDhbxjBaB4d50`) should still be rotated** since it
   sat in a working-tree file
3. Whatever Jane wants to build next on this agent
