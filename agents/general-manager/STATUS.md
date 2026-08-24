# General Manager — STATUS

Last updated: 2026-08-20 (Session 4 — finished the Wix-drafts backlog, found and fixed 3
separate rounds of cover-image bugs, ran a real SEO audit that found keyword cannibalization
and a Wix-slug-mismatch bug breaking pin/newsletter links, rebuilt pin copy twice more after
Jane rejected it again, did real keyword research (Keywords Everywhere + ValueSERP) and wrote
2 new long-tail posts from it, wrote 2 posts leading with Jane's real products, and added two
permanent business-integrity rules to the writing prompt after finding the agent had argued
against Jane's own value proposition. Read this before doing anything else with the GM.)

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
   produced.

Hard constraint, unchanged: **everything lands as a draft** (Wix draft posts, Tailwind
draft pins). Nothing ever publishes live automatically.

**Recurring finding, still true in Session 4**: manually testing pipeline pieces directly
(calling `blog_seo_agent.run()`, `pin_generator.py`, etc. straight from the shell instead of
through `check_replies_and_execute.py`) produces real, correct output — but skips the *only*
code path that pushes to GitHub and writes `dashboard_data.json`. Session 4 kept working this
way deliberately (it's the only way to verify real output before spending on images/pins) and
just remembered to commit+push and hand-write the dashboard entry every time — this worked,
but the outer GM loop itself still hasn't been exercised for real (see "What's NOT yet done").

---

## SESSION 1 (2026-07-29) — original build

Full architecture designed and built: 12 design decisions, drafts-only autonomy, OpenAI for
images, GitHub Issues for the approval exchange, GA4/Search Console/Wix Analytics as data
sources, Wix cover-image upload stays manual, pin visual style reference-driven. See git
history for full detail — condensed here since later sessions superseded most of it.

## SESSION 2 (2026-08-01 to 2026-08-03) — real testing, then a full pin-quality rebuild

Fixed a pipeline-breaking `response_format` bug in OpenAI image calls. Built the dashboard's
GM report card (`general_manager.latest_run_posts[]`). Removed `content_repurposer.py`'s
disconnected pin-copy generation. First full pin-copy/design rebuild (`skills/pinterest-agent/
copy_writer.py` + `skills/creative-designer/infographic_pin_prompt.py`) — later fully
superseded in Session 3.

## SESSION 3 (2026-08-05) — pin generation rebuilt again, as a clean dedicated module

Root cause of bad pin copy traced to a **4,000-character excerpt truncation** in the old pin
pipeline — pin copy was being written blind to most of the real post. Rebuilt from scratch as
`agents/blog-seo-agent/pinterest-pins/` (`post_sections.py`, `pin_writer.py`,
`pin_image_prompt.py`, `pin_generator.py`) — full real post grounding, no length cap,
hardcoded rules instead of a living context doc. Fixed a real audience-bias bug (content
defaulting to coaches/service-providers even for ecommerce keywords) across `CLAUDE.md`,
`blog_seo_agent.py`, `content_repurposer.py`, `pin_writer.py`, `product-catalog.md`. Backfilled
images for `shopify-vs-wix-for-ecommerce`. See git history for full Session 3 detail — Session
4 continued directly from where this left off.

---

## SESSION 4 (2026-08-09 to 2026-08-20)

### Part A — finished the Wix-drafts audience-bias backlog

Rewrote the remaining biased posts from Session 3's list: `how-to-set-up-shopify-store`,
`shopify-theme-store`, `shopify-store-template`, `online-store-for-small-business`. Each: full
rewrite via `blog_seo_agent.run(force_keyword=...)`, Wix draft updated **in place** via the
real `draft_id` (never duplicated), newsletter, 5 pins, dashboard entry, commit+push.

**`shopify-theme-store` needed two passes.** First rewrite fixed the coach/service bias but
misread the keyword — "shopify theme store" was written as a tour of Shopify's own theme
marketplace, not "a shopify theme FOR a store." Jane: *"this blog post is bullshit, how it's
connected with my business at all?"* Re-ran with an explicit `angle_note` override (a real,
reusable mechanism — see "Reusable pattern" below) reframing it as a genuine buying guide with
one soft, no-price/no-link mention of Jane's Shopify themes.

**`shopify-themes.html` was never rewritten** — still has the old service-based bias. Skipped
because Jane said the keyword itself was "too broad" and asked for different long-tail
keywords instead (→ Part E). Still pending if she wants it done later.

### Part B — cover-image bugs, three separate rounds

**Round 1 — Prompt 1/3 composition+environment never varied cross-post.** Confirmed ~20 of 40
real posts picked "from behind at a desk" for Prompt 1 — each post's image-prompt call is
isolated with no memory of prior posts, so the model kept reaching for its one default. Fixed
in `blog_seo_agent.py`: `_cover_assignment(keyword)` — an MD5-digest hash of the keyword
deterministically assigns composition + environment per prompt (not a plain char-sum: two real
keywords collided under a naive sum because their sums differed by an exact multiple of both
list lengths — MD5 chunks don't share that risk). Verified visually before shipping.

**Round 2 — Prompt 2 was never covered by Round 1, and activities defaulted to "seated,
typing on a laptop."** Jane: *"again had very typical photos... female sits in the exact
angle as always, cover 2 features laptop and a planner - exactly like on all previous blog
posts."* Real cause: Prompt 2 (props/objects) had zero assignment logic and always defaulted
to "overhead flat lay" + MacBook + the same Productivity Planner; several `_PERSON_COMPOSITIONS`
entries left the *activity* unspecified, so Claude filled it in as desk+laptop regardless of
the assigned environment. Fixed: added `_OBJECT_COMPOSITIONS`/`_HERO_PROPS`/`_ACCENT_PROPS`
pools + assignment for Prompt 2; rewrote every `_PERSON_COMPOSITIONS` entry to bake in a
specific non-laptop-default activity. Verified visually — genuinely different, no laptop, no
repeat planner.

**Round 3 — covers looked irrelevant and too dark.** Jane: *"Only the second one is ok. Two
others are completely irrelevant to the post or to business theme, they also way too dark."*
Real cause: the composition/environment fix forced variety in pose+setting but never required
the result to actually relate to the post topic or stay adequately lit — got "Walking away" +
"dark moody office, warm amber lamp as the ONLY light source." Fixed: softened the darkest
`_ENVIRONMENTS` entries (paired warm lighting with genuine daylight), added two non-negotiable
rules to the Prompt 1/3 generation call — a topical anchor (phone/tablet/object visibly
connected to the post) regardless of assigned composition, and a brightness floor forbidding
single-dim-light-source scenes. Verified visually on the real failing post.

**Also found and fixed**: `generate_images_from_prompts()`'s cover-prompt parser matched
labels by *exact literal string* (e.g. `"PROMPT 3 - TOPIC SPECIFIC (person + action):"`), but
Claude doesn't always reproduce the exact parenthetical wording — silently dropped Prompt 3
entirely on a real post, before an unrelated OpenAI credit outage even hit. Fixed to match on
the `"PROMPT N -...:"` prefix via regex instead.

**Credit-outage recovery pattern (used twice, both providers)**: Anthropic ran out mid-run
once, OpenAI ran out mid-run once. Both times: verify the provider is actually back (don't
retry blind), then complete the *specific missing piece* directly (generate just the missing
cover images / just the missing inline images from the already-embedded prompt text) rather
than re-running the whole expensive pipeline from scratch. Worth reusing this pattern for any
future mid-run outage.

### Part C — real SEO audit, two structural findings

Jane, after publishing ~20 posts over 2 months with traffic still around 800/month: *"go and
figure why and what you can do about it."*

**Finding 1 — keyword cannibalization.** 4 separate posts (`how-to-choose-a-shopify-theme`,
`shopify-theme-store`, `shopify-store-template`, `shopify-themes`) all open with "HOW TO
CHOOSE A SHOPIFY THEME..." and repeat headings almost verbatim ("mobile test" in 3/4, "speed
factor" in 3/4) — splitting ranking signal four ways instead of consolidating it. Not yet
resolved — Jane's call on which becomes canonical.

**Finding 2 — Wix auto-generates the live URL from the post title, not from the slug the
system tracks internally.** Confirmed via the Wix Draft Posts API's `slugs`/`seoSlug` fields:
e.g. the post we call `shopify-theme-store` is actually live at
`/post/how-to-choose-a-shopify-theme-for-store`. Every pin destination URL, newsletter link,
and dashboard link generated by this system assumes `BLOG_BASE_URL/{our_slug}` — when Wix's
real slug diverges, those links 404. **Confirmed broken this way**: `shopify-theme-store` →
real slug `how-to-choose-a-shopify-theme-for-store`; `shopify-vs-etsy` → `shopify-vs-etsy-for-
ecommerce`; `trending-products-to-sell-online` → `20-trending-products-to-sell-online`;
`starting-a-business-tips` → `5-starting-a-business-tips`; `website-template-for-ecommerce` →
`website-template-for-ecommerce-business`; `pinterest-affiliate-marketing` → `pinterest-
affiliate-marketing-for-beginners-start-here`. Tried forcing the slug via `PATCH` — Wix
silently ignores it (read-only, assigned only at publish time by Wix itself). **No code fix
built yet** — the real fix needs a reconciliation step (using the saved `draft_id` to look up
the real published slug after Jane publishes, then correct dashboard/pin/newsletter links) —
flagged as a real "What's NOT yet done" item, not resolved this session.

Also found while investigating: the GitHub Pages preview domain root (`janeswiss.github.io/`)
404s, but the actual per-post preview pages (`janeswiss.github.io/switzer-dashboard/posts/
{slug}.html`) resolve fine and update within minutes of a push — don't misread the bare-domain
404 as the whole preview site being down (an actual mistake made and self-corrected this
session).

Real current numbers pulled (not guessed): GA4 only has data from 2026-07 onward (tracking
just connected, no earlier baseline exists to confirm/deny "less traffic than before"); Wix's
own analytics (62-day cap): 1,524 sessions / 1,214 unique visitors / $1,574.70 sales / 8 orders
over the last ~2 months — roughly matches Jane's own 800/month estimate.

### Part D — pin copy quality, three more rounds

**Round 1 — headlines drifted to random sub-topics instead of the post itself.** For
`best-ecommerce-website-design`, 4 of 5 pin headlines were pulled from specific sub-sections
("Why your store loses sales before checkout," "The homepage change that increased
conversions") instead of the post's actual identity — confirmed by comparing against
`shopify-vs-wix-for-ecommerce`'s pins (previously approved), where all 5 stayed anchored
because that post was narrow enough there was nowhere else to drift. Fixed: added a
non-negotiable anchor rule to `pin_writer.py` — every headline must be a rephrasing of
POST TITLE/KEYWORD, angle changes framing not topic.

**Round 2 — titles were too long/mechanical, and Jane wants OpenAI making its own design
decisions.** Jane: *"I don't need in the pin title some random pulled parts... I need blog
post title rephrased differently... the text on pin design is also mostly crap."* Real
examples of what she wants: short, natural, keyword-first ("Best ecommerce website design
that converts"), not a mechanical "keyword - long clause" formula. Also: *"stop telling
openai what eyebrow should be etc etc... ask him to create pins for it."* Two changes: (1)
`pin_writer.py` title guidance rewritten — target ~4-9 words, dash construction allowed
sparingly not as default; (2) `pin_image_prompt.py`'s `_content_block()`/eyebrow+points
dictation removed entirely — OpenAI now only gets the (short) headline quoted exactly and
designs the rest of the pin's content itself. Verified: 4/5 regenerated pins genuinely strong
("Why your Shopify store isn't converting" — probably the best pin produced all session).

**Round 3 — the transformation-angle headline lost the topic anchor entirely.** One pin's
headline came back as "From confusing to converting" — short, on-brand, zero topic words,
could be for any post. Jane: *"no bs abstract title so fix this one."* Fixed: `image_headline`
specifically must always contain a real topic word, no exceptions for any angle including
transformation. Verified — now reads "Confusing to converting - ecommerce design."

**Separately, Jane flagged the recurring "That Actually" title tic** across the whole blog
(not just pins): 15 of ~47 real post titles use "actually," including every single post
written in Session 4. Same root-cause class as Part B's cover-image bug (no cross-post memory,
model reaches for its one "sounds authentic" default). Fixed: added `check_banned_title_words()`
+ `BANNED_TITLE_WORDS = ["actually"]`, checked separately from body text (fine in prose, not as
a title formula), triggers the same revision-retry pattern as the existing banned-word check.

### Part E — real keyword research (Keywords Everywhere + ValueSERP), 2 new posts written

Jane asked for real long-tail, high-buyer-intent keywords for Shopify-theme-promoting posts.
Used `skills/pinterest-audit-client/keyword_research.get_keyword_volumes()` (Keywords
Everywhere — real Google volume/competition/CPC, `dataSource: "gkp"`) — **this was already
built and working, just never wired into blog_seo_agent's own research before**. Combined with
ValueSERP's `related_searches` + real top-10 domain checks to verify actual search *intent*,
not just guess from volume.

**Two real traps found and avoided**: "shopify store for sale" (880 vol!) and "buy a shopify
store" (390 vol) are both 100% dominated by Flippa/Empire Flippers/BizBuySell — people wanting
to buy an *existing revenue-generating business*, not a design template. "premade shopify
store" / "pre built shopify store" / "done for you shopify store" are dominated by
**dropshipping pre-built-store sellers** (stores pre-loaded with supplier products) — a
different product than what Jane sells. All excluded despite good-looking numbers.

**Best real opportunities found and written**: `how to start an online store` (1,600 vol, 0.48
competition) and `how to start selling online` (170 vol, 0.35 competition — lowest found,
trending up). Both written with an explicit `angle_note` banning filler/dry-steps language and
requiring one soft, grounded mention of Jane's Shopify themes.

For the later `best shopify themes 2026` post, same research surfaced: `minimalist shopify
theme` (110 vol, 0.85 comp), `shopify themes for sale` (110 vol, 1.0 comp), `best shopify
themes 2026` (30 vol, 0.4 comp — best ratio, chosen), `best selling shopify theme` (20 vol,
0.51 comp), `cheap shopify theme` (10 vol, 0 comp) — all confirmed genuine theme-marketplace
search intent via real SERP checks.

### Part F — `best-ecommerce-website-design` written per Jane's detailed brief

Jane specified: Shopify-focused, human/personal tone (not dry steps), must feature and explain
8 specific theme features (product catalog, blog, categories, mega menu, slide-out cart
drawer, free shipping progress bar, cart upsell suggestions, mobile optimized) since they're
what her own themes include. Written via `angle_note`, verified: personal anecdotes present
("I've seen dozens of Shopify stores fail..."), all 8 features covered with real why-it-matters
framing, one soft CTA mention, zero bias terms.

### Part G — `best-shopify-themes-2026` written leading with Jane's real product

Jane asked the post to build toward the real conclusion that her Shopify themes are the best
fit, with a working CTA link to her actual product page. **Her product page
(`switzertemplates.com/shopify-theme-templates`) is a Wix-rendered SPA — plain scraping/
WebFetch returns empty.** Pulled real structured data instead via the Wix Stores API
(`POST /stores/v1/products/query`) — found 4 real color-variant products ("Shopify theme
template - Black&Gold/Burgundy/Chocolate/Champagne"), $110 each, full real feature list and
licensing terms from the actual product description. This is a reusable pattern worth
remembering: **when a Wix page won't scrape, check whether it's a real Wix Store product and
pull it via the Stores API instead of guessing.**

Updated `context/product-catalog.md`'s Product 5 entry from "no page yet, don't link" to the
real URL + real features (price still omitted from generated copy per Jane's standing
instruction — it changes). Updated `blog_seo_agent.py`'s CTA_MAPPING for Shopify/ecommerce
posts to link to the real page instead of "no hyperlink."

**Found and fixed a real rendering bug while reviewing this post**: one CTA was written as
markdown `[text](url)` instead of raw HTML — `_assemble_html()` only ever converted
`**bold**`/`*italic*` markdown, never link syntax, so it would have rendered as literal visible
brackets on the page. Fixed this post directly and added markdown-link conversion to the
assembler for all future posts.

Newsletter/carousel/pins were explicitly skipped for this post per Jane ("no need for ig
carousel and pins as I don't like the quality of the pins you create").

### Part H — two permanent business-integrity rules added, both from real published mistakes

Jane, reading the live `best-shopify-themes-2026` post: *"why the fuck we are writing the blog
post with the angle that design doesn't matter??? I sell branding and design templates... very
disappointed."* Real section found: "YOUR THEME IS A REVENUE DECISION, NOT A DESIGN DECISION" —
argued function beats "aspirational aesthetic." Root cause: the research-driven writing
process picked up a common contrarian-SEO-blog angle from competitor research without checking
whether the post's actual *thesis* worked for or against what Jane sells — a real blind spot,
since Session 4's verification habit had checked facts/tone/bias/word-count/images but never
"does this argument serve the business." Rewrote the section (design AND function as a
package, never traded off) and added a permanent CRITICAL rule to `build_prompt()`'s system
instructions: never argue design/aesthetics matter less than something else, on any topic.

Immediately after, Jane asked for the general case: *"never promote products/apps or services
that goes into conflict with what I'm selling... free shopify themes just as good as
premium."* Checked and confirmed: 3 real posts (including `best-shopify-themes-2026` itself —
the post built specifically to sell the $110 theme) contain a section literally titled "Free
Themes Have Gotten Significantly Better - Here Is When They Are Enough." Added a second
permanent CRITICAL rule: never build a section recommending/reassuring that a free or cheaper
competing option is sufficient — mentioning free options exist is fine, concluding they're
good enough is not. **Neither rule has been retroactively applied to the 3 existing posts
that violate it** — `best-shopify-themes-2026`, `how-to-set-up-shopify-store`, and
`shopify-themes` still contain the old "free themes are enough" language. Jane was offered a
fix for `best-shopify-themes-2026` and hadn't responded before this status update.

### Part I — dashboard: "mark done" checkbox

Added to the General Manager report cards (`switzer_ai_dashboard.html`): a checkbox per post
that toggles `completed` in `dashboard_data.json` via the existing `saveData()` GitHub-token
write-back (same mechanism as the Sprint Tracker's daily-task checkbox) — checked items get
struck through, greyed out, and sink to the bottom of the list. **Confirmed working in the
wild**: Jane used it herself mid-session (caused two real `dashboard_data.json` merge
conflicts on `git pull --rebase`, both resolved by keeping her `completed: true` and merging in
whatever note text had changed on the other side — expect this to keep happening naturally
now that the feature is live, it's not a bug).

### Reusable pattern confirmed this session: `angle_note` override

`blog_seo_agent.run(force_keyword=..., angle_note=...)` — an optional parameter that overrides
`keyword_row["Notes"]`, which `build_prompt()` already surfaces as "PIN INSPIRATION FROM
JANE'S RESEARCH — angles and themes." Used repeatedly this session to: correct a keyword
misinterpretation (shopify-theme-store), enforce a specific tone/feature brief
(best-ecommerce-website-design), enforce buyer-intent research findings
(how-to-start-an-online-store, how-to-start-selling-online), and lead a post toward a specific
product (best-shopify-themes-2026). This is now the standard way to hand a one-off, specific
brief to a single post without changing the global prompt — reach for it whenever Jane gives
post-specific instructions beyond the default flow.

---

## What's confirmed working (tested live, Session 4)

- Full pipeline for real keywords — images (all 3 rounds of cover-image bugs verified fixed
  visually), Wix draft updates (in place, never duplicated), Tailwind pins, newsletter.
- Real keyword research via Keywords Everywhere + ValueSERP, including catching wrong-intent
  traps before wasting a post on them.
- Pulling real Wix Store product data via the Stores API when a page won't scrape.
- Credit-outage recovery (both Anthropic and OpenAI, mid-run) without re-running the whole
  expensive pipeline.
- Dashboard "mark done" checkbox — real writes confirmed, real merge conflicts handled.
- `angle_note` as the standard mechanism for post-specific briefs.

## What's NOT yet done

1. **Keyword cannibalization not resolved** — 4 Shopify-theme posts still compete with each
   other. Needs Jane's call on which becomes canonical and what happens to the other 3.
2. **Wix-slug-mismatch bug has no code fix** — only discovered and manually corrected
   case-by-case. Needs a real reconciliation step (draft_id → real published slug lookup) so
   pin/newsletter/dashboard links stay correct after Jane publishes. At least 6 confirmed
   broken links exist right now from posts published earlier in the site's history.
3. **3 posts still violate the new "no free-alternative promotion" rule**:
   `best-shopify-themes-2026`, `how-to-set-up-shopify-store`, `shopify-themes` all still
   contain "free themes are just as good/enough" language written before the rule existed.
   Not retroactively fixed. `shopify-themes.html` also still has the old coach/service bias
   from Session 3 — never rewritten (Jane called the keyword "too broad" and redirected to
   long-tail research instead — Part E).
4. **Old broken Tailwind drafts still need manual cleanup** — accumulated across Sessions 2-4
   (every pin-copy revision round created a new batch since Tailwind has no update/delete, only
   create). No safe API-verified delete found.
5. **The outer GM loop** (`analyze_and_recommend.py` → GitHub issue → `check_replies_and_
   execute.py`) still hasn't been re-tested end to end. All of Session 4's real runs went
   through direct `blog_seo_agent.run()` calls, same pattern as Sessions 2-3.
6. **launchd activation** — still not installed. Still explicitly last.
7. **`POSTS_PER_WEEK`** — still undecided.
8. **CLAUDE.md's Agent Directory/Skills Directory** — still don't mention general-manager or
   pinterest-pins. Documentation debt.
9. **Old pinterest-agent/creative-designer pin systems** — still unused by GM, still present,
   still Jane's call on whether to delete.
10. Backfilling the 44 already-published posts with leaked `[DALLE: ...]` text — still
    optional, still not done.

## Immediate next step

Jane's choice. Live candidates from this session specifically: (a) decide the fix for
`best-shopify-themes-2026`'s "free themes are enough" section (offer already made, awaiting
her answer); (b) decide which of the 4 cannibalizing Shopify-theme posts becomes canonical;
(c) `shopify-themes.html` still needs its audience-bias rewrite whenever Jane picks a next
long-tail angle for it; (d) build the Wix-slug reconciliation fix so pin/newsletter links stop
breaking silently. Nothing should be assumed — ask before proceeding, per how every session has
gone so far.
