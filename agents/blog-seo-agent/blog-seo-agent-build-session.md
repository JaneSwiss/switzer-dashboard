# Blog SEO Agent - Full Build Session Summary
*Switzertemplates | Built: 5 May 2026*

---

## What Was Built

A fully automated Blog SEO Agent that:
- Picks the next unwritten keyword from a prioritised masterlist
- Searches Google (US results) for the keyword via ValueSERP API
- Fetches and analyses all organic competitor pages on the first page (up to 10)
- Writes a complete 1,200-1,800 word blog post in the SwitzerTemplates brand voice
- Automatically checks for banned words and revises before saving
- Generates 3 detailed image prompts + 1 infographic prompt per post for Nano Banana Pro
- Saves the post as a clean `.html` file with brand-styled formatting, ready to open in browser and copy into Wix
- Logs every completed post with keyword, date, word count, and filename
- Never crashes - logs errors silently and continues

---

## Why Blog SEO Agent, Not Cowork or a Skill

- A skill is a reusable prompt - you still do the work manually
- Cowork executes one-off tasks but has no persistent memory or codebase
- Claude Code builds a real agent with persistent logic, API integrations, and a queue that remembers what's been written
- This agent runs repeatedly, improves over time, and requires zero manual decisions per post

---

## Lessons Applied From Pinterest Agent (To Avoid Repeating Mistakes)

| Mistake | Fix Applied |
|---|---|
| Built on invented keyword data | Validated full keyword masterlist before writing any code |
| No plan before touching code | Complete spec written in chat before Claude Code opened |
| Terminal output truncation | All outputs written to files, never printed raw to terminal |
| No version control | Git initialised as first action, commit after every milestone |
| Guiding Claude Code blind | Review full code in chat before running anything |
| Confirmation loops | Detailed spec upfront so agent makes its own decisions |
| Partial fixes without confirming | Claude Code shows exact changed lines before committing |
| API assumption failures | Verified ValueSERP free tier limits before building |

---

## Phase 1 - Keyword Research and Analysis (Done in Claude Chat, Not Code)

### Why Do This First
Validate the data before building anything. If the keyword intelligence is wrong, everything the agent writes is wrong.

### Files Provided
- `Keywords-Pinterest.csv` - 12 keywords from Keywords Everywhere (Pinterest searches)
- `Keyword-Pinterest-2.csv` - 15 keywords from Keywords Everywhere (Pinterest searches)
- `keywords-Google.csv` - 48 keywords from Keywords Everywhere (Google searches)
- `Pinterest_Analytics_overview.csv` - Top 50 pins by outbound clicks (Dec 2025 - May 2026)
- `Claude-keywords.csv` - 17 additional keywords identified from Pinterest analytics gaps

### Key Finding From Pinterest Analytics
The analytics file contained only pin URLs and click counts - no titles. To identify what each pin was targeting, the pin destination URLs were shared directly in chat (Pinterest pages themselves are blocked by robots.txt).

**Top performing pins:**
| Pin | Outbound Clicks | Type | Destination |
|---|---|---|---|
| 20 trending products to sell online | 2,987 | Blog post | switzertemplates.com/post/... |
| How to Make Your Instagram Account Look Professional | 847 (3 pins) | Blog post | switzertemplates.com/post/... |
| Boho Wix website for Service business | 139 | Product page | switzertemplates.com/product-page/... |
| Branding Kit Business Templates in Sage | 100 | Landing page | switzertemplates.com/branding-kit-landing |
| 20 Free Instagram Post Templates | 99 | Freebie | switzertemplates.com/freebies |

**Critical insight:** Blog posts drove 92% of all Pinterest outbound clicks. Product pins drove only 6%. The keyword research files were almost entirely product-focused ("website template for X") but the actual traffic came from educational how-to content.

**Core mismatch identified:** The existing keyword files did not contain the #1 and #2 traffic-driving keywords at all. "Trending products to sell online" and "how to make your Instagram account look professional" were completely absent from the research.

### Keyword Scoring Model

Each keyword scored across 5 factors (max 100 points):

