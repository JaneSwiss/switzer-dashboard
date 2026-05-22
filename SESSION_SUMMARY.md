# Session Summary — Traffic Sprint + Dashboard + Agents
**Date:** 23 May 2026  
**Pick up from here in a new chat**

---

## WHERE WE ARE

### Active sprint
A 4-week traffic growth plan is live. Sprint started 22 May 2026.
Full plan: https://github.com/JaneSwiss/switzer-dashboard/blob/main/sprint-plan.md
Sprint Tracker with checkboxes is in the Dashboard → Blog SEO tab.

**Goal:** Grow switzertemplates.com from ~1,000 to 10,000 visitors/month.  
**Honest timeline:** 10k is achievable by month 4–6, not week 4. The sprint plants every seed.

**Traffic map (evidence-based):**
- Email re-engagement → +1,000–2,500/month in 24–48 hrs (Backlinko: email 7x faster than social)
- Etsy → website funnel → +500–1,500/month immediately (Jane still needs to do this manually in Etsy)
- Featured snippets restructure → +200–600/month in 2–4 weeks
- Google Discover → +200–500/month in 2–4 weeks
- Free lead magnet → +200–400/month in 1–2 weeks (Jane still needs to create this)
- SEO quick wins → +200–400/month in 7–14 days
- Pinterest static pins → +200–500/month but only after 60–90 days min (month 3–4 compounding)

**Key insight confirmed by research:** Pinterest algorithm does NOT penalise old URLs. New pin designs for old posts = fresh content. Old blog posts are worth pinning.

---

## WHAT WAS BUILT THIS SESSION

### 1. Content Repurposer Agent ✅ COMPLETE
**File:** `agents/content-repurposer/content_repurposer.py`

Reads any blog post HTML and generates:
- **10 Pinterest pin copy sets** (title + description + URL) → `outputs/repurposed/{slug}/pins.json`
- **1 email hook** (subject A/B + preview text + full body) → `outputs/repurposed/{slug}/email_hook.md`
- **1 Instagram carousel** (cover + 6 slides + caption + hashtags) → `outputs/repurposed/{slug}/instagram_carousel.md`

**Already run on all 19 existing posts → 190 pin copy sets, 19 email hooks, 19 carousels.**

How to run:
```bash
python3 agents/content-repurposer/content_repurposer.py --post <slug>   # single post
python3 agents/content-repurposer/content_repurposer.py --all           # all posts (skips already done)
```

Run this on every new blog post immediately after the Blog SEO agent writes it.

---

### 2. Blog SEO Agent — major improvements ✅ COMPLETE
**File:** `agents/blog-seo-agent/blog_seo_agent.py`

Improvements made:
- **Minimum 1,800 words**, target 2,000+, scales up based on competitor word counts
- **Research pipeline:** gather_research_snippets() + synthesize_research() builds a research brief before writing
- **FAQ section** with real questions from Google "People Also Ask" + Reddit threads
- **Direct answer in intro** (first 1–2 sentences state the answer, then open up to reader situation)
- **5 images per post:** 4 × landscape 16:9 (lifestyle, props, person+action, topic focus) + 1 × portrait 9:16 (Pinterest pin)
- **Expanded image variety:** 30+ location types including outdoor, studio, home, moody interiors; outfit rotation enforced (1 bold, 1 neutral); group option for coaching topics
- **FAQ JSON-LD schema** auto-extracted from post and embedded in `<head>` for Google rich results
- **Indexing:** Google sitemap ping on every run; `publish_indexing.py` for Bing + IndexNow after Wix publish

**Posts written this session:**
- `pinterest-marketing` — 4,779 words
- `pinterest-affiliate-marketing` — 4,227 words
- `coaching-business` — 3,985 words

**Next keyword in queue:** `pinterest-marketing-strategy` (Pinterest vol 1,318)

How to run the blog agent:
```bash
python3 agents/blog-seo-agent/blog_seo_agent.py
```

How to submit for indexing after publishing to Wix:
```bash
python3 publish_indexing.py <slug>
# Example: python3 publish_indexing.py pinterest-marketing-strategy
```

---

### 3. Dashboard — major updates ✅ COMPLETE

**Tab order:** Overview → Blog SEO → Repurposer → Etsy Expert → Pinterest

