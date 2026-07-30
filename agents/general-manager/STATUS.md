# General Manager — STATUS

Last updated: 2026-07-29 (full build session — architecture designed, all code written and
individually tested against real APIs, all credentials now in place, about to run first
real end-to-end test before activating the weekly schedule)

Read this before doing anything else with the General Manager. It's the memory of a long
design + build session — the reasoning behind decisions matters as much as the decisions
themselves, so don't just skim the file list.

---

## What this is

Unattended automation that runs Switzertemplates' blog/Pinterest traffic pipeline weekly,
so Jane stops being the bottleneck for keyword picking, writing, images, Wix drafts, pins,
and newsletters. Organizing goal (the "North Star"): **10,000 visitors/month** on
switzertemplates.com, as fast as realistically possible. Sales are treated as the lagging
indicator of traffic, not tracked as the primary metric — see decision 8.

It replaced an aspirational `growth-strategist` role that was documented in CLAUDE.md's
Agent Directory table but never built (zero code, confirmed via git log at design time).
CLAUDE.md's Agent Directory / Skills Directory have **not yet been updated** to reflect
this — that's a remaining doc task, not urgent.

---

## The shape: two steps, not one

1. **`analyze_and_recommend.py`** (weekly, launchd) — pulls Search Console + GA4 + Wix
   Analytics + Pinterest performance, picks candidate keywords (trending first, falling
   back to the static Priority Tier order), opens a **GitHub issue** with the full
   recommendation, updates the dashboard. Writes nothing else. Waits.
2. **`check_replies_and_execute.py`** (a few times/day, launchd) — checks the issue for a
   new comment from Jane. If there is one, hands it + the original candidates to Claude
   (`interpret_reply.py`) to work out what she actually approved/rejected/requested —
   **free text, not a fixed format**. Only on a clear decision does it write posts, push
   Wix drafts, generate pins, draft the newsletter, and email a completion summary.

Why two scripts instead of one that "pauses": Python doesn't reliably wait across days for
external input. They hand off through `logs/pending_recommendation.json`.

Why GitHub Issues instead of email for the approval exchange (this was iterated on — see
below): the dashboard (`switzer_ai_dashboard.html`) is a **static page with no backend** —
it can display state but can't receive input. GitHub Issues needed zero new infrastructure
(reuses `GITHUB_TOKEN`, already confirmed to have `issues: write` scope), and comments
don't have the threading-header fragility a raw email-reply-parsing design would have had.

---

## The 12 design decisions (chronological — later ones refine earlier ones)

1. **Autonomy**: everything lands as a draft (Wix draft posts, Tailwind draft pins).
   Nothing ever publishes live automatically. Hard constraint.
2. **OpenAI, scoped**: swap Gemini → OpenAI for blog images AND Pinterest pin backgrounds
   only. `skills/stock-photo-generator/` and pinterest-agent's own 2 Gemini call sites are
   untouched, out of scope.
3. **Pin generation**: fix/stabilize the existing `skills/creative-designer/` pipeline
   rather than routing through Canva (Jane explicitly rejected Canva).
4. **Report scope**: traffic pipeline only. Etsy, email broadcasts, leads = out of scope.
5. **Real Search Console**, not a SERP-scraping proxy — trustworthiness mattered more than
   avoiding setup.
6. **GA4** for session/conversion data per post (turned out not to be actually connected —
   see "GA4 was not actually set up" below).
7. **Content refresh**: close-to-page-1 posts/pages get flagged, never auto-rewritten. A
   real refresh pipeline is an explicit later phase.
8. **North Star**: 10,000 visitors/month is the one number everything serves. SEO has real
   lag (weeks-months) — don't over-read early weekly numbers, especially the first few.
9. **Image delivery to Wix is manual, by choice** — no Wix Media Manager API integration.
   3 cover-image candidates + 4-5 real inline section images per post go into a per-post
   GitHub folder; Jane compresses/uploads into the Wix draft herself. Deliberate trade of
   automation for control over the one output she cares most about.
10. **Pin visual style is reference-driven** — Jane's own proven-performing pins shape
    future pin-generation prompts, not generic brand-voice instructions alone.
11. **Two-step, GitHub-Issue approval** (final form of the recommend/approve exchange,
    superseding an earlier email-based design).
