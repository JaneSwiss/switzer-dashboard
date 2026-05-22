# 4-Week Traffic Sprint Plan — switzertemplates.com → 10k/month

## Context

Jane needs to grow website traffic from ~500–2,000/month to 10,000/month in 4 weeks.
Purely organic (no paid ads). Urgent financial situation — website must become primary
income source. This plan uses every existing asset and builds missing automation pieces.

---

## Revised Situation Assessment

**Key constraints:**
- Email: 21,000 subscribers, 15% open rate. Engagement is the problem, not list size.
- Pinterest: Takes 60-90 days minimum for real traffic. NOT a 4-week lever.
- Creative designer skill: Unreliable. Don't depend on it for the sprint.
- No paid ads budget.
- Old blog posts: **Worth pinning** — Pinterest algorithm doesn't penalise URL age,
  only pin image repetition. New pin designs for old posts = fresh content to Pinterest.
  (Source: GTR Socials, PassHulk, Sprout Social — all confirm this independently.)

---

## HONEST TRAFFIC MAP

### What can move in 4 weeks

| Source | Realistic monthly add | Timeline | Evidence |
|--------|----------------------|----------|----------|
| **Email — re-engagement + CTAs to website** | +1,000–2,500 | 24–48 hrs | Backlinko: email drives 7x more traffic than social per send |
| **Etsy → website funnel** (27,700 existing buyers) | +500–1,500 | Immediate | 1–3% conversion rate on warm audiences; zero competition for your own buyers |
| **Featured snippets** (restructure existing posts) | +200–600 | 2–4 weeks | 64% snippet capture rate documented; 47% traffic lift (Koanthic case study) |
| **Google Discover** (image-rich posts, consistent publishing) | +200–500 | 2–4 weeks | Blog grew 80K → 117K sessions/month after Discover optimisation (Newsifier) |
| **Free lead magnet** (drives Pinterest clicks + email signups) | +200–400 | 1–2 weeks | 25–30% conversion rate for ecommerce lead magnets; free downloads 3x CTR vs product pages |
| **SEO quick wins** (meta titles, descriptions, indexing all 48 posts) | +200–400 | 7–14 days | Standard — known to improve CTR 15–30% within weeks |
| **Directories + roundups** (one-time submissions) | +100–300 | 2–4 weeks | Brafton: quality directory listings drive ongoing referral traffic for 12+ months |
| **Pinterest — static pins** (old + new content, 7/day) | +200–500 | 60–90 days | Realistic: "Month 1 = near-zero clicks" (84Pins). Compounding starts month 3–4. |
| **Total realistic in 4 weeks** | **2,400–6,700/month** | | |

### What compounds from month 3 onward

| Source | Realistic monthly add | Timeline | Evidence |
|--------|----------------------|----------|----------|
| **Pinterest — compounding** | +1,500–3,000 | Month 3–4 | Meagan Williamson: compounding starts month 3, accelerates month 6+ |
| **Pinterest — video/idea pins** (3x CTR vs static) | +500–1,000 | Month 2–3 | Tailwind: video pins get 3x impressions, 55% higher purchase intent |
| **Blog SEO** (20 new posts indexed + ranking) | +800–2,000 | Month 3–6 | Standard SEO timeline; faster with featured snippet targeting |
| **Email** (ongoing, open rate improving) | +1,500–3,000 | Ongoing | Depends on subject line overhaul and list cleaning |
| **All other channels** | +500–1,000 | Ongoing | |
| **Total at month 6** | **7,200–12,700/month** | | |

**The honest conclusion:** 10k/month in 4 weeks is not achievable organically.
10k/month by month 4–6 is realistic if all channels run together from day 1.
The 4-week sprint plants every seed. The compounding harvest is months 3–6.

---

## The Email Problem (and What to Actually Do)

15% open rate on a weekly list of past buyers means the list has gone behaviourally cold.
The content isn't compelling enough to open, or people have email fatigue from weekly sends.

**What we build:** An Email Copy Agent that writes emails following Maxwell Copy /
Alex Cattoni principles — curiosity-driven subject lines, personal tone, value before ask,
specific CTA to switzertemplates.com (not Etsy). The agent cannot send via Flodesk
(no public API) but writes ready-to-paste copy that Jane drops in.