| Factor | Max Points | Logic |
|---|---|---|
| Volume score | 35 | Log-scaled - 60,500/mo = 35pts, 100/mo = ~9pts |
| Competition score | 25 | (1 - competition) × 25 - lower comp = higher score |
| Trend score | 15 | >50% trending = 15pts, >20% = 10pts, >5% = 5pts |
| Relevance score | 20 | Tier 1 (direct product match) = 20, Tier 2 (educational lead-in) = 15, Tier 3 (broad) = 8 |
| Pinterest bonus | 15 | 500+ proven clicks = 15pts, 100+ = 10pts, 50+ = 5pts |

### Priority Tiers
- **P1 - Build first:** Score 70+
- **P2 - Build next:** Score 55-69
- **P3 - Build later:** Score 45-54
- **P4 - Low priority:** Score below 45

### Final Masterlist Stats
- 89 total keywords
- 52 with search volume
- 37 at zero volume (kept - tools undercount niche terms)
- 8 P1 keywords, 27 P2, 26 P3, 28 P4

### P1 Keywords (Write These First)
| Keyword | Monthly Vol | Competition | Score | Maps To |
|---|---|---|---|---|
| canva branding kit | 5,400 | 0.08 | 102 | Branding Kits |
| starting a business plan | 49,500 | 0.01 | 78 | Courses + Ebooks |
| e commerce business plan | 1,900 | 0.03 | 77 | Digital Products + Bundles |
| branding for business | 4,400 | 0.25 | 75 | Branding Kits |
| free instagram post templates | 390 | 0.21 | 73 | Instagram Templates |
| ecommerce business ideas | 14,800 | 0.11 | 72 | Digital Products + Bundles |
| trending products to sell online | 590 | 0.47 | 71 | Digital Products + Bundles |
| website template for portfolio | 22,200 | 0.17 | 71 | Wix Templates (General) |

### Output File
`switzertemplates_keyword_masterlist.csv` - 89 keywords, scored and prioritised, ready to feed to the agent.

---

## Phase 2 - External Tools Setup

### ValueSERP (Google Search API)
**Why ValueSERP over SerpAPI:**
- SerpAPI cheapest plan: $75/month for 5,000 searches
- ValueSERP free tier: 2,500 searches (one-time grant)
- At 89 keywords × 10 competitor pages = ~890 searches to write the full masterlist
- The entire masterlist fits within the free tier

**Why not Serper.dev:** Registration was unavailable at time of build ("not possible to register at this moment"). ValueSERP is a direct equivalent.

**Setup:**
1. Sign up at valueserp.com (no credit card required for free tier)
2. Copy API key from dashboard
3. Add to project root `.env` file as: `VALUESERP_API_KEY=your_key_here`

**How the agent uses it:**
- Sends `gl=us`, `hl=en`, `num=10` with every query
- Forces US Google results regardless of physical location (Sydney)
- Returns full first page organic results

---

## Phase 3 - Project Structure

### Existing Project Structure
The switzertemplates project already existed with:
```
switzertemplates/
├── agents/
├── context/
├── outputs/
├── skills/
├── templates/
├── data/
├── scheduler/
├── reports/
├── CLAUDE.md
├── claudeignore
└── .env
```

### Blog SEO Agent Added Inside agents/
```
agents/
└── blog-seo-agent/
    ├── keywords/
    │   └── switzertemplates_keyword_masterlist.csv
    ├── output/
    │   └── (blog posts saved here as .html files)
    └── logs/
        ├── completed.json
        └── errors.json
```

**Key decisions:**
- No separate `.env` - agent reads from project root `.env`
- No extra config files - kept deliberately simple
- context files (`brand-voice.md`, `content-style-examples.md`) already existed in `context/` - not duplicated

### Git Setup
Git was already initialised on the project. First agent commit:
```
git add -A
git commit -m "scaffold blog-seo-agent"
```

---

## Phase 4 - Agent Code

**File:** `agents/blog-seo-agent/blog_seo_agent.py`