12. **Wix's own sales data, cheaply** — `TOTAL_SALES`/`TOTAL_ORDERS` alongside GA4, reusing
    `WIX_API_KEY` already required elsewhere. Fills the gap if GA4 ecommerce tracking isn't
    configured (it wasn't, until this session).

---

## File map

```
lib/
  openai_images.py          Shared: generate_image_bytes(prompt, aspect_ratio, quality,
                             output_format) -> (jpeg_bytes, cost_estimate). Model: gpt-image-2.
                             Compresses (Pillow, long-edge cap 1600px, JPEG q=82) before
                             returning. 1.5s pacing delay between calls (bursts of 15-20+
                             images/run). Used by blog_seo_agent.py AND creative-designer's
                             image_generator.py.
  gmail_client.py            Shared: send_email(to, subject, body) — send-only, extracted
                             from lead-gen-agent's proven email_sender.py. No IMAP/receiving
                             (that job moved to GitHub Issues).

agents/blog-seo-agent/
  blog_seo_agent.py          MODIFIED: generate_images_from_prompts() now makes 3 cover
                             images (not 5 — dropped the old dedicated 9:16 Pinterest
                             variant, pins come from pin_pipeline.py now), saved to
                             posts/images/{slug}/cover-N.jpg. NEW generate_inline_images()
                             finds [DALLE: ...] markers Claude writes inline (previously
                             NEVER rendered — just turned into visible text boxes, a real
                             bug), generates real images for each via lib/openai_images,
                             saves to posts/images/{slug}/inline-N.jpg, splices real <img>
                             tags into the post. run() now returns a dict
                             {filename, slug, keyword, image_cost, push_ok} instead of
                             nothing (was needed for the orchestrator + cost tracking).
  publish_to_wix.py          MODIFIED: find_html_file() now checks POSTS_DIR before the
                             legacy OUTPUT_DIR (was backwards, served stale copies for 6
                             slugs). extract_post_content() now strips cover images
                             entirely (Jane sets the real Wix cover manually) and replaces
                             each inline image with a clean placeholder paragraph naming
                             the exact file — tested against synthetic HTML, confirmed
                             working correctly (mutation-during-iteration bug caught and
                             fixed: cover images share one parent div, had to decompose
                             each unique parent once, not per-<img> mid-loop).

skills/creative-designer/
  image_generator.py         MODIFIED: _generate_background_gemini() -> renamed
                             _generate_background_openai(), now calls
                             lib/openai_images.generate_image_bytes(). Also renamed
                             _build_gemini_prompt -> _build_image_prompt and the
                             "gemini_instruction" dict key -> "image_instruction" for
                             consistency (pure cosmetic, no behavior change).
  main.py                    MODIFIED: new --auto-approve flag, guards BOTH
                             browser_approval() call sites (main path AND the
                             --review-session resume path — there are two, easy to miss
                             the second one). Skips the blocking browser review entirely;
                             Tailwind submission is unchanged (still always draft-only).
  requirements.txt            google-genai -> openai

skills/pinterest-agent/
  copy_writer.py              MODIFIED: destination_url now gets
                             ?utm_source=pinterest&utm_medium=social&utm_campaign={slugified
                             keyword} applied in Python (_add_utm()), AFTER Claude
                             generates or the PRODUCT_URLS fallback fires — guaranteed,
                             not left to the model. Also now loads
                             context/pin-visual-style.md into the system prompt (new
                             "PROVEN VISUAL STYLE" section) — degrades gracefully with a
                             placeholder message if that file doesn't exist yet.
  analyze_reference_pins.py   NEW. Standalone, NOT part of the weekly loop — run once
                             after Jane adds pins to context/top-performing-pins/, and
                             again whenever she adds more. Uses Claude vision (one call
                             per image + one synthesis call) to write
                             context/pin-visual-style.md. Tested: handles empty-folder
                             case gracefully (prints a message, does nothing).

agents/blog-seo-agent's CTA MAPPING (inside build_prompt(), the big f-string) — all 5
mapped URLs now have &utm_source=blog&utm_medium=content&utm_campaign={slug} appended
inline via f-string interpolation. Deliberately NOT applied to the separate crosslinking
section (internal blog-to-blog links) — UTM params on internal links is a known GA4
pitfall (corrupts session attribution).

agents/general-manager/                          ALL NEW THIS SESSION
  analyze_and_recommend.py   Step 1 entry point. Reads/writes logs/pending_recommendation.json.
                             Skips sending a new recommendation if one is already
                             unresolved (no pileup). pick_candidates() = trending first,
                             then _static_priority_candidates() (a small local
                             reimplementation of blog_seo_agent.load_next_keyword()'s
                             tier-sort logic, generalized to return N rows not just 1 —
                             deliberately NOT imported from blog_seo_agent.py, kept as a
                             small local duplicate per this codebase's "don't over-abstract"
                             norm).
  check_replies_and_execute.py   Step 2 entry point. Lock file (logs/execution.lock) guards
                             against overlapping runs. _produce_one_post() runs the full
                             chain for one keyword with per-stage try/except (one failure
                             doesn't stop the others). Loud osascript notification
                             specifically if GitHub is unreachable (the one failure mode
                             that would otherwise break the loop invisibly).
  interpret_reply.py          One Claude call (claude-opus-4-5 — higher-stakes than a
                             summary, chose accuracy over cost). Deliberately conservative:
                             ambiguous replies ("let me think about it") return empty
                             approved/new_requests so the caller leaves it pending rather
                             than guessing. TESTED LIVE with 3 real scenarios (mixed
                             approve/reject/new-request, plain "go ahead", genuine
                             ambiguity) — all 3 correct.
  report_writer.py            write_recommendation_issue() and write_completion_email(),
                             both one Claude call (claude-sonnet-4-6) with a plain-template
                             fallback if the call fails. TESTED LIVE — output was
                             genuinely good. Caught and fixed 2 real accuracy bugs during
                             testing: (1) the model was describing the photo-folder link
                             instead of including the actual URL — fixed by computing the
                             URL in Python and forcing verbatim inclusion in the prompt;
                             (2) it said "newsletter sent" / pins "published" when
                             everything is actually just a draft — fixed with explicit
                             prompt language ("nothing sends automatically, never say
                             sent").
  github_issues_client.py     create_issue / fetch_new_comments / close_issue against
                             api.github.com, repo hardcoded as JaneSwiss/switzer-dashboard
                             (confirmed via `git remote -v`). TESTED LIVE end-to-end
                             (created issue #1, fetched comments, closed it) — confirms
                             GITHUB_TOKEN already has issues:write, no extra setup needed.
  search_console_client.py    fetch_rankings() — ONE searchanalytics().query() call per
                             run (dimensions=[query,page], 28 days, rowLimit 25000),
                             everything else (rankings/new-opportunities/close-to-page-1)
                             computed locally from that one pull. get_trending_unwritten_
                             keywords() compares week-over-week via
                             logs/search_console_history.json (30% growth threshold + 15
                             impressions floor, BOTH ARE GUESSES — need real tuning once a
                             few weeks of data exist). TESTED LIVE — real data: 9 tracked
                             rankings, 18 new opportunities, 15 close-to-page-1 items.
                             GSC_SITE_URL=https://www.switzertemplates.com/ works (didn't
                             need the sc-domain: alternative).
  ga4_client.py               fetch_north_star_pace() (total sessions, 30-day vs prior
                             30-day, named DateRanges) and fetch_sessions_by_campaign()
                             (per-UTM-campaign, joins to slugs). TESTED LIVE — connects
                             fine, returns all zeros because the GA4 property was created
                             minutes before testing (see below) — expected, not a bug.
  wix_analytics_client.py     fetch_sales_and_sessions() — Wix's native Analytics Data API
                             (GET /analytics/v2/site-analytics/data, verified against
                             Wix's actual current REST docs, not guessed). 62-day retention
                             cap enforced (Wix's own limit). TESTED LIVE — real data: 676
                             sessions, $188.35 sales, 5 orders, 558 unique visitors/28 days.
                             Confirms WIX_API_KEY already has the READ-SITE-ANALYTICS scope.
  pin_pipeline.py             generate_pins_for_keyword() — builds one-keyword pin copy
                             (reuses topic_selector._score_product_match() + pinterest-
                             agent's copy_writer.generate()), writes
                             data/pinterest-agent/gm-topics-{slug}.json, then invokes
                             creative-designer/main.py via SUBPROCESS (not in-process
                             import) — deliberate, because skills/creative-designer/
                             copy_writer.py and skills/pinterest-agent/copy_writer.py are
                             two different files with the identical bare module name; both
                             on sys.path in one process risks a silent wrong-module import.
  logs/                       errors.json, search_console_history.json,
                             pending_recommendation.json, execution.lock (all created at
                             runtime, not pre-populated)
  launchd/                    run_weekly.sh + check_replies.sh (chmod +x'd) and both
                             .plist files (plutil-validated). NOT YET INSTALLED to
                             ~/Library/LaunchAgents — the in-repo copies are reference
                             only until activated on purpose.

switzer_ai_dashboard.html    MODIFIED: new renderGeneralManager() — reads
                             DATA.general_manager.awaiting_reply/candidates/issue_url,
                             renders a "waiting on you" card (reusing the existing
                             .csv-banner CSS, warning variant) at the top of the Overview
                             tab, linking to the GitHub issue. Hooked into the existing
                             load sequence. Renders nothing (empty string) when nothing's
                             pending.

context/
  top-performing-pins/        NEW empty folder — Jane's to populate whenever, not done yet
  pin-visual-style.md          Does not exist yet (output of analyze_reference_pins.py,
                             which needs the folder above populated first)

.gitignore                   Added data/pinterest-agent/gm-topics-*.json (ephemeral
                             per-run handoff files, not meaningful to keep)
```

---

## .env additions this session

```
OPENAI_API_KEY=sk-proj-...                                            (confirmed working)
GSC_SERVICE_ACCOUNT_JSON=/Users/janeair/.config/switzertemplates/gsc-service-account.json
GSC_SITE_URL=https://www.switzertemplates.com/                        (confirmed correct format)
GA4_PROPERTY_ID=547507995                                             (confirmed correct)
```
Service account: `switzertemplates-gm@switzertemplates.iam.gserviceaccount.com`, granted
Restricted access in Search Console and Viewer in GA4 Property Access Management. The
downloaded key file is also still sitting in `~/Downloads/switzertemplates-aae7c57210b7.json`
(untouched, copy safety rule — never delete/move Jane's files, only copy) — the copy at
`~/.config/switzertemplates/` is the one actually used.

Not yet added: `POSTS_PER_WEEK` (defaults to 2 in code if unset — that default was never
explicitly confirmed with Jane, worth revisiting once she's seen a real run).

---

## Important discovery: GA4 was not actually connected

CLAUDE.md / earlier planning assumed GA4 was already live on switzertemplates.com (it
wasn't — Jane found no property at all in analytics.google.com). Set up fresh this session:
new GA4 property, Web data stream for switzertemplates.com, Measurement ID pasted into
Wix's Marketing Integrations. **This means there's zero historical GA4 data** — the North
Star "trend vs prior period" comparison will show nothing meaningful for a while (first
month or so). Not a bug if the first several weekly reports show flat/zero trend — that's
the real state, not broken code.

---

## What's confirmed working (tested live against real APIs this session)

- OpenAI image generation — key added, NOT yet exercised end-to-end (next step)
- Search Console — real rankings/opportunities/close-to-page-1 data
- GA4 — connects and parses correctly, zero data because brand new (expected)
- Wix Analytics — real sales/sessions/orders data
- GitHub Issues — full create/comment-fetch/close cycle
- Gmail send — real test email delivered
- interpret_reply.py — 3 real scenarios, all correctly interpreted
- report_writer.py — both functions, real Claude output, 2 accuracy bugs found and fixed
- publish_to_wix.py's new image-stripping logic — synthetic HTML test, correct output
- Dashboard card — structurally verified (BeautifulSoup parse check), not visually
  screenshot-tested in an actual browser

## What's NOT yet done

1. **A full real end-to-end run** — one real keyword through write → images → Wix draft →
   pins → Tailwind → newsletter → completion email. This is the very next step (in
   progress as of this STATUS.md being written).
2. **launchd activation** — files exist and validate, `launchctl load` never run. Explicit
   last step, after the end-to-end test looks right.
3. **CLAUDE.md updates** — Agent Directory row for general-manager (replacing the
   never-built growth-strategist row), new Skills Directory block, Dashboard Update
   Protocol subsection. Documentation debt, not functional debt.
4. **Backfilling the 44 already-published posts** that have literal `[DALLE: ...]` text
   leaked into their HTML (root cause fixed for all NEW posts; old ones need either a
   stopgap regex strip or full backfill — optional, not required).
5. **`context/top-performing-pins/`** is empty — Jane hasn't dropped reference pins in yet.
   `analyze_reference_pins.py` degrades gracefully without it, but the pin-style feature
   (decision 10) isn't actually active until she does.
6. Nothing has been committed to git this session. Everything above is sitting as local
   file changes. (Confirmed via `git log` that no auto-commits happened — only the
   orchestrator scripts' own internal git operations would ever do that, and neither has
   run for real yet.)

## Immediate next step

Run one real post through `check_replies_and_execute.py`'s `_produce_one_post()` path (or
equivalent manual invocation) for a real masterlist keyword, with Jane watching the
results — first genuine test of the OpenAI image pipeline, the Wix placeholder logic
against a real generated post, and pin generation end to end. Then decide on
`POSTS_PER_WEEK`, then activate launchd.