**Tactics to improve open rates:**

1. **Re-engagement campaign first (Week 1):** Send one "are you still there?" email to the
   full list. Simple, honest, personal. Gives inactive subscribers a clear way to opt out.
   This cleans the list — 15% of a clean 10k list beats 15% of a cold 21k list every time.
   Open rates typically jump to 22-28% after a re-engagement + clean.

2. **Subject line overhaul:** Stop educational/generic subject lines.
   Use: specific numbers, a surprising statement, a direct call-out of a pain point.
   Example good: "Why your website isn't making sales (and it's not what you think)"
   Example bad: "5 tips for a better brand"

3. **Reduce frequency or make emails feel rarer/more valuable:** Weekly is a lot.
   Consider 2 sends/week but make each one feel unmissable.

4. **Every email must have 1 link to a blog post and 1 link to a product page on
   switzertemplates.com.** Not Etsy. Track clicks in Flodesk to measure website impact.

**What the Email Copy Agent produces per run:**
- Subject line (A/B variant included)
- Preview text
- Email body (200-350 words, brand voice, value-first)
- CTA block linking to specific blog post URL + product page URL

---

## What to Build

### 1. Content Repurposer Agent (HIGHEST PRIORITY)
**Location:** `agents/content-repurposer/content_repurposer.py`

Reads a blog post HTML file, makes one Claude call, outputs three things:

**a) 10 Pinterest pin copy sets** — each with:
- Title (50-80 chars, keyword-rich)
- Description (150-200 chars, benefit-led)
- Destination URL (blog post URL on switzertemplates.com)
Saved as `outputs/repurposed/{slug}/pins.json`

**b) Email hook** — 150-word email section introducing the post, with:
- Subject line suggestion
- Preview text suggestion
- Body paragraph driving to the post URL
Saved as `outputs/repurposed/{slug}/email_hook.md`

**c) Instagram carousel post** — complete, ready to publish:
- Cover slide title (punchy hook, stops the scroll)
- Slide 1–6 texts (one clear idea per slide, 2-3 sentences max, brand voice)
- Caption (educational or curiosity-led, ends with soft CTA, hashtags included)
Saved as `outputs/repurposed/{slug}/instagram_carousel.md`

**Batch mode:** `python3 agents/content-repurposer/content_repurposer.py --all`
Processes all posts in `posts/` directory in one run.
Then run on every new blog post after the agent writes it.