### Module 1 - Keyword Loader
- Reads `keywords/switzertemplates_keyword_masterlist.csv`
- Creates `output/` directory if it doesn't exist (important: do this before globbing)
- Checks `output/` for existing `.txt` files to skip already-written keywords
- Sorts remaining keywords by Priority Tier (P1 first)
- Returns the next keyword as a dict

**Bug fixed:** CSV priority values are `"P1 - Build first"` not `"P1"` - tier sort uses `[:2]` slice to extract just `"P1"` before lookup.

### Module 2 - Competitor Research
- Calls ValueSERP with `gl=us`, `hl=en`, `num=10`
- Strips ads, knowledge panels, featured snippets - organic results only
- Fetches each organic URL with a realistic browser User-Agent header
- Extracts: page title, H1, all H2s and H3s, approximate word count, opening paragraph
- If a page blocks the fetch (Cloudflare, paywall, login wall): logs as "blocked", skips silently, moves on
- 0.5 second delay between page fetches
- Continues with whatever data it has, including zero competitor data if everything fails

### Module 3 - Blog Post Writer
- Reads `context/brand-voice.md` and `context/content-style-examples.md` at runtime
- Builds a detailed prompt including: keyword, priority tier, full brand voice rules, style examples, competitor analysis summary
- Calls `claude-opus-4-5` (best writing quality for nuanced brand voice tasks)
- Target: 1,200-1,800 words
- **Banned word check:** Runs automatically after first draft. If hits found, sends a multi-turn revision request with full context so Claude can fix in place.
- Returns clean post text

**Blog post structure enforced in prompt:**
1. Title - exact keyword, benefit-led, under 60 chars, sentence case
2. Introduction (100-150 words) - opens with reader's frustration, no "In this post..."
3. Body: 4-6 H2 sections (150-250 words each) - one idea per section, personal examples woven in
4. One mid-post CTA - tied to the problem being discussed, not a hard sell
5. Conclusion (100-150 words) - no "In conclusion", ends with final CTA

**Voice rules enforced:**
- Short sentences, active voice, plain language
- "You" and "your" throughout
- Regular dashes only ( - ) never em dashes ( — )
- Sentence case headings
- No rhetorical question-answer patterns
- No "Let's dive in" or "Today we're going to cover"
- Banned word list checked and revised automatically

### Module 4 - Image Prompt Generator
A separate Claude call runs after the blog post is written. It reads the post content and generates detailed, paste-ready prompts for Nano Banana Pro.

**Outputs per post:**
- 1 hero image prompt (rectangular, 16:9, landscape)
- 1-2 supporting image prompts (rectangular, 16:9, landscape)
- 1 infographic prompt (minimalist, brand colours, 5-6 elements max)

**Brand style context baked into every prompt (`IMAGE_PROMPT_SYSTEM`):**
```
SwitzerTemplates brand style: modern, minimal, clean, editorial.
Colour palette: warm beige, cream, chocolate brown, soft sage green, muted dusty blue, warm white.
Never: bright colours, gradients, cartoonish styles, cluttered layouts, stock-photo-looking people.
Rectangular images: landscape orientation, 16:9 ratio, clean negative space, professional.
Infographic: minimalist layout, brand colours only, clean sans-serif typography, white or cream
background, simple icons if needed, no more than 5-6 elements, professional and uncluttered.
```

**Graceful failure:** If the image prompt call errors, the post still saves with a placeholder note. The run never crashes because of this step.

**Prompts are topic-specific** - generated from the actual post content, not generic. Example infographic prompt produced for "e-commerce business plan":

> Minimalist vertical infographic on warm cream background titled "E-Commerce Business Plan Essentials" in clean sans-serif typography, featuring 5 simple sections arranged vertically with small geometric icons in chocolate brown and soft sage green: 1) Product and Problem (small box icon), 2) Target Customer (simple person silhouette), 3) Revenue Model (minimal coin stack), 4) Marketing Channels (simple megaphone), 5) Key Metrics (minimal chart line), each section has a brief one-line description in muted dusty blue text, plenty of white space between elements, no borders or boxes, professional and uncluttered editorial design style