**New: Repurposer tab**
- Shows all 19 repurposed posts
- Links to pins.json, email_hook.md, instagram_carousel.md on GitHub for each post
- Checkboxes: "Pins scheduled in Tailwind", "Email sent in Flodesk", "Carousel posted on Instagram"
- Stats bar: total pins scheduled / emails sent / carousels posted / fully done

**New: Sprint Tracker card (in Blog SEO tab)**
- Link to full sprint plan on GitHub
- Daily task checkbox: "Upload 7 pins to Tailwind"
- Current week's tasks with owner badges (Claude / Jane / Run)
- Progress bar + overall % complete
- Auto-detects current week from sprint start date (22 May 2026)
- All saves persist to GitHub

**Post tracker improvements:**
- Pagination: 10 posts per page
- Published posts show strikethrough + grey title
- Source column shows "Jane uploaded" badge for her keywords

**Keyword masterlist improvements:**
- Pagination: 20 per page
- Pinterest Vol column (colour-coded)
- Source column

**Overview improvements:**
- Removed Everbee CSV notification
- Removed "Needs your attention" block
- Monthly accomplishments now auto-generated from real data (agents built, posts written, repurposed content, sprint tasks)
- Title shows current month name ("May accomplishments")
- Historical months shown below (April 2026 archived)

---

### 4. Keywords added to masterlist
**File:** `agents/blog-seo-agent/keywords/switzertemplates_keyword_masterlist.csv`

19 new keywords added from two CSV files Jane uploaded, all marked P1, sorted by Pinterest volume:
1. pinterest marketing (10,926 Pinterest vol)
2. pinterest affiliate marketing (8,260)
3. coaching business (2,169)
4. pinterest marketing strategy (1,318)
5. online coaching business (953)
6. wellness coaching business (912)
7. life coaching business (536)
8. pinterest marketing tips (464)
9. pinterest marketing business (269)
10. health coaching business (211)
11. faceless pinterest marketing (209)
12. business coaching website (199)
13. pinterest marketing expert (172)
14. pinterest marketing for beginners (131)
15. successful coaching business (117)
16. digital marketing pinterest (112)
17. pinterest marketing course (98)
18. coaching business plan (67)
19. starting a coaching business (59)

Each has a "Notes" column with pin inspiration from top-performing Pinterest pins.

---

### 5. GEO / AI visibility setup ✅ COMPLETE
- **llms.txt** created at repo root: tells AI crawlers (ChatGPT, Perplexity, Claude, Gemini) exactly who Switzertemplates is, all products with correct URLs, Pinterest services page
- **JSON-LD Organization schema** added to Wix via Custom Code → Head → All Pages (includes all products, prices, 2,800 reviews aggregateRating)
- **FAQ JSON-LD** auto-embedded in every blog post `<head>` by the agent
- **Wix Article schema** updated: hardcoded author to "Jane Switzer", added inLanguage: "en-US"
- **llms.txt** includes Pinterest marketing services at pinterest.switzertemplates.com ($699 and $1,299 packages)

---

### 6. Wix SEO fixes done by Jane
- BLOG_BASE_URL confirmed as `https://www.switzertemplates.com/post`
- BING_API_KEY added to .env
- JSON-LD schema added to Wix head via Custom Code
- Robots meta tag and indexing settings checked in Wix blog settings

---

## WHAT STILL NEEDS TO BE BUILT

### 1. Email Copy Agent (HIGH PRIORITY — build next)
**Planned location:** `agents/email-agent/email_agent.py`

**Phase A — Research (runs once):**
- Downloads transcripts from Maxwell Copy + Alex Cattoni YouTube channels using `youtube-transcript-api`
- Synthesizes into `context/email-copywriting-principles.md`
- Command: `python3 agents/email-agent/email_agent.py --research`

**Phase B — Writing (runs per email):**
- `--re-engagement` → "are you still there?" email to clean the list (15% open rate problem)
- `--blog-post <slug>` → email promoting a specific blog post
- `--product <name>` → product-focused email with website CTA
- `--weekly` → picks latest post, writes the week's email

Output: `outputs/emails/YYYY-MM-DD-{type}.md` — ready to paste into Flodesk.
Must include: subject line + A/B variant, preview text, full body, CTA to switzertemplates.com (NOT Etsy).

**New dependency to install:** `pip install youtube-transcript-api`

