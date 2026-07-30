# Lead-gen agent — STATUS

Last updated: 2026-06-19 (one main 50/50 service+ecom batch, 312 forms submitted across the day, e-commerce intitle queries + 4 junk-filter TODOs from 2026-06-18 formalized into code and verified live)

---

## What this agent does

Cold outreach pipeline for Jane's **Pinterest strategy consulting service** (NOT branding kits/templates).
Finds small business owners who have no Pinterest presence, generates personalised outreach, sends via email or website contact form.

Target: solo coaches, consultants, service providers, small e-commerce brands.
Pitch: Pinterest strategy packages → pinterest.switzertemplates.com

---

## Daily routine — two steps

**Step 1 — "run today's outreach":**
```
python3 skills/lead-gen-agent/daily_runner.py
```
Runs: web search finder → email drafts (15) → form drafts (150) → email sender (15/day) → **preview file**.

To skip email sending (e.g. already sent today):
```
python3 skills/lead-gen-agent/daily_runner.py --skip-emails
```

Stops before form sending. Saves planned submissions to `outputs/leads/planned-forms-YYYY-MM-DD.txt` and prints the list in chat. Jane reviews, removes junk, approves.

**Step 2 — after Jane says "submit":**
```
python3 skills/lead-gen-agent/contact_form_sender.py --limit 160
```
Runs form sender against approved leads. If backlog exists (leads with form URL but no draft), run:
```
python3 skills/lead-gen-agent/outreach_generator.py --type contact-form --limit 162
python3 skills/lead-gen-agent/contact_form_sender.py --limit 162
```

---

## Pipeline stages

```
web_search_finder.py         → finds leads via Google (Serper API)
                               5 service + 5 ecommerce + 65 intitle:contact = 75 queries/run
                               intitle:contact results → contact_page_url stored directly, skip extraction
                               regular service/ecommerce queries kept for occasional snippet emails only
                               75 queries/day × 30 days = 2,250/month (within 2,500 free tier)
directory_harvester.py       → DISABLED (2026-06-16): all 4 sources blocked or JS-rendered
                               PT (React), Houzz (JS profiles), WeddingWire (blocked), Noomii (404).
                               File kept for future retry.
website_contact_extractor.py → DISABLED (2026-06-16): intitle:contact makes this redundant
                               Was: scrape websites to find email or contact URL
                               Was slow (30+ min/run), used Apify quota, lower quality than intitle leads
                               Re-enable only if a non-intitle lead source is added back
outreach_generator.py        → generates personalised draft per lead (Claude)
                               runs twice: --type email (limit 15), --type contact-form (limit 150)
email_sender.py              → sends emails via Gmail SMTP (15/day)
contact_form_sender.py       → submits contact forms via Playwright (160 attempt limit)
                               Jane reviews planned list before this runs (two-step flow)
export_contacts.py           → exports contacts-book-YYYY-MM-DD.csv (auto-runs after sending)
```

**Disabled:** Instagram finder, Etsy finder (Apify actor broken), directory harvester, website contact extractor. Only web search (intitle:contact) active.

Lead tracker CSV: `outputs/leads/lead-tracker.csv`
Sent log (append-only): `outputs/leads/sent-emails.log`
Outreach drafts: `outputs/leads/outreach-drafts/`
Manual form failures: `outputs/leads/manual-forms.csv`
Planned form previews: `outputs/leads/planned-forms-YYYY-MM-DD.txt`

---

## Current queue (as of 2026-06-19 end of day, live-verified counts)

| Stage | Count |
|-------|-------|
| Already messaged | 1,092 |
| Qualified (not yet contacted) | 855 |
| Found (no contact info yet) | 235 |
| Dead (audited out) | 720 |
| Contacts book | 2,338 (494 email, 1,844 form URL) |
| Total in tracker | 2,902 |
| Manual-forms.csv (form exists, auto-fill failed) | 93 |

---

## Contact form volume — approach

