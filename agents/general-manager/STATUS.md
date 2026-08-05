# General Manager — STATUS

Last updated: 2026-08-03 (Session 2 — first real end-to-end runs, found and fixed a
pipeline-breaking bug, then did a full rebuild of the Pinterest pin copy + design system
after Jane rejected the first real output on quality grounds. Read this before doing
anything else with the General Manager.)

---

## What this is

Unattended automation that runs Switzertemplates' blog/Pinterest traffic pipeline weekly,
so Jane stops being the bottleneck for keyword picking, writing, images, Wix drafts, pins,
and newsletters. Organizing goal (the "North Star"): **10,000 visitors/month** on
switzertemplates.com. Sales are the lagging indicator, not the tracked metric.

---

## The shape: two steps, not one

1. **`analyze_and_recommend.py`** (weekly, launchd) — pulls Search Console + GA4 + Wix
   Analytics + Pinterest performance, picks candidate keywords, opens a **GitHub issue**
   with the recommendation, updates the dashboard. Waits.
2. **`check_replies_and_execute.py`** (a few times/day, launchd) — checks the issue for a
   new comment. If there is one, `interpret_reply.py` (Claude) works out what Jane actually
   approved/rejected/requested from free text. Only on a clear decision does it write
   posts, push Wix drafts, generate pins, draft the newsletter, and email a summary, then
   update `dashboard_data.json`'s `general_manager` section with active links to everything
   produced (see "Dashboard report card" below).

Hard constraint, unchanged: **everything lands as a draft** (Wix draft posts, Tailwind
draft pins). Nothing ever publishes live automatically.

---

## SESSION 1 (2026-07-29) — original build

Full architecture designed and built: 12 design decisions, all files listed below created,
each piece unit-tested against real APIs individually, but no real end-to-end run yet and
nothing committed to git. Full decision log and file-by-file build notes were in the
previous version of this file — condensed here since Session 2 changed or superseded much
of it; see git history (`git log -- agents/general-manager/STATUS.md`) for the original
if the detail is ever needed.

Key decisions that still hold: drafts-only autonomy, OpenAI for images (scoped to blog +
pin generation only), GitHub Issues for the approval exchange, GA4/Search Console/Wix
Analytics as data sources, Wix cover-image upload stays manual (Jane's choice), pin visual
style should be reference-driven (this became the whole focus of Session 2).

---

## SESSION 2 (2026-08-01 to 2026-08-03) — real testing, then a full pin-quality rebuild

### Part A — first real end-to-end runs, found a pipeline-breaking bug

Ran the full pipeline for real (`blog_seo_agent.run()` → `publish_to_wix.publish()` →
`content_repurposer.repurpose()` → `pin_pipeline.generate_pins_for_keyword()`) on keyword
"pinterest seo". First two attempts hit transient Anthropic API errors (500, then 529
overloaded) — not code bugs, just retried.

Third attempt succeeded structurally but **every single OpenAI image call failed**: `lib/
openai_images.py` was passing `response_format="b64_json"` to `client.images.generate()`,
but `gpt-image-2` doesn't accept that parameter at all (it always returns b64_json by
default — unlike DALL-E 3). Fixed by removing the parameter. This meant the first real
post published with **zero images** and the inline `[DALLE: ...]` markers fell back to
visible placeholder text — the exact bug the whole image pipeline was built to prevent.
Also discovered creative-designer falls back to a **blank placeholder background** (no
real photo) when OpenAI generation fails, so the first batch of 5 Tailwind pin drafts from
this run are unusable.

Also discovered (not a bug, existing pre-Session-2 behavior): `blog_seo_agent.run()`'s own
git commit+push step does `git add` broadly, not scoped to just the new post — it swept up
**every uncommitted file in the repo** (including all of this session's General Manager
build) into one commit titled "add post: pinterest seo" and pushed it to `origin/main`.
Nothing was lost, just bundled under a misleading message. Worth knowing if a future commit
message looks broader than expected — check `git show --stat` before assuming something's
wrong.

**Fixed and re-verified**: re-ran the same keyword after the `response_format` fix — real
cover + inline images generated, Wix draft updated in place (not duplicated, using
`publish_to_wix.publish(slug, draft_id=...)`), real Tailwind pin drafts. Confirmed the fix
holds.

### Part B — dashboard: GM report card on Overview tab

