# Nerd Agent — Status

*A living file. Update it at the end of any session where we build/change something
meaningful on this agent — overwrite stale sections, don't just append.*

**Last updated:** 2026-06-10 (second session — added AI topic, ingested 10 AI/Claude videos,
built AI card in dashboard)

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
- `learn --topics <topic>` — override auto-detected topic (e.g. `--topics ai-tools`)
- `report --status` / `report --all` / `report --topic <t>` — regenerate insight files
- `list`, `list --topic`, `list --id` — browse the knowledge base
- `share` — write insight files to `context/` and refresh dashboard

## Current knowledge base — 20 sources, 2 topics

| Topic | Sources | Insight file |
|-------|---------|-------------|
| Pinterest marketing | 10 | `context/nerd-insights/pinterest-marketing.md` |
| AI tools & making money with AI | 10 | `context/nerd-insights/ai-tools.md` |

### Pinterest sources (10)

| # | Title | Entry ID |
|---|---|---|
| 1 | Tony Hills Newsletters | 3fca9459 |
| 2 | How To Use Pinterest In 2026 - Step by Step Guide | 54872267 |
| 3 | The Pinterest Strategy Etsy Sellers Should Be Using in 2026 | 2dfd7b65 |
| 4 | How to Grow on Pinterest in 2026 (Try these NEW tools!) | ee788c1f |
| 5 | The Pinterest Strategy That's Actually Working for Me in 2026 (`v=TfOhKeciZpU`) | 7bc04b29 |
| 6 | How to Get Started with Pinterest in 2026 (Important Updates) | 3948dfc6 |
| 7 | The Pinterest Strategy That's Actually Working for Me in 2026 (`v=m9vnKPnVocA`) | 6ea5df36 |
| 8 | How I'm Growing my Blog with Pinterest in 2026 | 38c2578b |
| 9 | Why Your Pinterest Traffic Isn't Growing in 2026 (Fix This First) | 0e4879ee |
| 10 | (`v=QkXSH_cLPQ4`) | 21529eed |

### AI sources (10)

| # | Title | Entry ID |
|---|---|---|
| 1 | Why You Must Stop Selling Your Time for Money | ce754acb |
| 2 | How This Mom Makes $48K/Month With Claude | 339a5c3d |
| 3 | I Asked Claude To Make Me as Much Money as Possible | 68c04d3b |
| 4 | I Built My Entire Content Team Inside Claude (No Employees) | 9247e0c2 |
| 5 | If You Want to Get Rich With AI, Build This One Agent First | 620da512 |
| 6 | I built a complete "business operating system" using claude code | 4b2421dc |
| 7 | Learn 97% of Claude in Under 16 Minutes | 840cae84 |
| 8 | How I'd Use Claude AI to Build a Premium Personal Brand | 5f676964 |
| 9 | This AI Business Will Make You $1M (With Zero Employees) | 2ff3dc02 |
| 10 | How I Make $100k/month Using Claude Code (full guide) | c044e55e |

Entry files: `agents/nerd-agent/knowledge/entries/*.json`
Topic insight files: `context/nerd-insights/pinterest-marketing.md`, `context/nerd-insights/ai-tools.md`

## Output files — current state

**`context/nerd-insights/pinterest-summary.md`**
Consolidated Pinterest summary. Written in plain English, no generic intro. Covers: keyword
research SOP (PinClicks, annotations, Interest Explorer, Trends), two pinning recipes (3-pin
simple and 6-pin rotation), what gets a pin clicked vs. saved, the 6-cause traffic-stall
diagnostic, tool breakdowns, algorithm-change protocol. Includes concrete examples throughout.

**`context/nerd-insights/pinterest-action-checklist.md`**
Action checklist specifically for Switzertemplates. Written for Jane — assumes she's already
using Tailwind, posting ~10 pins/day, and using PinClicks. Focuses on 6 techniques from the
sources she's likely not doing yet.

**`context/nerd-insights/ai-tools.md`**
AI topic insight report covering 10 YouTube videos about Claude AI and making money with AI.
Two sections: "What We Learned" (strictly from sources) and "Implementation Suggestions for
Switzertemplates" (6 concrete proposals tied back to learnings). Key findings: token economics
reshaping knowledge work, 5 things people will still be paid for (conviction/judgment/taste/
commercial outcomes/system improvement), 82% of people haven't used AI yet, personal brand
as competitive moat, Draft Loop content system, complete business operating systems.