**Goal:** 100+ contact forms/day.
**Previous reality:** ~12–17 forms/day (general search + extraction).
**2026-06-16:** 64 forms submitted (35 intitle queries → 137 contact page leads → 64 successfully submitted).
**Why it was short of 100:** limit was 100 attempts. At 63% success = 63 submitted. Fixed 2026-06-17: attempt limit raised to 160 → 160 × 63% ≈ 101 submitted.

### PRIMARY APPROACH: intitle:"contact" search

Uses `intitle:"contact"` operator — Google matches the page `<title>` tag, which is page-specific, so the result URL IS the actual `/contact` page. Stored directly as `contact_page_url`, bypassing extraction entirely. Zero Apify cost per lead.

- 35 intitle queries → 137 contact page leads (first run)
- Now running **65 intitle queries/day** → expect ~250 contact page leads/day
- Form submission success rate: ~63% (64 submitted / 102 attempted)
- With 65 queries and improved form sender, target is 100+ submitted/day

### Form submission success rate — improvements added 2026-06-16

Three fixes applied to `contact_form_sender.py`:

1. **Early bail on booking-only embeds** — detects Calendly, Acuity, Setmore, YouCanBook.me etc. in page source → marks `form-failed` and skips immediately. No 45-second Playwright wait wasted.

2. **Textarea wait** — after networkidle, waits up to 5 extra seconds for `textarea` or `input[type=email]` to appear. Catches JS-rendered forms (React, Vue, Squarespace) that mount slightly after page load.

3. **iframe fallback** — if no form found in main page HTML, walks all iframes and tries to fill the form inside them. Covers HoneyBook, JotForm, Dubsado, Typeform — common tools used by coaches and wedding photographers.

**What was tried and failed:**
- `inurl:contact` — Google returns canonical/homepage URL. Reverted 2026-06-15.
- Directory harvesting (PT/Houzz/WeddingWire/Noomii) — all blocked or JS-rendered. 0 leads. Disabled 2026-06-16.
- Website contact extractor — slow, expensive, lower quality than intitle. Disabled 2026-06-16.

---

## Target niches

### Service niches (searched per city, US + UK/AU cities)
life coaching, health coaching, relationship coaching, financial coaching, mindset coaching,
therapy, business coaching, nutrition coaching, esthetics, interior design,
wedding photography, event planning, personal styling, home organizing

### E-commerce niches (no city, lower priority)
handmade jewelry, handmade skincare, handmade candles, ceramic pottery, print on demand

### Removed niches
personal trainers, florists, pilates, massage therapists, virtual assistants, copywriters,
social media managers, digital product sellers, brand consultants — removed as too competitive,
low budget, or direct competitors. Massage therapists removed 2026-06-16 (different profession
from therapy/psychology/counselling).

---

## Tools and limits

| Tool | Purpose | Limit |
|------|---------|-------|
| Serper.dev | Google search for new leads | 2,500 searches/month free. 75 queries/run = 2,250/month |
| Apify residential proxy | Website scraping (extractor — currently disabled) | ~$0.05/day when active |
| Gmail SMTP | Email sending | 500/day hard limit. Sending 15/day to avoid spam flags |
| Playwright (local) | Contact form submission | No external limit. ~45s per form. Runs on Jane's Mac |
| Anthropic API (Sonnet 4.6) | Draft generation | ~$0.01/draft. ~$2.50/day at 362 drafts. ~$75/month |

---

## Junk filtering — 4 layers

### Layer 0: Query construction (web_search_finder — before even sending to Serper)

**Exact phrase matching:** All niche terms quoted (`"life coach"` not `life coach`).

**Niche-specific extra excludes** appended per niche:
- `therapy` — `-"group practice" -"therapy center" -"mental health center" -"counseling center" -"associates"`
- `business coaching` — `-"coaching firm" -"coaching company" -"coaching group"`
- `nutrition coaching` — `-"nutrition center" -"dietitian group" -"registered dietitian center"`

**Solo-signal query templates:**
- Coaching niches (8): `"life coach" "work with me" Seattle ...`
- Therapy: `"private practice" "therapist" Seattle ...`