Jane asked why the dashboard wasn't reflecting any of this — answer: the manual test
scripts called pipeline stages directly instead of going through
`check_replies_and_execute.py`'s `main()`, which is the only place that updates
`dashboard_data.json`. Fixed properly (not just patched for one run):

- `check_replies_and_execute.py`'s `_update_dashboard()` now builds a rich
  `general_manager.latest_run_posts[]` array per post — active links to the live blog post,
  a rendered post preview, the GitHub image folder, the Wix drafts list, the newsletter
  draft, the IG carousel, and Tailwind — computed from real URL patterns (`WIX_SITE_ID`,
  `GITHUB_REPO`, `BLOG_BASE_URL`), not guessed.
- Also mirrors successfully-repurposed posts into `repurposer.posts[]`, since
  `content_repurposer.py` never touched the dashboard itself either.
- `switzer_ai_dashboard.html`: new `renderGeneralManagerReport()` renders this as a card on
  the **Overview** tab (`#gm-report-card`), one row per post, color-coded link buttons
  (teal/amber/coral/choc backgrounds, not plain outlined buttons). Header format: "General
  Manager - run 3 Aug 2026" (`fmtGmDate()`). Removed the old Etsy/Blog/Pinterest/Pending/
  Posts-this-month stat-grid cards from Overview per Jane's request — also had to remove
  the now-dead `renderOverview()` function entirely (it was still being called from
  `togglePub()` too — a second call site that would have thrown "not defined" if missed).
- **Post preview link bug**: originally pointed at the GitHub *blob* URL (`github.com/.../
  blob/main/posts/{slug}.html`), which renders as syntax-highlighted source code, not a
  page. Fixed to use the GitHub Pages URL (`janeswiss.github.io/switzer-dashboard/posts/
  {slug}.html`) — this convention already existed in `blog_seo_agent.py` (the `"url"` field
  on every post entry uses exactly this pattern), I just hadn't reused it. Verified with
  `curl` that it returns 200 and actually renders.
- **Tailwind link**: `https://www.tailwindapp.com/dashboard/` (was a generic `/app` guess).

### Part C — content_repurposer's pins.json removed entirely

`content_repurposer.py` had its own, completely separate pin-copy generation (title +
description + URL, no images, never wired to anything) alongside the real pin pipeline —
two unrelated texts existed for the same post with no way to tell which was real. Jane
asked "why do the Tailwind pins say something different from the Pin Copy button" — this
was the answer. Removed `pins.json` generation from `content_repurposer.py` entirely
(`parse_pins()` deleted, `save_outputs()` simplified, `--all` mode's completion check
updated). It now only produces `email_hook.md` and `instagram_carousel.md`. Dashboard's
"Pin copy" button removed accordingly.

### Part D — full rebuild of Pinterest pin copy + design (the big one)

Jane reviewed real generated pins and rejected them hard: "rubbish", generic, forced
product pitches, near-identical designs, boring/illogical eyebrow+headline pairing, Title
Case where it shouldn't be. She then walked through her own reference material and iterated
live with Claude on example pin copy until it was right. Everything below reflects that.

**Reference material Jane provided** (read these before touching pin copy/design again):
- `agents/general-manager/switzertemplates-pins/` — 10 real pin design images spanning
  genuinely different structures: numbered icon grid, elegant outline-number list, colored
  block list, grouped checklist, bold text-stack, lifestyle/mockup lead-magnet. NOT one
  style — the range itself is the point.
- `agents/general-manager/switzertemplates-pins/titles-descriptions-CTAs/` — 4 screenshots,
  10 title/description/CTA examples in Jane's actual liked voice.

**Root causes found, in the order discovered:**
1. `_PM_SPLIT` forced 1 product pin even at PM=0 ("no product match"), so an unrelated
   keyword ("pinterest seo") got a forced, unconvincing pitch for Instagram templates.
   Fixed: PM=0 → 0 product pins.
2. All 5 variations under one topic shared identical `pin_items` (same list, same order,
   badge colors tied to item position not variation) → visually near-duplicate pins, a real
   Pinterest spam-detection risk, not just an aesthetic complaint.
3. Titles (`pin_headline`) were redefined this session to be 2-5 word labels for image
   legibility — but that discarded the "magazine cover line" curiosity-hook quality of
   Jane's actual approved style, which was 5-15 word full sentences.
4. CTA was a real, concrete bug: a pin's `seo_description` ended with "Grab it in my Etsy
   store!" while `destination_url` pointed at the blog — `PRODUCT_URLS` never actually maps
   anything to a real Etsy link, so that CTA (from the *old* approved-CTA list) was always
   going to be a lie.
