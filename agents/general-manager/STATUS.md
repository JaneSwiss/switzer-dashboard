# General Manager — STATUS

Last updated: 2026-08-05 (Session 3 — Pinterest pin generation rebuilt a second time, this
time as a clean, dedicated module modeled on Blog SEO Agent's proven pattern, replacing
`skills/pinterest-agent/copy_writer.py` in the GM flow entirely. Also fixed a real
audience-bias bug and closed a dashboard/Wix-sync gap. Read this before doing anything else
with the General Manager.)

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
   produced (see "Dashboard report card" in Session 2 notes below).

Hard constraint, unchanged: **everything lands as a draft** (Wix draft posts, Tailwind
draft pins). Nothing ever publishes live automatically.

**Important, session 3 finding, worth repeating every session**: manually testing pipeline
pieces directly (calling `pin_generator.py`, `content_repurposer.py`, a backfill script,
etc. straight from the shell instead of through `check_replies_and_execute.py`) produces
real, correct output — but skips the *only* code path that pushes to GitHub and writes
`dashboard_data.json`. This has now bitten twice (Session 2 Part B, and again in Session 3).
**After any manual/direct test run, remember to commit+push and update the dashboard by
hand**, or better, just re-run through the real orchestrator once things are confirmed
working.

---

## SESSION 1 (2026-07-29) — original build

Full architecture designed and built: 12 design decisions, all files listed below created,
each piece unit-tested against real APIs individually, but no real end-to-end run yet and
nothing committed to git. Full decision log and file-by-file build notes were in the
previous version of this file — condensed here since later sessions changed or superseded
much of it; see git history (`git log -- agents/general-manager/STATUS.md`) for the
original if the detail is ever needed.

Key decisions that still hold: drafts-only autonomy, OpenAI for images (scoped to blog +
pin generation only), GitHub Issues for the approval exchange, GA4/Search Console/Wix
Analytics as data sources, Wix cover-image upload stays manual (Jane's choice), pin visual
style should be reference-driven (became the whole focus of Sessions 2 and 3).

---

## SESSION 2 (2026-08-01 to 2026-08-03) — real testing, then a full pin-quality rebuild

**Historical note (Session 3): the pin copy/design architecture built in this session's
Part D — `skills/pinterest-agent/copy_writer.py` + `skills/creative-designer/
infographic_pin_prompt.py` + `context/pinterest-expert.md` — is no longer what GM uses.**
Session 3 replaced it entirely with a new, dedicated module (see below) after Jane rejected
this architecture's real output a second time and asked for a clean rebuild instead of
another patch. The detail below is kept for history/context — `copy_writer.py` and
`pinterest-expert.md` are untouched, unused by GM, and Jane's call on what to do with them.

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

**Fixed and re-verified**: re-ran the same keyword after the `response_format` fix — real
cover + inline images generated, Wix draft updated in place (not duplicated, using
`publish_to_wix.publish(slug, draft_id=...)`), real Tailwind pin drafts. Confirmed the fix
holds.

### Part B — dashboard: GM report card on Overview tab

Jane asked why the dashboard wasn't reflecting any of this — root cause: manual test
scripts called pipeline stages directly instead of going through
`check_replies_and_execute.py`'s `main()`, the only place that updates
`dashboard_data.json`. Fixed: `_update_dashboard()` now builds a rich
`general_manager.latest_run_posts[]` array per post — active links to the live blog post, a
rendered post preview (GitHub Pages URL, not the raw GitHub blob URL, which renders as
source code), the GitHub image folder, Wix drafts, newsletter, IG carousel, Tailwind.
`switzer_ai_dashboard.html` renders this as a card on the Overview tab.

### Part C — content_repurposer's pins.json removed entirely

`content_repurposer.py` had its own, disconnected pin-copy generation (never wired to
anything real) running alongside the actual pin pipeline — two different texts existed for
the same post with no way to tell which was real. Removed entirely; `content_repurposer.py`
now only produces `email_hook.md` and `instagram_carousel.md`.

### Part D — first full rebuild of Pinterest pin copy + design (superseded in Session 3)

Root causes found and fixed at the time (see git history for full detail): forced product
pitches on 0-product-match keywords, identical `pin_items` across all 5 variations (a real
Pinterest spam-detection risk), titles that discarded Jane's real "magazine cover line"
style, a CTA promising an Etsy link that didn't exist, a **stale few-shot example section in
`pinterest-expert.md`** that silently overrode every rule change made earlier the same
session (concrete examples beat prose rules — this was the single biggest lesson of Session
2 and it recurred in Session 3 in a different form), tactic-as-agent personification
("Pinterest SEO built..."), an un-ported Instagram-comparison ban, decorative sparkle/leaf
filler baked into every layout template. Resulted in 3 fixed layout templates
(`icon_grid`/`outline_list`/`colored_block`) rotated by variation letter, `_enforce_case()`
as a programmatic case backstop, copy-first/design-derived architecture.

**Why this got replaced anyway**: even after all these fixes, Jane tested the same idea
directly against ChatGPT and got visibly better results than the pipeline produced. Root
cause (found in Session 3, see below): the prompt had drifted right back into being
over-specified (long mechanical style descriptions, hedged/optional-sounding content
instructions) — the same failure mode as the stale-examples bug, recurring in new form.
That, plus a genuine root-cause discovery that pin copy was being generated from a
**severely truncated post excerpt**, is what triggered the Session 3 rebuild.

---

## SESSION 3 (2026-08-05) — pin generation rebuilt again, this time as a clean, dedicated module

### Part A — reference-driven image prompts, iterated live (now superseded, see Part B)

Before the full rebuild, spent significant time getting `skills/creative-designer/
infographic_pin_prompt.py` to generate genuinely varied, non-generic pins by picking ONE
real reference pin per generation (from `context/pin-reference-styles.json`, still live and
reused in Part B) and giving OpenAI real creative freedom instead of a mechanical spec.
Iterated through several real bugs, each found by generating and inspecting actual images:
- Overly-long, mechanical `STYLE REFERENCE` text and hedged "you don't need to use all of
  them" content language caused the model to render near-blank pins (a single line of
  headline text on an empty gradient) — fixed by matching a working prompt Jane tested
  directly against ChatGPT: terse structural reference line, unhedged content, a bare
  closing directive ("Create a pin to illustrate this topic/information").
