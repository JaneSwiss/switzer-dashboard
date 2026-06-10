# Nerd Agent — Status

*A living file. Update it at the end of any session where we build/change something
meaningful on this agent — overwrite stale sections, don't just append.*

**Last updated:** 2026-06-10 (multiple rewrites of the summary, checklist, and dashboard
output until Jane was happy — see full history below)

---

## What it does

Ingests external research (YouTube videos, Substack/blog articles, pasted newsletter
text, plain `.txt` notes), extracts key points + business ideas via Claude, and writes
synthesized topic insight files to `context/nerd-insights/` for other agents to reuse.
Also maintains a `nerd_agent` tab in the main dashboard (`dashboard_data.json`).

Run from project root: `python3 agents/nerd-agent/nerd_agent.py <command> ...`
Commands: `learn`, `report`, `list`, `share` — see the module docstring for full usage.

## Confirmed working

- `learn --url <youtube/substack/article URL>` — fetches transcript, extracts insights,
  stores entry, updates topic insight file + dashboard
- `learn --txt <path/to/file.txt>` — ingest a plain text file (use for newsletter notes,
  ChatGPT-extracted PDF text, etc.)
- `learn --batch <file>` — one URL per line, ingest in sequence
- `learn --force` — re-ingest a URL that already exists in the knowledge base
- `report --status` / `report --all` / `report --topic <t>` — regenerate insight files
- `list`, `list --topic`, `list --id` — browse the knowledge base
- `share` — write insight files to `context/` and refresh dashboard

## Current knowledge base — 10 sources, all Pinterest

All 10 sources are about Pinterest marketing. No other topics yet.

| # | Title | Type | Entry ID |
|---|---|---|---|
| 1 | Tony Hills Newsletters | text (.txt) | 3fca9459 |
| 2 | How To Use Pinterest In 2026 - Step by Step Guide | youtube | 54872267 |
| 3 | The Pinterest Strategy Etsy Sellers Should Be Using in 2026 (Jenna Kutcher & Dylan Jahraus) | youtube | 2dfd7b65 |
| 4 | How to Grow on Pinterest in 2026 (Try these NEW tools!) | youtube | ee788c1f |
| 5 | The Pinterest Strategy That's Actually Working for Me in 2026 (`v=TfOhKeciZpU`) | youtube | 7bc04b29 |
| 6 | How to Get Started with Pinterest in 2026 (Important Updates) | youtube | 3948dfc6 |
| 7 | The Pinterest Strategy That's Actually Working for Me in 2026 (`v=m9vnKPnVocA`) | youtube | 6ea5df36 |
| 8 | How I'm Growing my Blog with Pinterest in 2026 | youtube | 38c2578b |
| 9 | Why Your Pinterest Traffic Isn't Growing in 2026 (Fix This First) | youtube | 0e4879ee |
| 10 | (`v=QkXSH_cLPQ4` — title scrape failed, stored as video ID) | youtube | 21529eed |

Entry files: `agents/nerd-agent/knowledge/entries/*.json`
Topic insight files: `context/nerd-insights/pinterest-marketing.md`, `content-creation.md`, `business-strategy.md`

## Output files — current state

Three files are the deliverables. Read these to understand what the agent has produced:

**`context/nerd-insights/pinterest-summary.md`**
The consolidated Pinterest summary. Written in plain English, no generic intro or
statistics. Structured around actionable sections: keyword research (PinClicks SOP,
annotations, Interest Explorer, Pinterest Trends seasonal method), two pinning recipes
(3-pin simple and 6-pin rotation), what gets a pin clicked vs. saved (with spec table),
the 6-cause traffic-stall diagnostic with fixes, tool breakdowns (PinClicks, Tailwind
Turbo Pin, Pin Generator, Interest Explorer), and algorithm-change protocol. Includes
examples from sources throughout (the "day hike first aid kit" PinClicks example,
Megan's exact board-rotation method, the 180k clicks account, the Etsy cart finding).
No blah-blah filler, no general stats paragraphs.

**`context/nerd-insights/pinterest-action-checklist.md`**
Action checklist specifically for Switzertemplates. Written for Jane, not for someone
starting from scratch. Assumes she's already using Tailwind, posting ~10 pins/day, and
using PinClicks. Contains only things she's likely not doing yet that could move the
needle: PinClicks gap-finding (targeting old/unsaturated results), annotations workflow,
Megan's 6-pin/3-board rotation on existing top-converting products, mining existing
analytics for top-click pins and making 5 variations of each, seasonal Trends calendar,
Turbo Pin trial, and the traffic-leak diagnostic.

**`context/nerd-insights/pinterest-action-checklist.md`** ← same file
**`dashboard_data.json`** — `nerd_agent` section updated to reflect 10 sources.

## Dashboard tab — Nerd

The Nerd tab in `switzer_ai_dashboard.html` shows:

- **"Pinterest" card** (dark red title + icon): four actionable sections with bullet
  lists — keyword research, pin scheduling recipes, what gets clicked, and the 6-cause
  traffic-stall framework. Each section has a "→ full detail" link to the named anchor
  in `pinterest-summary.md`. "View action checklist" button in dark red on the left.
- **"Recent sources" table**: auto-populated from `dashboard_data.json`.
- The old "Knowledge base" card (stats + how-to-run description) was removed — Jane
  found it useless.

Colors used: `var(--red-mid)` (#C0392B) for Pinterest title, icon, button, and "→" links.

## Key code changes made (for context if the code needs touching)

**`nerd_agent.py` — extraction depth fixes:**
- `MAX_TEXT_CHARS`: `15_000` → `100_000` — the old limit was truncating 41-88 minute
  video transcripts to ~20% of their content before Claude ever saw them
- `extract_insights` prompt: `key_points` raised from "3-8 points" to "8-20 points
  spanning the full runtime"; `summary` raised from "2-3 paragraphs" to "4-6 paragraphs
  preserving specific names, numbers, tools, and step-by-step detail"; added explicit
  rule against compressing concrete claims into vague generalities
- `max_tokens` in `extract_insights`: `2000` → `6000`
- Result: 17-20 key points per source (vs. 7-9 before), zero truncation warnings

**`nerd_agent.py` — extraction fidelity fix (earlier session):**
- `extract_insights` previously asked for `business_ideas` and `actionable_steps` at
  the same time as summarising — this caused the agent to invent business applications
  while reading individual sources. Those fields were removed entirely.
- Now: `extract_insights` is strictly faithful (topics + key_points + summary only).
  `write_topic_report` does the synthesis and clearly labels "What We Learned" vs.
  "Implementation Suggestions for Switzertemplates" as separate sections.

**PDF support removed** (earlier session):
- `fetch_pdf` and the vision sub-pipeline (image extraction + captioning) were removed —
  dead code that added PyMuPDF/Pillow deps and a second model in the loop.
- Replacement workflow: feed the PDF to ChatGPT, save the extracted text as `.txt`,
  then `learn --txt "/path/to/notes.txt"`.

## Summary of summary rewrites (so you understand the iteration history)

The consolidated summary went through multiple rewrites based on Jane's feedback:

1. **First version** — too short, too generic, "general bullshit"
2. **Added source links** — every claim got a `[source]` YouTube link — Jane wanted to
   understand HOW things worked, not just citations
3. **"Workflow 1-6" numbered structure** — more detail, step-by-step — Jane called it
   "robotic, technical, gives me zero understanding of how this works"
4. **Conversational rewrite** — second-person, plain English — closer, but still included
   general stats paragraphs ("Pinterest is a search engine…") and timeline info she
   didn't want
5. **Current version** — no general intro, no stats paragraphs, no blah-blah, straight
   to actionable steps with examples from sources. "→ full detail" links from the
   dashboard instead of per-claim [source] links.

**Root cause of repeated revisions:** The `summary` and `key_points` fields in the
extracted entries already contained full step-by-step detail. The consolidation step kept
compressing that into name-drops and statistics. The fix was to read the full `summary`
field of each entry (not just `key_points`) and actually transfer the process detail.

## Checklist history

The action checklist was originally written for someone starting from scratch — covered
account setup, "try Tailwind," "post consistently," etc. Jane pointed out she already uses
Tailwind, already posts ~10 pins/day, already uses PinClicks. Rewritten to skip all of
that and focus on six specific techniques from the source material she's likely not using
yet (see checklist file for detail).

The checklist also had stale references to "Workflow 2" from when the summary used
numbered workflow headers. Those references are now removed.

## Next steps / what to work on next

1. **Feed more sources** when Jane has them. Run:
   `python3 agents/nerd-agent/nerd_agent.py learn --url <url>`
   or for batch: create a `.txt` file with one URL per line and run `learn --batch`.

2. **The Netlify token `nfp_TuZK1wZunkFhrvUhx8DJMGitDhbxjBaB4d50`** was found in plain
   text in `.claude/settings.local.json` in an earlier session. It should be rotated —
   it's been in a version-controlled file.

3. **Add a second topic** when Jane starts feeding the agent sources on a new subject
   (email marketing, SEO, etc.). The agent handles multiple topics automatically — just
   supply a `--topics` flag when ingesting or let it auto-classify.