**`dashboard_data.json`** — `nerd_agent` section updated to reflect 20 sources, 2 topics.

## Dashboard tab — Nerd

The Nerd tab in `switzer_ai_dashboard.html` shows:

- **"Pinterest" card** (dark red, `var(--red-mid)`): 4 sections — keyword research,
  pin scheduling recipes, what gets clicked, traffic-stall diagnostic. "View action checklist"
  button in dark red. "→ full detail" links to anchors in `pinterest-summary.md`.

- **"AI" card** (dark teal, `var(--teal-mid)`): 4 sections — what AI is actually changing
  (token economics, 5 paid-for skills, 82% haven't used AI, personal brand moat), how people
  are making money with AI ($48K/month breakdown, $25M zero-employees example, agency→product
  conversion), what Claude can actually do (Draft Loop, business OS, Projects + system prompts),
  how this applies to Switzertemplates (4 specific angles). "→ full detail" links to anchors
  in `ai-tools.md`.

- **"Recent sources" table**: auto-populated from `dashboard_data.json`, shows last 10 sources.

## Topic classification — important note

When ingesting AI/Claude-related content, always pass `--topics ai-tools` explicitly:

```
python3 agents/nerd-agent/nerd_agent.py learn --url <url> --topics ai-tools
```

Or for batch:
```
python3 agents/nerd-agent/nerd_agent.py learn --batch urls.txt --topics ai-tools
```

Without this flag, Claude will fall back to the nearest allowed topic (usually
`business-strategy`), and the entry will need to be manually patched.

## Key code changes made

**`nerd_agent.py` — added `ai-tools` topic (this session):**
- Added `"ai-tools"` to `ALLOWED_TOPICS`
- Added `"ai-tools": "AI Tools & Making Money with AI"` to `TOPIC_LABELS`

**`nerd_agent.py` — extraction depth fixes (earlier session):**
- `MAX_TEXT_CHARS`: `15_000` → `100_000` — the old limit was truncating 41-88 minute
  video transcripts to ~20% of their content before Claude ever saw them
- `extract_insights` prompt: `key_points` raised from "3-8 points" to "8-20 points
  spanning the full runtime"; `summary` raised from "2-3 paragraphs" to "4-6 paragraphs
  preserving specific names, numbers, tools, and step-by-step detail"
- `max_tokens` in `extract_insights`: `2000` → `6000`

**`nerd_agent.py` — extraction fidelity fix (earlier session):**
- `business_ideas` and `actionable_steps` fields removed from extraction.
- Now: `extract_insights` is strictly faithful (topics + key_points + summary only).
  `write_topic_report` does the synthesis with clear labelling.

**PDF support removed (earlier session):**
- Workflow for PDFs: feed to ChatGPT, save text as `.txt`, then `learn --txt <path>`.

## Source files location

- `agents/nerd-agent/source-files/Tony-Hills-Newsletters.txt` — ingested as `3fca9459`
- `agents/nerd-agent/source-files/Youtube-links.pdf` — original Pinterest URL list (all ingested)
- `agents/nerd-agent/source-files/AI/AI-Youtube-videos.pdf` — original AI URL list (all ingested)
- `agents/nerd-agent/source-files/AI/AI-Youtube-videos-urls.txt` — extracted URLs (used for batch ingest)

## Next steps / what to work on next

1. **Feed more AI sources** when Jane has them:
   `python3 agents/nerd-agent/nerd_agent.py learn --url <url> --topics ai-tools`

2. **Feed more Pinterest sources** when Jane has them:
   `python3 agents/nerd-agent/nerd_agent.py learn --url <url> --topics pinterest-marketing`

3. **Add a new topic** when Jane starts a new research area (email marketing, SEO, etc.).
   Add the slug to `ALLOWED_TOPICS` and `TOPIC_LABELS` in `nerd_agent.py` first, then ingest.

4. **Regenerate the Pinterest summary** if more Pinterest sources are added:
   `python3 agents/nerd-agent/nerd_agent.py report --topic pinterest-marketing`
   Then update the Pinterest card in the dashboard manually with the new content.

5. **Regenerate the AI report** if more AI sources are added:
   `python3 agents/nerd-agent/nerd_agent.py report --topic ai-tools`
   Then update the AI card in the dashboard manually with the new content.