5. `content_repurposer.py`'s separate (better-sounding) pin copy came from reading the
   *actual blog post*, not just the keyword — `pinterest-agent/copy_writer.py` never saw
   the post at all. It also used Opus; `copy_writer.py` used Sonnet.
6. Biggest one, found last: `pinterest-expert.md` had a "Style reference — exact tone and
   format to match" section that explicitly told Claude to check every variation against 3
   **old** benchmark examples (short titles, "no CTA" as ideal) — which directly
   contradicted the new rules written earlier the same session. Concrete examples pull
   harder on model output than prose rules, so this section was silently overriding
   everything above it. This is *the* answer to "why does it still sound generic after all
   these rule changes" — the rules were right, the literal pattern-matching material was
   still wrong.
7. Titles were using the tactic as the verb's grammatical subject ("Pinterest SEO
   built/turned/beats...") — a classic AI-writing tell. A tactic can't act; a person acts,
   or the tactic is a noun phrase being described ("the strategy that...").
8. A pin used a Pinterest-vs-Instagram comparison — already permanently banned in
   `blog_seo_agent.py` ("overused across previous posts") for blog post openers, but never
   ported to pin copy.
9. `_enforce_case()` (the programmatic sentence-case/ALL-CAPS backstop) didn't special-case
   the standalone pronoun "I", and had no path for real proper nouns beyond a fixed short
   list — "while i sleep" shipped in one rendered pin before this was caught.
10. Image prompts had "sparkle/leaf/botanical decorative accents" and hairline dividers
    baked into every layout template — Jane identified these as gpt-image-2's default
    "elegant" filler, not anything in her real reference pins, and exactly what makes an
    image read as AI-generated instead of custom-designed. Also removed the `tagline`
    element entirely — nothing renders below the bottom watermark bar now.