- All pins leaned the same 2-3 colors — added `_PALETTE_VARIANTS`, a rotating "lead accent
  color" line layered on the brand palette.
- Jane asked for pin **type** variety too, not just layout — added a `pin_type` field
  ("infographic" vs "photo") to `pin-reference-styles.json`, split 3-infographic/2-photo per
  topic in `image_generator.py`. The 2 photo references
  (`pin-design-example-photo.jpg`/`photo2.jpg`) are real files Jane renamed herself in
  `agents/general-manager/switzertemplates-pins/` to flag them for this purpose.
- Fixed a real cross-topic bug: reference/palette rotation was keyed only to variation
  letter (a-e), so every topic on the account picked the exact same first-5 references in
  the same order — added a topic-keyword hash so different posts draw from different points
  in the pool too.

This work is still in the codebase (`skills/creative-designer/infographic_pin_prompt.py`,
`image_generator.py`, `analyze_pin_references.py`) but **is no longer what GM calls** — see
Part B. It would still run if `skills/creative-designer/main.py` were invoked directly/
manually, using `skills/pinterest-agent/copy_writer.py` for copy. Worth knowing this fork
exists: two different copy-writing systems now live in the repo, only one is used by GM.

### Part B — the real rebuild: `agents/blog-seo-agent/pinterest-pins/`

Jane reviewed real pins from Part A's system and rejected them again — bad titles, cramped/
distorted icons, duplicated content on two-column layouts. Working through *why*, live,
surfaced the actual root cause: **`pin_pipeline.py` was grounding pin copy in a 4,000-
character excerpt of the real blog post** (`content_repurposer.extract_post_content`,
truncated). Confirmed directly: `shopify-vs-wix-for-ecommerce` is 2,928 words / 8 real
sections; the 4,000-char cutoff landed 22% through the post, **before either of its two
comparison sections** ("WHERE WIX WINS" / "WHERE SHOPIFY WINS"). Pin copy had been writing
blind to most of what its own source post actually said — this, not prompt phrasing, is why
items read as disconnected, invented filler.