### 2. Product Page Pin Generator (HIGH PRIORITY)
Generates pin copy for product pages (not blog posts):
- 5 pins → `/branding-packages`
- 5 pins → `/premade-wix-website-templates-for-sale`
- 5 pins → `/business-template-bundles`
- 5 pins → `pinterest.switzertemplates.com`

Can be a simple script, output as JSON for Tailwind manual scheduling.

### 3. Jane's manual tasks (no code needed)
- **Etsy → website funnel:** Add switzertemplates.com to Etsy shop announcement + bio + message to buyers. Create website-only offer/discount.
- **Free lead magnet:** Create a free mini template pack or checklist on a Wix landing page. Pinterest pins link to it (converts 3x better than product pages).
- **Directory submissions:** Creative Market, Design Bundles, Product Hunt, blogger outreach for "best templates" roundups.
- **Featured snippets:** Restructure top 5 blog posts so first paragraph answers the question in 40–60 words.
- **Request indexing:** Submit all 48 Wix blog posts via Google Search Console.
- **IndexNow key:** Create Wix page at `/switzertemplates2026` with just that text, add `INDEXNOW_KEY=switzertemplates2026` to .env.

---

## DAILY ROUTINE (while sprint is active)

| Task | Who | Time |
|------|-----|------|
| Run blog SEO agent | Agent | ~10 min |
| Publish post to Wix + run publish_indexing.py | Jane | ~15 min |
| Run repurposer on new post | Agent (1 command) | ~5 min |
| Upload 7 pins to Tailwind (repurposer copy + Canva images) | Jane | ~25 min |
| **Total** | | **~55 min/day** |

**Pin strategy:** 7 pins/day max (safe Pinterest limit). Mix blog pins + product page pins.
Current supply: 190 pin copy sets = 27 days. Will grow as new posts are written.

---

## KEY FILES REFERENCE

| File | Purpose |
|------|---------|
| `agents/blog-seo-agent/blog_seo_agent.py` | Main blog writing agent |
| `agents/blog-seo-agent/keywords/switzertemplates_keyword_masterlist.csv` | 108 keywords, P1 first |
| `agents/content-repurposer/content_repurposer.py` | Repurposes posts → pins + email + carousel |
| `outputs/repurposed/` | All repurposed content, one folder per post slug |
| `posts/` | All blog post HTML files |
| `publish_indexing.py` | Run after publishing to Wix → submits to Google + Bing |
| `sprint-plan.md` | Full 4-week traffic growth plan |
| `llms.txt` | AI crawler info file (needs to go on Wix domain too) |
| `context/brand-voice.md` | Tone, banned words, writing rules |
| `context/product-catalog.md` | All products with pricing and CTAs |
| `dashboard_data.json` | All dashboard data, sprint tracker, repurposer state |
| `switzer_ai_dashboard.html` | The dashboard UI |

---

## ENVIRONMENT / API KEYS IN .ENV
- `ANTHROPIC_API_KEY` — Claude (all agents)
- `VALUESERP_API_KEY` — Google SERP research
- `NANO_BANANA_API_KEY` — Gemini Imagen (blog images)
- `BING_API_KEY` — Bing indexing submission ✅ added this session
- `BLOG_BASE_URL=https://www.switzertemplates.com/post` ✅ set this session
- `TAILWIND_API_KEY` — Pinterest scheduling
- `INDEXNOW_KEY` — not yet set (needs Wix page created first)

---

## BUSINESS CONTEXT (for new chat)
- **Business:** Switzertemplates — Canva templates, Wix website templates, branding kits, Instagram templates, Pinterest marketing services
- **Owner:** Jane Switzer
- **Etsy:** Top 1% seller, Star Seller, 27,700+ sales, 2,800+ reviews
- **Email list:** 21,000 subscribers (past buyers), 15% open rate — needs re-engagement
- **Pinterest services:** pinterest.switzertemplates.com — $699 strategy / $1,299 strategy + setup
- **Website:** switzertemplates.com (Wix)
- **Dashboard:** https://janeswiss.github.io/switzer-dashboard/
- **GitHub:** https://github.com/JaneSwiss/switzer-dashboard
- **Traffic goal:** 10k/month (currently ~1,000/month)
- **Blog URL format:** switzertemplates.com/post/{slug}