**Current architecture (copy first, design derived from copy — Jane's explicit instruction):**
1. `pin_pipeline.py` reads the real post text (`_post_excerpt()`, reusing
   `content_repurposer.extract_post_content()`) and passes it into `copy_writer.generate()`.
2. `copy_writer.py` (now Opus, was Sonnet) writes `seo_title` FIRST for each of 5
   variations — full sentence, 8-15 words, outcome-led, one of 5 rotating angles
   (benefit/problem/result/comparison/transformation-led, comparison-led restricted to
   comparing two things *within* the topic, never a platform). `cta` is now its own field,
   names the destination directly, rotates.
3. `eyebrow` + `headline` are DERIVED from `seo_title` — a visual split that must
   reconstruct the title as one sentence when read together. `eyebrow` is genuinely left
   empty on some variations (real pins mix eyebrow+headline with headline-only).
4. `pin_items` (5-6 real facts, grounded in the post) live once per topic; each variation
   picks its own subset/order via `item_order` so no two pins show an identical list.
5. `_enforce_case()` guarantees sentence-case/ALL-CAPS programmatically (not just prompted)
   — handles "I", a short proper-noun list (`_PROPER_NOUNS`: pinterest, etsy, instagram,
   canva, wix, google, tiktok, facebook, shopify, flodesk, tailwind, jane,
   switzertemplates) and a separate acronym list rendered full-uppercase (`_ACRONYMS`: seo,
   diy, url, cta, faq, ai, pdf, ugc, roi).
6. `infographic_pin_prompt.py` has **3 structurally distinct layout templates** —
   `icon_grid` (numbered circle badges + icons, 2-column), `outline_list` (single column,
   thin outline numerals, elegant serif, no color fill), `colored_block` (flat colored
   rectangles, numbered text only, no icons) — rotated by variation letter in
   `image_generator.py` (`LAYOUTS[letter_index % 3]`), plus a rotating badge-color offset.
   No decoration, no dividers, no frames, nothing below the bottom bar.
7. `pinterest-expert.md`'s "Style reference" section now contains real few-shot material:
   Jane's actual liked examples verbatim, plus the specific pin copy she personally
   reviewed and approved line-by-line in this session (not paraphrased). This is the
   section Claude is told to literally pattern-match against.

**Verified against 3 full real runs** (each showed Jane the actual rendered images before
being called done): final run showed correct grammar (no personification), no platform
comparison, no stray decoration, genuine layout/color variety across all 5 pins, titles
matching the reference voice (e.g. "Domain quality beats keyword stuffing", "From
guesswork to a system that ranks").

**Files touched in Part D:**
```
context/pinterest-expert.md                    Heavily rewritten: Title principles, CTA
                                                 rules, "Pin design text is DERIVED from
                                                 copy" section (replaces old "pin_headline
                                                 vs seo_title"), Design principles
                                                 (infographic-era, replaces old photo-brief
                                                 era text), Style reference (real few-shot
                                                 examples), quality checks, "never do" list,
                                                 PM=0 split note. All internally consistent
                                                 now — check this file first before writing
                                                 pin copy rules by hand elsewhere.
skills/pinterest-agent/copy_writer.py           Model -> opus. New fields: title_angle,
                                                 headline, cta, item_order. eyebrow can be
                                                 empty. _enforce_case() + _PROPER_NOUNS +
                                                 _ACRONYMS added. _PM_SPLIT[0] = (0,5).
skills/creative-designer/infographic_pin_prompt.py   NEW (built then revised). 3 layout
                                                 template builders + _header_block/
                                                 _footer_block. No tagline, no decoration,
                                                 no dividers.
skills/creative-designer/image_generator.py     Rewritten: single OpenAI call per pin (no
                                                 Pillow compositing), layout + color_offset
                                                 chosen from variation letter.
skills/creative-designer/main.py                preloaded_copy mapping updated for new
                                                 field names (topics-JSON -> copy_data).
agents/general-manager/pin_pipeline.py          Added _post_excerpt() for real-post
                                                 grounding.
agents/content-repurposer/content_repurposer.py pins.json generation removed entirely.
```

---

## What's confirmed working (tested live, Session 2)

- Full pipeline for one real keyword, twice — first run caught the `response_format` bug,
  second run confirmed the fix (real images, real Wix draft update, real Tailwind pins).
- Dashboard Overview tab GM report card — real links, verified the GitHub Pages preview URL
  actually resolves (curl 200).
- Pin copy + design rebuild — 3 full runs, final one confirmed correct on every axis Jane
  flagged (grammar, comparison ban, decoration, layout variety, color variety, case).

## What's NOT yet done

1. **Old broken Tailwind drafts need manual cleanup** — at least 2 batches of pins from
   before the fixes (blank backgrounds from the response_format bug, then a
   decent-but-generic batch from before the copy rebuild) are still sitting in Jane's
   Tailwind queue. No safe API-verified way to delete them found — flagged for her to
   delete by hand.
2. **`agents/content-repurposer/switzertemplates-pins/` → `agents/general-manager/
   switzertemplates-pins/` folder move is uncommitted** — shows as deleted+untracked in
   `git status`. Jane moved it on disk; I haven't committed that change or been asked to.
3. **The outer GM loop (`analyze_and_recommend.py` → GitHub issue → `check_replies_and_
   execute.py`) hasn't been re-tested since the Part D pin rebuild** — the pieces should
   still compose correctly (same `pin_pipeline.py` call), but only the inner pin-generation
   step has been re-verified directly, not the full weekly-report → approval → execution
   loop end to end.
4. **launchd activation** — still not installed to `~/Library/LaunchAgents`. Explicitly a
   "do this last" step.
5. **`POSTS_PER_WEEK`** — still defaults to 2, never explicitly confirmed with Jane.
6. **CLAUDE.md updates** — Agent Directory / Skills Directory still don't mention
   general-manager. Documentation debt, not functional debt.
7. **`context/top-performing-pins/`** (the old, now-superseded reference folder path from
   Session 1's decision 10) is empty and `analyze_reference_pins.py`/`pin-visual-style.md`
   were never actually used — superseded by the real reference folders under
   `agents/general-manager/switzertemplates-pins/` in Part D. Worth deciding whether to
   delete the dead `analyze_reference_pins.py` script and its `context/pin-visual-style.md`
   loading code in `copy_writer.py`, or leave it as inert dead code.
8. Backfilling the 44 already-published posts with leaked `[DALLE: ...]` text — still
   optional, still not done.

## Immediate next step

Jane's choice — options on the table: (a) re-run the full outer GM loop (recommend → GitHub
issue → approve → execute) end to end now that pin quality is fixed, to confirm the whole
system works together, not just the inner pin step; (b) clean up old Tailwind drafts and
review the current pin batch manually first; (c) decide `POSTS_PER_WEEK` and activate
launchd. Nothing should be assumed — ask before proceeding on any of these, per how this
session has gone (Jane reviews and corrects before anything is declared done).