Jane's response: stop patching `copy_writer.py`/`pinterest-expert.md` (a system that had
now needed 3 separate rewrites in two sessions, each new fix fighting the last one) and
instead build pin generation fresh, mirroring `blog_seo_agent.py`'s proven pattern —
hardcoded rules instead of a living context doc that keeps drifting, one well-grounded
Claude call, real content, then a validation pass. New, self-contained module:

```
agents/blog-seo-agent/pinterest-pins/
  post_sections.py    Extracts the REAL, FULL post structure (every real <h3> section +
                       its actual body text, no length cap) — replaces the 4000-char
                       excerpt bug above at the root.
  pin_writer.py        Hardcoded rules (not a living doc) + one Claude call per post,
                       grounded in post_sections output, producing 5 variations. Includes
                       real transcribed examples from Jane's own reference images
                       (agents/general-manager/switzertemplates-pins/titles-descriptions-
                       CTAs/ — these had never actually been read into text before this
                       session, only sitting as unread images). Validation pass mirrors
                       blog_seo_agent's check_banned_words: personification-pattern regex,
                       near-duplicate-item check across variations, deterministic case
                       enforcement (_enforce_case) — with one Claude revision retry if
                       issues are found, same pattern as the banned-word retry.
  pin_image_prompt.py  Builds the OpenAI prompt from validated copy only (never invents
                       copy). Reuses context/pin-reference-styles.json directly (shared,
                       still-live file, not part of what got replaced). 4 fixes baked in,
                       all found from real bad output: (1) only the short, purpose-written
                       image_headline/image_eyebrow are quoted exactly — pin_items are
                       informational so there's room to fit them; (2) explicit permission to
                       drop items / keep descriptions brief instead of cramming (this is what
                       was distorting icons); (3) icons only where the reference style
                       actually uses them; (4) never duplicate a point to fake a two-sided
                       layout — this fixed the duplicate-content bug at its source, since
                       genuinely two-sided posts (like the Wix/Shopify one) now produce
                       genuinely paired items instead of forcing single facts into both
                       columns.
  pin_generator.py     Orchestrator, mirrors blog_seo_agent.run(): write → validate →
                       generate 5 images (OpenAI) → upload (Cloudinary, reused from
                       creative-designer) → submit to Tailwind (reused tailwind_client.py).
                       CLI: `python3 pin_generator.py <slug> "<keyword>"`.
```