**Rotation queue:** `.search_state.json` — 1,357 service combos + 826 intitle combos. Each run consumes next batch from pre-shuffled queue. Reshuffles when exhausted.

### Layer 1: Serper result filtering (web_search_finder — before saving to tracker)

**`_should_skip(url)`** — expanded 2026-06-16:
- `.edu`, `.gov`, `.ac.uk`, `.ac.au`, `.ac.nz`, `.edu.au` — academic/government TLDs
- Domain contains "hospital," "rehab," "university," "college" — institutional signals
- `"directory"` anywhere in domain/subdomain — catches `directory.iaprc.org`, `findmytherapistdirectory.com` etc.
- Known junk domains in `SKIP_DOMAINS`

**`_should_skip()` additions (2026-06-17):**
- `.org` and `.coop` TLDs → always skip (nonprofits/cooperatives — not solo business owners)
- `"academy"` in domain → skip (training schools, e.g. accentbeautyacademy.com)
- `"rentals"` in domain → skip (equipment/furniture rental companies)

**`SKIP_DOMAINS` additions (2026-06-17):**
- `weebly.com` — free builder hosting; leads are generic resource sites, not real businesses
- `jobtoday.com` — job board

**`_INSTITUTIONAL_KEYWORDS` additions (2026-06-17):**
- `"group practice"`, `"group practices"` — multi-practitioner signal in snippets

**`SKIP_DOMAINS` additions (2026-06-16):**
- People/contact lookup: `rocketreach.co`, `zoominfo.com`, `radaris.com`, `spokeo.com`, `local.yahoo.com`, `prospeo.io`
- Job boards: `ziprecruiter.com`, `monster.com`, `careerbuilder.com`
- Big chains: `daveandbusters.com`, `greatwolf.com`, `headspace.com`
- Media/magazines: `homestolove.com.au`, `womenshealthmag.com`, `scribd.com`, `yumpu.com`
- Event venues: `denverconvention.com`
- Room rental (not therapists): `roomsfortherapists.co.uk`
- Near-me directories: `nutritionistnear.me`, `findmytherapistdirectory.com`

**Directory URL path filter** — `_is_directory_url()` checks exact path segments.

**Listicle/aggregator title filter** — `_is_listicle_title()` skips digit-start titles and aggregator phrases.

**Google Places snippet filter** — `_is_places_snippet()` detects GMB results (2+ middle dots + hours/reviews).

**Institutional keyword filter** (title + snippet):
- Hospitals, medical centers, health systems, universities, nonprofits, chains
- Multi-practitioner signals: "our team of," "our therapists," "our coaches," etc.

**URL normalisation:**
- Blog/article path (`/blog/`, `/news/`, `/journal/`, etc.) → strip to homepage
- Product/shop path → strip to homepage
- Shopify tracking param (`srsltid=`) → strip to homepage

### Layer 2: Extractor filtering — CURRENTLY DISABLED

Was: Apify scraping with lightweight pre-check, Wix detection, `_has_contact_form()` verification. Re-enable if extractor is turned back on.

### Layer 3: Lead tracker filtering (lead_tracker.py)
- `_is_sendable_email()` — blocks bad prefixes (noreply, support, admin, etc.) and platform domains
- Dead/messaged/paid leads excluded

### Layer 4: Pre-send filtering (email_sender + contact_form_sender)
- `_is_sendable_email()` runs again before every email
- `_is_bad_contact_domain()` runs before every form submit
- Sent log deduplication — never contacts same address twice
- `form-failed` in notes → auto-skipped

---

## Deduplication

`append_leads()` in lead_tracker.py deduplicates by: `etsy_url`, `instagram_handle`, `contact_email`, `website`.

---

## Outreach — email (3 rotating templates)

All templates share: personalised opener (Claude-generated), Jane's social proof (28,000+ sales), link to pinterest.switzertemplates.com, free guide link. No price mentioned. Subject line from pool of 50+ variants.