### Module 5 - Output (HTML)
- Saves post as `output/keyword-slug.html` (not .txt)
- HTML is assembled using `_assemble_html()` with a clean, minimal template
- Word count in terminal and `completed.json` reflects actual words only (HTML tags stripped before counting)
- Image prompts appended inside a styled `<div class="image-prompts">` block at the bottom of the file
- Appends entry to `logs/completed.json` with: keyword, date, word count, filename
- Logs errors to `logs/errors.json` without crashing
- Prints terminal summary

**HTML template structure:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>[POST TITLE]</title>
<style>
  body { font-family: Georgia, serif; max-width: 780px; margin: 60px auto; padding: 0 24px; color: #2d2d2d; line-height: 1.8; }
  h1 { font-size: 2em; margin-bottom: 8px; }
  h2 { font-size: 1.3em; margin-top: 48px; margin-bottom: 12px; border-bottom: 1px solid #e0d9d0; padding-bottom: 6px; }
  p { margin: 0 0 20px 0; }
  .cta { background: #f5f0ea; border-left: 3px solid #b5896a; padding: 16px 20px; margin: 32px 0; }
  .image-prompts { background: #f9f9f7; border: 1px solid #e0d9d0; padding: 24px; margin-top: 60px; font-family: monospace; font-size: 0.9em; }
  .image-prompts h3 { font-family: Georgia, serif; font-size: 1em; color: #888; text-transform: uppercase; }
</style>
</head>
<body>
[POST CONTENT]
<div class="image-prompts">
<h3>Image Prompts for Nano Banana Pro</h3>
[IMAGE PROMPTS]
</div>
</body>
</html>
```

**HTML content rules:**
- Title in `<h1>`
- Body sections in `<h2>`
- Paragraphs in `<p>`
- CTA blocks in `<div class="cta">`
- No markdown in output - clean HTML only

**Glob update:** `load_next_keyword()` checks for both `.txt` and `.html` in output so existing posts (from before the HTML update) are never rewritten.

### Module 6 - Run
- Single `run()` function executes all modules in sequence
- One keyword per run
- Called at bottom of file with `if __name__ == "__main__": run()`

### Dependencies
```
anthropic
requests
beautifulsoup4
python-dotenv
```

Install with: `pip install anthropic requests beautifulsoup4 python-dotenv`

### Bugs Fixed Before First Run
1. **Tier sorting:** `tier_key` used `[:2]` slice to extract `"P1"` from `"P1 - Build first"`
2. **First run crash:** `OUTPUT_DIR.mkdir(parents=True, exist_ok=True)` added before `OUTPUT_DIR.glob("*.txt")`

---

## Phase 5 - Run Results

| Run | Keyword | Word Count | File | Notes |
|---|---|---|---|---|
| 1 | canva branding kit | 1,603 | canva-branding-kit.txt | First run, .txt format |
| 2 | starting a business plan | 1,526 | starting-a-business-plan.txt | Second run, .txt format |
| 3 | e commerce business plan | 1,631 | e-commerce-business-plan.html | First HTML run, 9/9 competitor pages fetched, banned word "imagine" caught and auto-revised |

All posts reviewed and approved. Quality described as good - reads naturally, not like generic AI content. HTML layout reviewed in browser and approved.

---

## How To Run The Agent

### Every time you want a new blog post:

1. Open Terminal (Cmd + Space → type "Terminal")
2. Navigate to your project:
```
cd ~/path/to/switzertemplates
```
(Tip: drag the switzertemplates folder into Terminal to paste the path automatically)

3. Run the agent:
```
python agents/blog-seo-agent/blog_seo_agent.py
```

4. Watch the terminal output - it prints progress as it runs (1-2 minutes)

5. Find your new post in `agents/blog-seo-agent/output/keyword-slug.html`

6. Open the `.html` file in your browser to read and approve the post

7. Copy the image prompts from the bottom of the HTML file into Nano Banana Pro, generate and download the images

8. Copy post content into your Wix blog editor, add the images, publish

### What the terminal output looks like when working correctly:
```
==================================================
  Blog SEO Agent — Switzertemplates
==================================================

[1/4] Loading next keyword...
  Keyword : e commerce business plan
  Slug    : e-commerce-business-plan

[2/4] Researching competitors...
  Fetching SERP for: e commerce business plan
  Fetching: https://competitor1.com...
  Done - 9/10 pages fetched successfully.

[3/4] Writing blog post...
  Calling Claude (claude-opus-4-5) to write blog post...
  Banned words found: ['imagine'] - requesting revision...

[4/4] Saving output...
  Saved  : agents/blog-seo-agent/output/e-commerce-business-plan.html
  Words  : 1,631
  Log    : agents/blog-seo-agent/logs/completed.json

==================================================
  Done.
  Keyword  : e commerce business plan
  File     : agents/blog-seo-agent/output/e-commerce-business-plan.html
  Words    : 1,631
==================================================
```

---

## Ongoing Maintenance

### When All 89 Keywords Are Written
Run the keyword list through Keywords Everywhere again and add new terms as the business grows. Drop the new CSV into `agents/blog-seo-agent/keywords/` (replace the old file or update it with new rows).

### Monitoring What's Working
Once posts are live on Wix, connect Google Search Console. It shows which posts are ranking, for which keywords, and how much traffic they're driving. Feed that data back into future keyword decisions.

### If the Agent Breaks
Check `agents/blog-seo-agent/logs/errors.json` first - it logs every error with the stage, keyword, and error message. Most common issues:
- ValueSERP API key expired or quota exceeded - check valueserp.com dashboard
- Anthropic API key issue - check your .env file
- A keyword slug already exists in output but completed.json doesn't have it - delete the .html file and rerun

### Adding More Keywords
Add new rows to `switzertemplates_keyword_masterlist.csv` following the same column format. The agent picks them up automatically on the next run.

### About Nano Banana Pro and Image Generation
Nano Banana Pro is a web-based UI tool (nanobanana.org) powered by Gemini 3 Pro. It does not have a public REST API - it cannot be called programmatically from the agent. The agent generates detailed image prompts instead, which you paste manually into Nano Banana Pro's interface.

The underlying model (Gemini) is accessible via Google Cloud Console / Google AI Studio if you ever want to automate image generation in a future build. The `NANO_BANANA_API_KEY` in your `.env` is a Google/Gemini API key that could be used for this.

---

## Content Pillars Covered By The Masterlist

| Pillar | Keywords | Maps To |
|---|---|---|
| Branding | 6 | Branding Kits |
| Business Education | 11 | Courses + Ebooks |
| Instagram | 5 | Instagram Templates |
| Ecommerce | 5 | Digital Products + Bundles |
| Website Templates | 10 | Wix Templates |
| General | 17 | Lower priority - write last |

---

## Tools and Accounts Used

| Tool | Purpose | Cost |
|---|---|---|
| Claude Code | Built the agent | Included in plan |
| ValueSERP | Google search results API | Free (2,500 searches) |
| Anthropic API (claude-opus-4-5) | Writes blog posts + image prompts | Pay per token |
| Keywords Everywhere | Keyword volume and competition data | Per search |
| Nano Banana Pro | Image and infographic generation (manual) | Subscription |
| Git | Version control | Free |

---

## Phase 6 - Image Prompt System Development (6 May 2026)

The `IMAGE_PROMPT_SYSTEM` constant went through multiple iterations based on live testing in Nano Banana Pro. This section documents the full evolution and final validated rules.

---

### Why Image Prompts Matter

Nano Banana Pro has no API - it cannot be called programmatically. The agent generates detailed text prompts instead, which are pasted manually into Nano Banana Pro's web interface. Getting these prompts right is critical because vague prompts produce generic AI-looking results that don't match the SwitzerTemplates brand.

---

### Photography - What Was Wrong Initially

First-generation photo prompts were too restrictive and identical across posts:
- Always defaulted to overhead flat lay workspace regardless of post topic
- Too polished and symmetrical - screamed "AI generated"
- No people, no personality props, no variety in surface or mood
- Everything centred and perfectly arranged

**Root cause:** The prompt rules specified objects and composition too rigidly without allowing scene-level interpretation based on post topic.

---

### Photography - Reference Analysis

Two batches of Pinterest reference images were analysed. Key findings:

**What makes photos look real vs AI-generated:**
- Imperfect light - streaks, uneven pools, one corner brighter than another
- Visible surface texture - linen weave, wood grain, fabric wrinkle
- Organic placement - objects slightly overlapping, one element partially cropped at frame edge
- Depth layers - something blurry in the foreground
- Colour imperfection - slight overexposure in brightest corner
- Human evidence - half-drunk coffee, pen rolled slightly off centre
- People present but never facing camera - back, side profile, or hands only

**Signature props identified from references:**
- Starbucks iced latte or matcha in clear cup with green straw
- Apple MacBook in silver or space grey
- Apple AirPods Max in silver or space grey
- Productivity Planner by Intelligent Change:
  - Version 1: black linen hardcover, gold foil title, yellow and grey ribbon bookmarks
  - Version 2: grey linen hardcover, silver foil title
- Matcha latte or latte in ceramic or glass cup
- Gold jewellery - rings, bracelets, gold watch or bangle
- Tortoiseshell claw clip

**People styling:**
- Female entrepreneur, face never visible
- Business outfits: oversized blazers, tailored coats, wide-leg trousers, high heels
- Hair: low bun, loose waves, or claw clip
- Hands: long gel nails in nude, white French, or deep toned. Gold jewellery always visible.

**Surfaces and interiors:**
- Dark oak wood, marble, travertine, concrete - not always cream linen
- Luxurious interiors: arched mirrors, bouclé chairs, statement desks, large windows
- Mix of light cream scenes AND dark moody chocolate brown scenes

**Film aesthetic:** Kodak Portra 400, visible grain, warm colour grading, slightly soft, not digitally sharp. 35mm or 50mm lens, shallow depth of field.

**Props removed after review:** Vogue magazine (removed as unnecessary)

---

### Photography - Validated Prompt Structure

Every photo prompt must:
1. Open with a specific topic-relevant scene (not a generic flat lay)
2. Name the surface and lighting direction explicitly
3. Include 1-2 signature props relevant to the post topic
4. Specify film aesthetic and lens
5. Describe one imperfection (cropped element, uneven light, surface texture)
6. End with the negative prompt block

**Negative prompt block (end of every photo prompt):**
```
no text, no words, no writing, no labels, no bright colours,
no gradients, no studio lighting, no stock photography look,
no digital sharpening, no visible screens with text.
```

**Strict text rules:**
- All notebooks completely blank and closed
- All screens face away or show only a dark reflection
- No readable typography on any surface

---

### Infographics - What Was Wrong Initially

First-generation infographic prompts had one fatal flaw: every post got the same horizontal alternating timeline layout regardless of content. This produced identical-looking infographics across all posts.

Secondary issues:
- Font name "Noto Serif Display Light" was rendering as visible text in the image
- Nodes were too large and dominant
- Too much unused space on one side of the canvas
- No variety in structure or visual approach

---

### Infographics - Reference Analysis (Two Batches)

**What the references share:**

- Thin hairline strokes everywhere - lines, circles, curves all single-weight
- Noto Serif Display Light for headings, Montserrat Regular for secondary text
- No dominant title - headings and subheadings only
- One accent colour used sparingly - never two competing
- Generous empty space as an intentional design choice
- Small dot or diamond ornaments as section separators only
- Background: warm cream with subtle paper texture (deep sage acceptable for Venn diagrams)
- Shape as the primary design element - the structure must match the content

**Layout variety seen in references:**
- Serpentine flow curves for journeys
- Vertical spine with alternating content for processes
- Venn diagrams for overlapping frameworks
- Radial dot maps for concept clusters
- Rounded pill lists for soft sequential items
- Two-column comparisons for contrasting ideas
- Starburst centrepieces for radiating concepts
- Pyramids for hierarchies
- Pure typography grids for word-led content
- Floating object grids for lifestyle lists

**Key principle extracted:** The layout must emerge from the content. A journey needs a curve. A list of rituals needs floating objects. A framework needs a Venn. A process needs a vertical drop. No two consecutive posts should use the same layout.

---

### Infographics - Validated Brand Colours

| Role | Hex |
|---|---|
| Background | #F8F5F2 (warm cream with paper texture) |
| Headings | #262427 (near-black) |
| Nodes and accents | #8D6E63 (chocolate brown) |
| Connecting lines and rules | #A5988E (muted sand) |
| Supporting text | #BBB0AA (warm taupe) |

---

### Infographics - Validated Typography

- Headings and main labels: Noto Serif Display Light, sentence case, light weight, never bold
- Numbers, secondary labels, supporting phrases: Montserrat Regular, lowercase or small all caps with generous letter spacing
- Never write font names as visible text in the image
- No dominant title - headings and subheadings only
- Maximum 2 font styles per infographic

---

### Infographics - Tested and Validated Layouts

**Layout 1: Serpentine Flow Curve**
Tested for "Trending products to sell online" post. Result approved.
Single thin S-curve in muted sand, small filled dots in chocolate brown at natural points, labels alternating above and below.

**Layout 2: Vertical Spine (centred, alternating)**
Tested for "E-commerce business plan" post. Multiple iterations:
- First attempt: spine on left third, too much dead space on right. Rejected.
- Second attempt: spine centred, content alternating left and right. Approved as a layout but dots still present.
- Third attempt: pure dots removed, replaced with thin short horizontal underline beneath each number. Cleaner.

**Layout 3: Pure Typography Two-Column Grid**
Tested. Clean but described as "not beautiful or interesting" - lacks a visual anchor at 16:9.

**Layout 4: Rounded Pill Grid**
Tested. Result not shared but layout added to the menu for future use.

---

### Infographics - Font Name Rendering Bug

**Problem:** When "Noto Serif Display Light" appeared in the prompt, Nano Banana Pro rendered the font name as visible text inside the headings instead of applying it as a style.

**Fix:** Replace all font name references with descriptive terms:
- "Noto Serif Display Light" → "elegant serif font" in prompts
- Added explicit instruction: "Never write font names as visible text in the image"

---

### Banned Word Handling - Simplified

Original plan was to add a second revision pass if banned words survived the first attempt. This was simplified after review:

**Current behaviour:**
- Agent checks for banned words after first draft
- If found, sends a multi-turn revision request
- If banned words survive the revision, logs them to `errors.json` and saves the post as-is
- No second revision attempt - not worth the complexity

**Persistent offenders noted:** `discover` and `imagine` are the most common survivors of the first revision pass.

---

### Final IMAGE_PROMPT_SYSTEM Structure

The constant is divided into four sections:

**1. Brand colours** - hex codes for all five brand tones, used explicitly in every prompt

**2. Brand fonts** - Noto Serif Display Light for headings, Montserrat Regular for secondary text. Never written as visible text in images.

**3. Photography rules** - scene direction by topic, people styling, signature props, surfaces and interiors, film aesthetic, strict text rules, negative prompt block

**4. Infographic rules** - 10 layout options with descriptions of when to use each, rules for all layouts, mandatory variety instruction

**Output format instruction:** Agent must state which layout it chose and why before writing the infographic prompt. Must never repeat the same layout as the previous post.

---

### Commit History (Updated)

| Commit | Message |
|---|---|
| bc7c9ac | scaffold blog-seo-agent |
| cb23bd8 | fix tier sorting and output dir on first run |
| (subsequent) | add image prompts and html output |
| 544b1be | update image prompt system with validated infographic and photography rules |
| 2880bc6 | fix infographic font name rendering and node size |
| (subsequent) | increase image prompt max_tokens to 2048 to prevent truncation |
| (subsequent) | rewrite image prompt system for topic-relevant scenes and varied infographic layouts |
| (subsequent) | rewrite full image prompt system with validated photography and varied infographic rules |
| (subsequent) | simplify banned word handling - log and continue if first revision fails |

---

*End of session summary*