**The 48-post math:** 48 posts × 10 pins = 480 pin copy sets ready for Tailwind.
At 7 pins/day (Jane's realistic daily upload limit) = 68-day supply from one script run.
Jane uploads 7 pins manually to Tailwind each day using the generated copy + her own images.

---

### 2. Email Copy Agent (HIGH PRIORITY)
**Location:** `agents/email-agent/email_agent.py`

#### Phase A — Research (runs once, regenerates monthly)
Before writing any email, the agent builds a principles file by researching both
Maxwell Copy and Alex Cattoni's actual content.

**How it works:**
1. Uses ValueSERP to find top videos + articles from each creator
2. Uses `youtube-transcript-api` (free Python library, no API key needed) to download
   transcripts from their top 20-30 YouTube videos each
3. Fetches key blog posts / website content via existing requests/BeautifulSoup setup
4. One Claude call synthesizes everything into structured principles:
   - Subject line formulas that work
   - Email opening patterns
   - CTA structures
   - Tone and voice rules
   - What to avoid
5. Saves to `context/email-copywriting-principles.md`

**Channels to research:**
- Maxwell Copy: https://www.youtube.com/@maxwellcopy/
- Alex Cattoni: https://www.youtube.com/@AlexCattoni/

**New dependency:** `pip install youtube-transcript-api`
**No new API keys needed** — uses existing ValueSERP + Claude.

#### Phase B — Email Writing (runs per email)
**Modes:**
- `--research` — runs Phase A only, rebuilds the principles file
- `--re-engagement` — writes the re-engagement campaign email for Week 1
- `--blog-post <slug>` — writes a full email promoting a specific blog post
- `--product <product-name>` — writes a product-focused email with website CTA
- `--weekly` — picks the latest published blog post and writes the week's email

**Uses:** brand-voice.md + content-style-examples.md + email-copywriting-principles.md

**Output:** `outputs/emails/YYYY-MM-DD-{type}.md` — ready to paste into Flodesk.
Includes: subject line (+ A/B variant), preview text, full body, CTA block.

---

### 3. Pinterest Product Page Pins (HIGH PRIORITY)
**New mode in:** `skills/creative-designer/main.py` OR standalone script

Generates pin copy specifically for product pages (not blog posts):
- 5 pins for `/branding-packages`
- 5 pins for `/premade-wix-website-templates-for-sale`
- 5 pins for `/business-template-bundles`
- 5 pins for `pinterest.switzertemplates.com`

Different angle from blog pins — direct benefit, product-focused, commercial intent.
Output: JSON ready for Tailwind manual scheduling.

**Note on creative-designer skill:** Since the skill is not reliable yet, product page
pins will be copy-only (title + description + URL). Jane schedules them in Tailwind
with existing pin images or manually created designs. No image generation dependency.

---

### 4. Etsy → Website Funnel (ZERO EFFORT, IMMEDIATE)
**No code needed. Jane does this in Etsy dashboard.**

Jane has 27,700+ Etsy buyers — the warmest possible audience. They already trust her.
Etsy's rules allow: website URL in shop announcement, shop bio, and message-to-buyers.
Etsy does NOT allow direct promotion of off-platform purchases in listings.

**Actions (30 minutes total):**
- Add switzertemplates.com to Etsy shop announcement with a hook:
  "Exclusive bundles + new templates drop on our website first"
- Add website URL to Etsy shop bio/about section
- Update the "message to buyers" (auto-sent after every purchase) to mention:
  "For exclusive bundles and more templates visit switzertemplates.com"
- Create a website-only offer (e.g., 15% off, or a free bonus template for website orders)
  to give Etsy buyers a reason to cross over

**Expected impact:** 1–3% of Etsy buyers clicking through = 277–830 warm visitors.

---

### 5. Free Lead Magnet (WEEK 1 — HIGH LEVERAGE)
**One Wix page + one Pinterest pin → ongoing traffic + email signups.**

Pinterest users click free downloads at 3x the rate of product pages.
A free resource also grows the email list with fresh, highly-engaged subscribers.

**What to create (Jane chooses one):**
- Free 5-template mini brand kit (a sampler of your best sellers)
- Free "Small Business Brand Checklist" PDF (educational, positions expertise)
- Free "Instagram Content Calendar Template" for coaches

**How it works:**
- Create a dedicated landing page on switzertemplates.com for the free resource
- Email agent writes the email sequence for new subscribers who download it
- Content repurposer creates 10 Pinterest pins linking to this page (not a sales page)
- Pins to a free resource convert 2–3x better than pins to product pages

**Expected impact:** 25–30% of landing page visitors convert to email subscribers.
Pins to a freebie page consistently outperform pins to product pages on Pinterest.

---

### 6. Featured Snippets (WEEK 1–2 — QUICK WIN)
**Restructure existing blog posts. No new writing needed.**

Featured snippets (the answer box at the top of Google results) are 3x easier to win
than ranking #1. One blog captured 64% of targeted snippets. Traffic lift: 47%.
The new agent-written posts already have FAQ sections — ideal for snippets.

**What to do:**
- Identify 10 existing posts that answer a specific question (e.g., "How to create a
  branding kit", "What should a coaching website include")
- For each: ensure the first paragraph directly answers the question in 40-60 words
- Ensure H2/H3 headings are phrased as the exact question
- Tables and bullet lists preferred by Google's snippet algorithm
- The FAQ sections we already added are exactly right for this

**Expected timeline:** 2–4 weeks. Some snippets appear faster.

---

### 7. Directories + Roundup Submissions (ONE-TIME, WEEK 1)
**2 hours of work. Ongoing passive traffic for 12+ months.**

Getting listed in "best Canva templates" or "best Wix templates for coaches" roundup
articles creates permanent referral traffic and SEO backlinks.

**Where to submit:**
- Creative Market (as a seller — she may qualify)
- Design Bundles
- Product Hunt (launch the website as a product)
- Canva template directories (search "best Canva template shops 2026")
- Blogging roundups: email 10–15 bloggers who wrote "best templates for coaches/small
  business" and ask to be included (include her 27,700 sales as social proof)

**Expected impact:** 100–300 additional visitors/month per placement, compounding.

---

### 8. Blog Post Publishing Sprint
**No new code needed.** Just execution:
- Run blog SEO agent daily (or every 2 days) to build post library fast
- Publish each new post to Wix same day
- Run `publish_indexing.py` for each post
- Run content repurposer on each post immediately after publishing

**Target:** 20 new posts published by end of Week 4.
Combined with 10 already published = 30 agent posts live on Wix.

---

## 4-Week Week-by-Week Plan

### Daily rhythm (Weeks 2–4, weekdays)
**~45–60 minutes total per day — this is what Jane does each day:**

| Task | Who | Time |
|------|-----|------|
| Run blog SEO agent | Agent (automatic) | ~10 min |
| Publish post to Wix + run publish_indexing.py | Jane | ~15 min |
| Run repurposer on the new post | Agent (1 command) | ~5 min |
| Upload 7 pins to Tailwind (repurposer copy + Canva images) | Jane | ~25 min |

**Week 1:** 3 posts total (~1 every 2 days — lighter while agents are being built)
**Weeks 2–4:** 1 post per day = 7 posts/week = up to 21 new posts by end of sprint

**Daily recurring task (every day, all 4 weeks):**
- [ ] Upload 7 pins to Tailwind (use repurposer copy + your own Canva images)

---

### WEEK 1 (Days 1–7): BUILD + ACTIVATE

**ME — Build (Days 1–3):**
- [ ] Build Content Repurposer agent
- [ ] Build Email Copy Agent (incl. Maxwell Copy / Alex Cattoni research phase)
- [ ] Build product page pin copy generator
- [ ] Add Sprint Tracker to dashboard

**JANE — Quick wins (Days 1–2, no code needed):**
- [ ] Add switzertemplates.com to Etsy shop announcement + bio + message to buyers
- [ ] Submit to 10 directories/roundups (Creative Market, Design Bundles, Product Hunt, 7 blogger outreach emails)
- [ ] Submit all 48 existing posts for indexing via Google Search Console

**RUN — Activate (Days 3–7):**
- [ ] Run Email Copy Agent `--research` → builds email-copywriting-principles.md
- [ ] Run repurposer on all 48 existing posts → 480 pin copy sets + email hooks + carousels
- [ ] Run product page pin generator → 20 product pins
- [ ] Run Email Copy Agent `--re-engagement` → Jane pastes into Flodesk and sends
- [ ] Run blog SEO agent 3× → publish 3 new posts to Wix + run publish_indexing.py each
- [ ] Add 2–3 internal product links to each of the 10 agent posts on Wix (~30 min)
- [ ] Create 1 free lead magnet (mini template pack or brand checklist) → live Wix page
- [ ] Upload 7 pins/day to Tailwind using repurposer output (start Day 3)

---

### WEEK 2 (Days 8–14): CONTENT SPRINT
- [ ] Run blog SEO agent daily → publish 7 new posts to Wix + index each
- [ ] Run repurposer on each new post → immediately queue pins in Tailwind
- [ ] Run Email Copy Agent `--blog-post <slug>` → Jane sends in Flodesk
- [ ] Upload 7 pins/day (blog pins + product page pins + lead magnet pins)
- [ ] Restructure top 5 blog posts for featured snippets (direct answer in first paragraph, Q&A headings)
- [ ] Check Flodesk re-engagement open rate → remove inactive contacts
- [ ] Confirm Tailwind queue has 7/day scheduled through end of week

---

### WEEK 3 (Days 15–21): COMPOUND
- [ ] Run blog SEO agent daily → publish 7 more posts (17 new total)
- [ ] Run repurposer on each new post → Tailwind queue grows
- [ ] Run Email Copy Agent `--blog-post <slug>` → Jane sends in Flodesk
- [ ] Upload 7 pins/day
- [ ] Update meta titles + descriptions on all 48 Wix blog posts (~1 hour)
- [ ] Check Pinterest analytics: which pins are driving outbound clicks?
  → Create 10 fresh pin variations for top 3 performing posts
- [ ] Check Google Search Console: are featured snippet restructures showing results?

---

### WEEK 4 (Days 22–28): DOUBLE DOWN
- [ ] Run blog SEO agent daily → publish 7 more posts (24 new total)
- [ ] Run repurposer on each new post → Tailwind queue
- [ ] Run Email Copy Agent `--blog-post <slug>` → Jane sends in Flodesk
- [ ] Upload 7 pins/day
- [ ] Traffic review: Google Analytics + Pinterest outbound clicks + Flodesk click map
- [ ] Identify top traffic source → double everything going into it

---

## Architecture Decision

**New agents to build:**
1. `agents/content-repurposer/content_repurposer.py` — NEW
2. `agents/email-agent/email_agent.py` — NEW

**Existing to extend:**
3. Product page pin copy — can be a small standalone script or added to repurposer

**Do NOT rely on creative-designer skill** — it's not stable enough to be in the
critical path of a 4-week sprint. Pin images can be created manually in Canva or
from existing brand assets.

**Flodesk stays manual** — no API. Email agent writes the copy, Jane sends it.

---

## Critical Files

| File | Action |
|------|--------|
| `agents/content-repurposer/content_repurposer.py` | CREATE |
| `agents/email-agent/email_agent.py` | CREATE |
| `agents/content-repurposer/product_pins.py` | CREATE (or merge into repurposer) |
| `context/email-copywriting-principles.md` | CREATE (email agent research output) |
| `context/brand-voice.md` | READ (used by email agent) |
| `context/content-style-examples.md` | READ (email style reference) |
| `context/product-catalog.md` | READ (used by product pin generator) |
| `posts/*.html` | READ (repurposer input) |
| `dashboard_data.json` | UPDATE — add `sprint_tracker` section with all checklist items |
| `switzer_ai_dashboard.html` | UPDATE — add Sprint Tracker tab with interactive checklist |

### Dashboard Sprint Tracker spec
**Location:** Blog SEO tab — new card added at the top, above the post tracker table.

**Card 1 — Plan link:**
- Title: "4-Week Traffic Sprint Plan"
- Button: "View full plan" → opens sprint-plan.md hosted on GitHub Pages
  (plan file copied to repo root as sprint-plan.md, rendered at GitHub blob URL)
- One-line summary of the sprint goal and honest timeline

**Card 2 — This week's checklist:**
- Shows only the CURRENT week's tasks (auto-detected from sprint start date)
- Each task is an interactive checkbox
- Owner shown as a small badge: "Claude" (I build it) or "Jane" (she does it)
- Checked items get strikethrough + green tint
- Progress bar: X of Y tasks done this week
- "Daily task" pinned at top: "Upload 7 pins to Tailwind" with today's checkbox

**Data persistence:**
- Checkbox state saved to `dashboard_data.json` → `sprint_tracker.weeks.weekN.tasks[].done`
- Saves to GitHub on every click (same `saveData()` pattern as published post toggles)
- Sprint start date in `dashboard_data.json` → `sprint_tracker.start_date`
- Current week auto-calculated from start date + today's date

---

## Verification / Success Metrics

**End of Week 1:**
- 480+ pin copy sets in Tailwind queue
- Re-engagement email sent, open rate > 20% (list is cleaner)
- 3 new blog posts live and indexed

**End of Week 2:**
- 8 new blog posts live
- First weekly email sent driving to switzertemplates.com
- Flodesk showing clicks to website domain

**End of Week 4:**
- 20 new blog posts live (30 total with agent posts)
- Google Analytics: track toward 8,000–10,000 monthly sessions
- Pinterest outbound clicks to switzertemplates.com increasing week-over-week
- Email open rate improved from 15% to 20%+ after list clean