**Key design choice**: `image_headline` is a separate, deliberately SHORT field (a few
words, close to the actual keyword — e.g. "Shopify vs Wix for ecommerce - an honest
comparison") written by the copywriter itself, not invented by the image model from a long
summary. This is what fixed the "long, dumb on-image titles" complaint — writing marketing
copy is the copywriter's job; asking an image model to also invent headline text from a
vague summary was the actual mistake, not something more prompt engineering on the image
side could fix.

`pin_pipeline.py` rewritten to call `pin_generator.py` via subprocess instead of
`copy_writer.py` + `skills/creative-designer/main.py`. Old Pinterest Agent (`skills/
pinterest-agent/` — `copy_writer.py`, `pinterest-expert.md`, `topic_selector.py`, the Canva
image pipeline) is completely untouched and out of scope — Jane's explicit call on whether
to keep or delete any of it later.

**One implementation bug found and fixed during testing**: `_enforce_case(text, upper=True)`
was keeping proper nouns capitalized-not-uppercase ("Wix BUILT-IN FEATURES" instead of "WIX
BUILT-IN FEATURES") — proper nouns need to match the surrounding case, not always stay in
Title case. Fixed; didn't end up visible in the test run shown to Jane (the pin with paired
Wix/Shopify items happened to render as a photo-type pin, which skips the item list), but
matters for future infographic-type comparison pins.

**Verified with a real run** on `shopify-vs-wix-for-ecommerce`: 5 pins, grounded in the real
post, natural coherent sentences (not disconnected nouns), one variation organically
produced genuine paired Wix/Shopify content straight from the post's real comparison
sections (no invented duplication), short keyword-forward titles matching Jane's own
examples, no cramped/distorted icons, 3 infographic + 2 photo split. Jane confirmed: "these
new ones look good."

### Part C — backfilled the same post's missing images + newsletter upgrade

`shopify-vs-wix-for-ecommerce` (written 2026-06-26, predates the current image pipeline)
had zero images and had never been through pins/newsletter at all. Generated 3 fresh cover
+ 4 inline images (new Claude call inserts `[DALLE: ...]` markers into the *existing*
already-written body without changing any wording, then renders them the normal way),
reassembled via `blog_seo_agent._assemble_html()`, preserved the FAQ schema. Cost: $0.65
images this post. Confirmed this generalizes — see "What's NOT yet done" for the other 12
draft posts in the same situation.

Newsletter (`content_repurposer.py`): Jane wanted 3 subject line variations (not 2) plus a
single inbox description capped at 80 characters (was: 2 subject lines + ~90-char preview
text, uncapped in practice). Prompt rewritten accordingly, verified both on pinterest-seo
and shopify-vs-wix-for-ecommerce — real output landed at 64-65 characters, well inside the
cap, each subject line a genuinely different angle.

### Part D — fixed a real audience-bias bug: content defaulted to coaches/service only

Jane, reviewing the Shopify-vs-Wix pins: "don't push the idea that I sell templates for
coaches only... Shopify is not for coaches, it's mostly for ecommerce." Traced to hardcoded
instructions in multiple places that forced every post's examples toward
coaches/service-providers regardless of topic — a real bug for ecommerce-specific keywords
like Shopify, where the natural audience is product sellers. Fixed everywhere it was
actually driving generation (not just illustrative example text): `CLAUDE.md` (Business
Overview, Target Customer, Niches, Wix Website product description — now explicitly
"service providers and coaches, but also product-based and ecommerce sellers", topic
decides framing), `blog_seo_agent.py` (3 hardcoded lines: research prompt, "REAL EXAMPLES"
instruction, "DEPTH AND VALUE REQUIREMENTS"), `content_repurposer.py`,
`pinterest-pins/pin_writer.py`, `context/product-catalog.md` (Bundle + Wix Website "who
it's for" sections). Left untouched: `context/content-style-examples.md`'s illustrative
"business coach templates" snippets (tone examples, not audience-restricting rules) and the
out-of-scope `pinterest-expert.md`.

### Part E — dashboard/Wix-sync gap (the "manual testing bypasses the orchestrator" bug, again)

Jane asked why she didn't see the Shopify-vs-Wix update on the dashboard. Same root cause as
Session 2 Part B, recurring because Session 3's work was done via direct one-off test
scripts (proving out the new module), not through `check_replies_and_execute.py`. Fixed for
this post specifically: (1) synced the Wix draft with the new backfilled content via
`publish_to_wix.publish(slug, draft_id=...)` — it had gone stale, still showing the
pre-backfill body; (2) committed and pushed everything (had been sitting local-only); (3)
manually added a `general_manager.latest_run_posts[]` entry in the exact schema
`_build_post_report()` produces, since the real orchestrator never ran. See the reminder at
the top of this file — this needs to stop being a recurring surprise.

**Files touched in Session 3** (beyond the new `pinterest-pins/` module and Part A's
already-listed files):
```
CLAUDE.md                                Business Overview, Target Customer, Niches, Wix
                                          Website product line broadened past coaches/
                                          service-only.
agents/blog-seo-agent/blog_seo_agent.py  3 hardcoded audience lines fixed (see Part D).
agents/content-repurposer/content_repurposer.py   Newsletter prompt rewritten (3 subject
                                          lines + 80-char description); audience line fixed.
agents/general-manager/pin_pipeline.py   Rewritten to call the new pinterest-pins module.
context/pin-reference-styles.json        pin_type field added ("infographic"/"photo") per
                                          reference; short_description field added (terser
                                          than the original long descriptions — confirmed
                                          via Jane's direct ChatGPT test that long mechanical
                                          descriptions underperform a short structural cue).
context/product-catalog.md               Bundle + Wix Website "who it's for" broadened.
posts/shopify-vs-wix-for-ecommerce.html  Backfilled with real images (see Part C).
dashboard_data.json                      general_manager.latest_run_posts + repurposer.posts
                                          entries added for shopify-vs-wix-for-ecommerce.
```

---

## What's confirmed working (tested live)

- Full pipeline for real keywords, multiple times across Sessions 2 and 3 — images, Wix
  draft updates, Tailwind pins, newsletter, all verified against actual rendered output, not
  assumed.
- Dashboard Overview tab GM report card — real links, verified.
- **New Pinterest pin system** (`agents/blog-seo-agent/pinterest-pins/`) — grounded in real,
  full post content; genuine coherent copy; short keyword-forward on-image titles; no
  cramped icons; no duplicate-content-on-mismatched-layout bug; 3-infographic/2-photo split;
  case enforcement bug found and fixed. Verified on `shopify-vs-wix-for-ecommerce`, confirmed
  good by Jane.
- Backfilling images + pins + newsletter for an already-written, pre-pipeline post — proven
  once on `shopify-vs-wix-for-ecommerce`.
- Audience framing now genuinely follows topic (ecommerce topics get product-seller
  examples, not forced coaching framing).

## What's NOT yet done

1. **12 more Wix drafts need the same backfill treatment.** Confirmed (Session 3) that all
   13 posts in Jane's Wix Drafts tab already exist as fully-written posts in `posts/*.html`
   — this isn't a writing task. Only `pinterest-seo` and (as of this session)
   `shopify-vs-wix-for-ecommerce` have images/pins/newsletter. The other 11 — 5 more June
   Shopify/ecommerce posts, 6 June Pinterest posts — have zero images, zero pins, zero
   newsletter, and predate the current image pipeline: `how-to-set-up-shopify-store`,
   `shopify-theme-store`, `shopify-store-template`, `how-to-choose-a-shopify-theme`,
   `online-store-for-small-business`, `how-to-get-followers-on-pinterest`,
   `pinterest-tips-for-beginners`, `how-to-start-a-pinterest-page`,
   `pinterest-marketing-manager`, `how-to-create-pins-on-pinterest`,
   `how-to-earn-money-from-pinterest`. Same pattern as Part C above, one at a time, each
   confirmed with Jane before moving to the next — do NOT batch all 11 unattended.
2. **Old broken Tailwind drafts need manual cleanup.** Several stale test batches now exist
   across Sessions 2 and 3 (blank-background bug, pre-copy-rebuild generic batch, several
   during-Session-3 iteration batches). No safe API-verified way to delete found — flagged
   for Jane to clean up by hand in Tailwind directly.
3. **The outer GM loop** (`analyze_and_recommend.py` → GitHub issue → `check_replies_and_
   execute.py`) still hasn't been re-tested end to end since either pin rebuild. Only the
   inner pin-generation step (now via the new module) has been directly re-verified.
4. **launchd activation** — still not installed to `~/Library/LaunchAgents`. Explicitly a
   "do this last" step.
5. **`POSTS_PER_WEEK`** — still defaults to 2, never explicitly confirmed with Jane.
6. **CLAUDE.md's Agent Directory / Skills Directory** still don't mention general-manager or
   the new pinterest-pins module. Documentation debt, not functional debt.
7. **Decide what to do with the now-doubly-superseded old Pinterest pin system**: `skills/
   pinterest-agent/` (`copy_writer.py`, `pinterest-expert.md`, `topic_selector.py`,
   `analyze_reference_pins.py`, the Canva image pipeline) and `skills/creative-designer/`'s
   own copy/image path (`infographic_pin_prompt.py`, `image_generator.py`, `main.py`) are
   both now unused by GM but still present and technically functional if run manually.
   Explicitly Jane's call — she asked for the full picture of what each does before
   deciding what to delete; that explanation happened this session but no deletion decision
   was made yet.
8. Backfilling the 44 already-published (non-draft) posts with leaked `[DALLE: ...]` text —
   still optional, still not done. Separate from item 1 above (those are unpublished drafts
   missing images entirely, not published posts with a text-leak bug).

## Immediate next step

Jane's choice. Most likely candidates given how this session went: (a) continue the Wix
drafts backlog — pick the next post from item 1 above and run the same backfill+pins+
newsletter treatment, confirming each one before moving to the next; (b) re-test the full
outer GM loop now that pin generation is stable; (c) clean up stale Tailwind drafts and
decide the old pin system's fate (item 7). Nothing should be assumed — ask before proceeding,
per how both sessions have gone (Jane reviews and corrects before anything is declared done,
and has twice now discovered gaps caused by manual testing bypassing the real dashboard/git
update path — check that specifically after any hands-on testing).