Greeting: "Hi {FirstName}," extracted in priority order:
1. `owner_name` field
2. Email prefix if it looks like a real name
3. "byName" pattern in prefix (e.g. `aestheticsbyeimear@` → Eimear)
4. Domain root starting with a known first name
5. CamelCase business name (first word only)
Falls back to "Hi," if none found.

## Outreach — contact form (1 template)

Same structure as email but shorter — no subject, adapted for a contact box.
Draft files: `{lead_id}-{business}-contact-form.txt`

## Niche angles — all covered

All 15 service niches + 5 e-commerce niches have specific Pinterest reasoning in `NICHE_ANGLES` dict in `outreach_generator.py`. None fall back to `FALLBACK_ANGLE`.

---

## Contact form sender — technical notes

- `requestSubmit()` for form submission — bypasses newsletter overlays
- `navigator.webdriver` hidden — reduces Cloudflare bot detection
- `networkidle` wait after `domcontentloaded` — gives JS-rendered forms time to mount
- Extra wait for `textarea`/`input[type=email]` after networkidle (added 2026-06-16)
- reCAPTCHA fields skipped
- JS eval fallback for hidden/framework-managed fields (HighLevel/msgsndr)
- iframe fallback — tries all iframes if no form found in main page (added 2026-06-16)
- Booking-only embeds (Calendly, Acuity etc.) detected and bailed early (added 2026-06-16)
- Failed leads marked `form-failed` in notes → auto-skipped on future runs
- Type 1 failure (no form found) → `form-failed` flag only
- Type 2 failure (form found, couldn't fill) → added to `manual-forms.csv` + `form-failed` flag

---

## Full pipeline run results

### 2026-06-19 (one main 50/50 service+ecom batch, plus two smaller batches)

**Batch 1 (service-based, earlier in session):**

| Step | Result |
|------|--------|
| Quality audit | removed 12 junk |
| Clean leads | 63 |
| Forms submitted | 63 |

**Batch 2 (ecommerce/POD):**

| Step | Result |
|------|--------|
| Quality audit | junk/borderline removed |
| Clean leads | 32 |
| Forms submitted | 32 |

**Code formalization session (no new leads — see "Changes made 2026-06-19" below):**
Implemented the 4 TODOs flagged in the 2026-06-18 STATUS.md entry as real code in `web_search_finder.py`. Verified live, found and fixed 2 real bugs during testing (`siematic` substring vs domain, `dermaswissinstitute.com` not caught by `dermatology` alone).

**Batch 3 — main 50/50 service+ecommerce/POD batch (target: 100+ submissions):**

| Step | Result |
|------|--------|
| Finder round 1 (service + ecom intitle) | 353 new leads |
| Quality audit round 1 | 39 removed (23 + 16, junk/borderline) |
| Finder round 2 — top-up (fresh ecom intitle phrasing, formalized 20-query pool already exhausted from earlier ad-hoc use today) | 36 new leads |
| Quality audit round 2 | 3 removed (junk/borderline) |
| Clean leads (combined) | 347 (314 + 33) |
| Forms attempted | 347 |
| Forms submitted | **217** |
| Manual-forms.csv (form exists, fill failed) | 16 |
| No form found at all | 114 |

**Day total:**

| Metric | Count |
|--------|-------|
| New leads found | 353 + 36 = 389 |
| Leads removed in quality audits | 12 + (32-batch junk, count folded into batch) + 39 + 3 = 54+ (exact batch-2 junk count not logged separately this session) |
| Forms submitted | **312** (63 + 32 + 217) |
| Total messaged to date | 1,092 |

### 2026-06-18 (four batches — mandatory pre-send quality audit introduced)

Jane's standing rule from this session onward: **every batch of contact-form leads must be manually quality-audited against known junk patterns before drafts are generated and before any form is sent — every single time, not just occasionally.** See [[feedback_quality_check_before_form_send]] in agent memory.

**Batch 1 — backlog (37 forms, no new audit needed, pre-existing drafts):**

| Step | Result |
|------|--------|
| Forms attempted | 63 |
| Forms submitted | 37 |

**Batch 2 — service niches only (intitle_sample=65):**

| Step | Result |
|------|--------|
| Finder (65 intitle queries) | 222 new leads |
| Quality audit | 32 removed (directory listing pages, medspas, wrong business type, wrong region) |
| Clean leads | 190 |
| Forms submitted | 111 / 190 attempted |

**Batch 3 — first e-commerce/POD-specific run:**

No e-commerce intitle query pool existed in the codebase (only the 14 service niches had one — see "E-commerce intitle queries" below). Built one ad-hoc (not yet merged into `web_search_finder.py`).

| Step | Result |
|------|--------|
| Finder (10 ad-hoc e-commerce intitle queries) | 44 new leads |
| Quality audit | 12 removed (marketplace platforms, B2B fulfillment suppliers, theme demo sites, news articles) |
| Clean leads | 32 |
| Forms submitted | 18 / 32 attempted |

**Batch 4 — combined top-up (50/50 service + e-commerce, target 100+ submissions):**

| Step | Result |
|------|--------|
| Finder round 1 (35 service intitle + 20 e-commerce intitle) | 113 + 40 = 153 new leads |
| Quality audit round 1 | 24 removed (15 high-confidence + 9 borderline) |
| Finder round 2 — top-up (20 service intitle + 10 e-commerce intitle) | 80 + 39 = 119 new leads |
| Quality audit round 2 | 13 removed (11 high-confidence + 2 borderline) |
| Clean leads (both rounds combined) | 235 |
| Forms submitted | 150 / 235 attempted |

**Day total:**

| Metric | Count |
|--------|-------|
| New leads found | 222 + 44 + 153 + 119 = 538 |
| Leads removed in quality audits | 32 + 12 + 24 + 13 = 81 |
| Forms submitted | **316** (37 + 111 + 18 + 150) |
| Total messaged to date | 875 |

### 2026-06-17 (two sessions)

**Session 1 (backlog + new leads):**

| Step | Result |
|------|--------|
| Finder (75 queries: 5 service + 5 ecom + 65 intitle) | new leads added to tracker |
| Email drafts generated | 15 |
| Emails sent | 15 |
| Contact form drafts generated | 150 + 162 (backlog batch) |
| Forms attempted (batch 1) | 132 |
| Forms submitted (batch 1) | 71 |
| Forms attempted (batch 2 — backlog) | 162 |
| Forms submitted (batch 2 — backlog) | 101 |
| Subtotal forms | 172 |

**Session 2 (new leads — this session):**

| Step | Result |
|------|--------|
| Finder (75 queries: 5 service + 5 ecom + 65 intitle) | 242 new leads (1 email snippet, 233 contact page direct) |
| Email drafts generated | 0 (skip-emails not yet added; 14 emails sent before flag could be applied) |
| Emails sent | 14 (went out before --skip-emails flag was available) |
| Contact form drafts generated | 150 |
| Manual junk review: leads removed | 26 (glassdoor.com.br, jobilize.com, poughkeepsiejournal.com, wellness.atlanticpkg.com, investors.jcrew.com, paulamorrisoninteriors.com, leverlaw.com, crystaleyebrows.com, glossgenius.com pages × 3, therapynext.com, lifecoachingcertification.net, purefinancial.com, altadenacare.com, millerfamilycare.com, marcdliangmd.com, cosmeticlasercenters.com, acmdesignarchitects.com, logicwealthmanagement.com, prnhealthservices.com, peacefulhopehpc.com, integratingcancernutrition.com, cobbconvention.com, movementbank.com, reswellhealth.com, lifecoachmedia.com, lifecoachcharlotte.be) |
| Forms attempted (session 2) | 126 |
| Forms submitted (session 2) | 81 |

**Day total:**

| Metric | Count |
|--------|-------|
| New leads found | 242 |
| Emails sent | 29 (15 session 1 + 14 session 2) |
| Forms submitted | **253** (172 + 81) |
| Total messaged to date | 461 |

### 2026-06-16 (first intitle:contact run)

| Step | Result |
|------|--------|
| Finder (75 queries: 5 service + 5 ecom + 35 intitle) | 167 new leads (1 email snippet, 137 contact page direct) |
| Directory harvester | 0 (all sources blocked/JS — disabled) |
| Extraction | 132 leads processed (now disabled) |
| Email drafts generated | 50 |
| Emails sent | 14 |
| Contact form drafts generated | 100 |
| Forms attempted | 102 |
| Forms submitted | 64 |
| Total messaged today | 78 |
| Contacts book | 912 (494 email, 418 form URL) |

### 2026-06-15 (baseline before intitle)

| Step | Result |
|------|--------|
| Finder (40 queries) | 183 new leads |
| Extraction | 189/276 leads updated |
| Emails sent | 14 |
| Forms submitted | 12 |
| Total messaged | 26 |

---

## Changes made 2026-06-19

### Formalized all 4 TODOs from the 2026-06-18 "Known remaining issues" list into `web_search_finder.py`
- **`ECOM_INTITLE_QUERIES`** — 20 curated intitle:"contact" queries across the 5 e-commerce/POD niches (handmade jewelry, handmade skincare, handmade candles, ceramic pottery, print on demand), placed after `INTITLE_QUERIES`. `run()` signature now `run(service_sample=20, ecommerce_sample=5, intitle_sample=10, ecom_intitle_sample=0)` — new param defaults to `0` so existing `daily_runner.py` calls are unaffected unless explicitly passed.
- **`_is_directory_connect_path()`** — new helper, flags any contact URL whose path ends in `/connect` with 2+ path segments (directory-profile signature). A bare single-segment `/connect` (e.g. `alfredtang.com/connect`, a business's own contact page) is correctly NOT flagged. Wired into the merged service+ecom intitle loop.
- **`SKIP_DOMAINS` additions:** `goldsupplier.com`, `decoratingden.com`, `researchgate.net`, `medium.com`, `harutheme.com`, `seattlerefined.com`, `seek.com`.
- **`_DOMAIN_SIGNALS` additions:** `actioncoach`, `siematic`, `medspa`, `dermatology`, `plasticsurgery`, `institute`.
- **Bugs found and fixed during live verification (not just unit-level reasoning):**
  - `siematic.com` was first added to `SKIP_DOMAINS`, but the real-world domain was `siematic-boston.com` (not a subdomain) — moved to `_DOMAIN_SIGNALS` as a substring check instead.
  - `dermatology` substring didn't catch `dermaswissinstitute.com` — added `institute` as its own broader `_DOMAIN_SIGNALS` entry (consistent with the existing `_INSTITUTIONAL_KEYWORDS` treatment of "institute" in titles/snippets).
- Confirmed no false positives on known-good leads (juliawalther.com, atxaesthetician.com) during testing.

### E-commerce intitle query pool exhaustion observed
Running the new 20-query `ECOM_INTITLE_QUERIES` pool a second time same-day (it had already been used ad-hoc earlier) produced only 9 new leads due to heavy dedup — far short of the ~40 expected from a fresh pool. True 50/50 service/ecom split isn't achievable within a single day once the small 20-query pool is exhausted; the main batch ended up ~97% service / ~3% ecom before a manual top-up with entirely fresh (non-pool) query phrasing recovered 36 more ecom leads. Worth a larger ecom intitle pool (40-60 queries) if daily 50/50 splits become a recurring ask.

## Changes made 2026-06-18

### Mandatory pre-send quality audit (process change, not code)
From now on, every batch of contact-form leads gets manually checked against known junk patterns before drafts/sending — not just spot-checked occasionally. This applies even to small batches. See [[feedback_quality_check_before_form_send]].

### E-commerce/POD intitle queries — formalized into code (2026-06-18, later same day)
`web_search_finder.py`'s `_build_intitle_queries()` only covered the 14 service niches. Added `ECOM_INTITLE_QUERIES` (20 curated queries across the 5 e-commerce/POD niches, no city loop) directly in the file, wired into `run()` behind a new `ecom_intitle_sample` param (default `0` — opt-in, doesn't change existing `daily_runner.py` behavior unless explicitly passed). Service and e-commerce intitle queries are merged into the same processing loop. Gets its own rotation queue (`ecom_intitle_queue` in `.search_state.json`) — much smaller pool (20 vs 826) so it cycles/reshuffles far more often. Call with e.g. `web_search_finder.run(service_sample=0, ecommerce_sample=0, intitle_sample=0, ecom_intitle_sample=20)` for an e-commerce-only run.

### New junk patterns — coded as filters in `web_search_finder.py` (2026-06-18)
- **Directory platform `/connect` signature** — new `_is_directory_connect_path()` flags any contact URL ending in `/connect` with 2+ path segments (catches both the long `/region/city/niche/name/connect` form and the short `/name/connect` form, e.g. catholictherapists.com). A bare single-segment `/connect` (a solo site's own contact page, e.g. alfredtang.com/connect) is correctly NOT flagged. Wired into the merged intitle loop. Confirmed across inclusivetherapists.com, physicaltherapynearme.co, ukihca.com, serviceprospot.com, longbeachbiz.com, catholictherapists.com, quokkahub.com.au, atozhealthguide.com, lifewellness.com.
- **`SKIP_DOMAINS` additions:** `goldsupplier.com` (B2B wholesale supplier platform), `decoratingden.com` (interior design franchise), `researchgate.net` + `medium.com` (content/academic platforms, never a business's own site), `harutheme.com` (WordPress theme vendor demo sites), `seattlerefined.com` (local lifestyle media outlet), `seek.com` (job board, alongside existing `seek.com.au`).
- **`_DOMAIN_SIGNALS` additions (substring match, not exact domain):** `actioncoach` (franchise — domain varies per location), `siematic` (kitchen manufacturer showroom — note this needed a substring match, not `SKIP_DOMAINS`, since real domains are like `siematic-boston.com`), `medspa`, `dermatology`, `plasticsurgery`, `institute` (medical/institutional overlap not caught by other filters — `institute` is broad but consistent with the existing title/snippet `_INSTITUTIONAL_KEYWORDS` treatment).
- **Not coded (too broad / low confidence, still manual):** "clinic" alone isn't reliable (many solo estheticians legitimately use it); "recovery" alone risks false positives on wellness branding; wrong-niche slippage from loose OR-based e-commerce queries (a doula site matched a skincare query) is a query-design issue, not a filterable pattern.

## Changes made 2026-06-17

### Limits raised (daily_runner.py) — session 1
- Email draft generation: 50 → 15 (we only send 15/day, no point generating more)
- Contact-form draft generation: 100 → 150
- Form sender attempt limit: 100 → 160
- Result: 172 forms submitted in session 1 vs 64 the day before

### --skip-emails flag added (daily_runner.py) — session 2
- `python3 daily_runner.py --skip-emails` skips email draft generation and email sending entirely
- Use on days when emails have already been sent or you only want forms
- Skips both outreach_generator (email) and email_sender steps

### Junk filters added (web_search_finder.py) — session 1
- `.org` and `.coop` TLDs → always skip (nonprofits, cooperatives)
- `"academy"` in domain → skip (training schools)
- `"rentals"` in domain → skip (equipment/furniture rental companies)
- `weebly.com` → added to SKIP_DOMAINS (free site builder, generic resource sites)
- `jobtoday.com` → added to SKIP_DOMAINS (job board)
- `"group practice"` / `"group practices"` → added to `_INSTITUTIONAL_KEYWORDS` (snippet filter)

### Manual junk removals — session 1 (31 leads)
Removed: academies, nonprofits (.org), cooperatives (.coop), franchises (TAB), job boards,
large corporate firms, teen coaching, Yelp results pages, male coaches, design schools,
therapy platform profiles, physical therapy, sports massage.

### Manual junk removals — session 2 (26 leads)
Full quality audit of planned form list. Removed:
- **Job boards / news sites:** glassdoor.com.br, jobilize.com, poughkeepsiejournal.com
- **Booking platforms:** studiosphynx.glossgenius.com + 2 other glossgenius.com pages
- **Medical practices / clinics:** altadenacare.com, millerfamilycare.com, marcdliangmd.com, cosmeticlasercenters.com, prnhealthservices.com, peacefulhopehpc.com (hospice), integratingcancernutrition.com (oncology)
- **Large firms / wrong type:** purefinancial.com (major financial advisory firm), logicwealthmanagement.com (wealth management), acmdesignarchitects.com (architecture firm), movementbank.com (bank), cobbconvention.com (convention centre)
- **Directory profile (not their site):** therapynext.com (pid= in URL = directory listing)
- **Training program (not a coach):** lifecoachingcertification.net
- **Wrong region:** lifecoachcharlotte.be (Belgium .be TLD, outside US/UK/AU)
- **Misclassified / wrong niche:** crystaleyebrows.com (eyebrow studio classed as financial coaching), leverlaw.com (law firm), paulamorrisoninteriors.com (blog post URL not contact page)
- **Inactive / bad URL:** wellness.atlanticpkg.com (PDF link), investors.jcrew.com (J.Crew investor relations), reswellhealth.com (unclear if clinic or coach), lifecoachmedia.com (dead static HTML site)

### Junk patterns identified for future filter consideration
These patterns keep appearing and could be added to web_search_finder.py:
- `"glossgenius.com"` → SKIP_DOMAINS (booking platform, not a contact form)
- `"convention"` in domain → skip (event venues, not event planners)
- `"wealthmanagement"` in domain → skip (financial firms, not coaches)
- `"certification"` in domain → skip (training programs, not practitioners)
- `.be` TLD → skip (Belgium, outside target markets)

---

## Known remaining issues

- **Form success rate** ~58-64% (varies by batch/niche mix) — improved with iframe + textarea wait + booking bail, but JS-heavy forms (Pixieset for photographers) still fail
- **Wedding photographer niche** — many use Pixieset or HoneyBook embedded galleries, lower form success rate vs other niches
- **Therapist / nutrition niche** — highest junk risk: medical clinics, multi-practice groups, and clinical specialists slip through. Now improved with .org filter and group practice keyword, but still requires manual review each day
- **Medical niche overlap** — nutritionists, estheticians, and health coaches can overlap with medical clinics. `medspa`/`dermatology`/`plasticsurgery`/`institute` now filtered automatically (2026-06-18); "OB," "peds," generic "MD" suffix, and "recovery" (addiction treatment) still require manual catch — too easy to false-positive if added as broad domain signals
- **Directory profile pages** — `/connect` signature now filtered automatically (`_is_directory_connect_path()`, 2026-06-18). Other directory path patterns (e.g. `/experts/`) still manual-only
- **Mandatory pre-send audit** — hard rule every batch (see [[feedback_quality_check_before_form_send]]), still mostly manual. The 2026-06-18/19 code changes (directory `/connect`, new `SKIP_DOMAINS`/`_DOMAIN_SIGNALS` entries) reduce the junk rate but full automation isn't realistic — new junk patterns keep appearing each session
- **E-commerce quality** — comparable junk rate to service niches once audited (not lower priority as previously assumed); loose OR-based queries pull in more wrong-niche slippage than exact-phrase service queries
- **E-commerce intitle pool is small (20 queries)** — exhausts fast under same-day reuse (2026-06-19: second run same day returned only 9 new leads vs ~40 expected). True 50/50 service/ecom daily splits aren't reliably achievable until the pool is expanded to 40-60 queries
- **Apify Etsy actor** — broken, not used

---

## API keys (all in .env)

- `ANTHROPIC_API_KEY` — Claude API
- `APIFY_API_KEY` + `APIFY_PROXY_PASSWORD` — Apify scraping proxy (not currently used)
- `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD` — email sending
- `SERPER_API_KEY` — Google search for leads
- `TAILWIND_API_KEY` — not used by lead-gen agent
- `HUNTER_API_KEY` — email enrichment (disabled, only 25/month free)
