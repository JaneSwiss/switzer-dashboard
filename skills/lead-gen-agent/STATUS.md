# Lead-gen agent — STATUS

Last updated: 2026-06-14

---

## What this agent does

Cold outreach pipeline for Jane's **Pinterest strategy consulting service** (NOT branding kits/templates).
Finds small business owners who have no Pinterest presence, generates personalised outreach, sends via email or website contact form.

Target: solo coaches, consultants, service providers, small e-commerce brands.
Pitch: Pinterest strategy packages → pinterest.switzertemplates.com

---

## Daily routine (just tell me "send today's outreach" and I run all of this)

1. Send emails to leads with direct email addresses (limit 15–20/day)
2. Submit contact forms to leads without email addresses (limit 20–30/day)
3. If queue is running low: run extractor on next batch, then generate drafts
4. If extractor queue is also low: run web_search_finder first to add new leads

---

## Pipeline stages

```
web_search_finder.py         → finds new leads via Google (Serper API)
website_contact_extractor.py → scrapes websites to find email or contact URL
outreach_generator.py        → generates personalised draft per lead (Claude)
email_sender.py              → sends emails via Gmail SMTP
contact_form_sender.py       → submits contact forms via Playwright (headless Chrome)
export_contacts.py           → exports contacts-book-YYYY-MM-DD.csv (auto-runs after sending)
```

Lead tracker CSV: `outputs/leads/lead-tracker.csv`
Sent log (append-only): `outputs/leads/sent-emails.log`
Outreach drafts: `outputs/leads/outreach-drafts/`
Manual form failures: `outputs/leads/manual-forms.csv`

---

## Contacts book

Permanent, dated CSV of all qualified leads. Re-generated automatically after every send run.

File pattern: `outputs/leads/contacts-book-YYYY-MM-DD.csv`
Script: `python3 skills/lead-gen-agent/export_contacts.py`

Columns: business_name, owner_name, niche, website, email, contact_form_url, source, messaged, date_messaged, response

**As of 2026-06-14:** 482 contacts — 172 messaged, 310 not yet contacted, 302 have email, 180 have contact form URL.

---

## Current queue (as of 2026-06-14)

| Stage | Count |
|-------|-------|
| Already messaged | ~172 |
| Ready to email (have email + draft, not sent) | ~130 |
| Ready for contact form (have URL + draft) | ~5 |
| Need extraction (have website, no contact info) | ~249 |
| Need outreach draft generated | ~200 |
| Total in tracker | ~978 |

---

## Target niches

### Service niches (searched per city, US + UK/AU cities)
life coaching, health coaching, relationship coaching, financial coaching, mindset coaching,
therapy, business coaching, nutrition coaching, esthetics, interior design,
wedding photography, event planning, massage therapy, personal styling, home organizing

### E-commerce niches (no city, lower priority)
handmade jewelry, handmade skincare, handmade candles, ceramic pottery, print on demand

### Removed niches
personal trainers, florists, pilates, virtual assistants, copywriters, social media managers,
digital product sellers, brand consultants — removed as too competitive, low budget, or direct competitors

---

## Tools and limits

| Tool | Purpose | Limit |
|------|---------|-------|
| Serper.dev | Google search for new leads | 2,500 searches/month free. Each run uses ~6–25 queries |
| Apify residential proxy | Website scraping (extractor only) | ~$0.05/day at current pace |
| Gmail SMTP | Email sending | 500/day hard limit. Sending 15–20/day |
| Playwright (local) | Contact form submission | No external limit. ~45s per form. Runs on Jane's Mac |
| Anthropic API (Sonnet 4.6) | Draft generation | ~$0.01/draft |

---

## Junk filtering — 4 layers

### Layer 1: Serper result filtering (web_search_finder — before saving to tracker)

**Institutional keyword filter** (checks title + snippet):
- Hospitals, medical centers, health systems, rehab centers
- Universities, colleges, schools
- Foundations, institutes, nonprofits, food banks
- YMCAs, JCCs, churches, councils
- Chains and franchises (Massage Envy, Hand and Stone, etc.)
- Multi-practitioner signals: "& associates," "counseling center," "therapy center," "mental health center," "behavioral health," "family services," "coaching firm," "coaching team," "design group," "design firm," "design studio team," "& partners"

**Domain-level signals** (checked in `_should_skip()`):
- `.edu`, `.gov` — always skipped
- Domain contains "hospital," "rehab," "university," "college" — skipped
- Known junk domains in `SKIP_DOMAINS` (Yelp, directories, booking platforms, etc.)

**URL normalisation** (keeps the lead, fixes the URL):
- Blog/article path (`/blog/`, `/news/`, `/journal/`, etc.) → strip to homepage
- Product/shop path (`/shop`, `/collections`, `/products`) → strip to homepage
- Shopify Google Shopping tracking param (`srsltid=`) → strip to homepage

**Snippet email extraction** (bonus — no fetch needed):
- Sendable email in Serper snippet → lead marked qualified, skips extraction entirely

**Service query excludes** (appended to every city-based query):
`-site:yelp.com -site:psychologytoday.com -site:thumbtack.com -site:bark.com -site:zocdoc.com -site:healthgrades.com -site:betterhelp.com -site:theknot.com -site:weddingwire.com`

### Layer 2: Extractor filtering (website_contact_extractor)
- `SKIP_WEBSITE_DOMAINS` — non-business domains cleared before fetching
- `_BAD_EMAIL_DOMAINS` — known platform/directory domains filtered from extracted emails
- Wix sites detected → skip contact form path (forms are JS-only, can't be submitted)
- `_has_contact_form()` — contact page URL only stored if real fillable form found in static HTML
- E-commerce leads already on Pinterest → marked dead, skipped
- Homepage returns 403/401/429 (BLOCKED) → bail on whole domain immediately, skip all paths

### Layer 3: Lead tracker filtering (lead_tracker.py)
- `_is_sendable_email()` — blocks bad prefixes and known platform domains
- Bad prefixes: hiring, jobs, noreply, board, support, billing, frontdesk, admin, reception, customercare, intake, concierge, enquiries, feedback, press, media, partnerships, wholesale, orders
- `mysite.com` blocked (placeholder domain)
- Dead/messaged/paid leads excluded from extraction queue

### Layer 4: Pre-send filtering (email_sender + contact_form_sender)
- `_is_sendable_email()` runs again before every email send
- `_is_bad_contact_domain()` runs before every form submit
- Sent log deduplication — never emails the same address twice
- `form-failed` in notes → auto-skipped by contact form sender

---

## Deduplication

`append_leads()` in lead_tracker.py deduplicates by:
- `etsy_url` — Etsy shop URL
- `instagram_handle` — Instagram handle
- `contact_email` — email address
- `website` — website URL ← added this session (prevents same site being added twice from multiple finder runs)

---

## Outreach — email (3 rotating templates)

All templates share: personalised opener (Claude-generated), Jane's social proof (28,000+ sales), link to pinterest.switzertemplates.com, free guide link. No price mentioned. Subject line from pool of 50+ variants.

Greeting: "Hi {FirstName}," extracted in priority order:
1. `owner_name` field (set by scraper)
2. Email prefix if it looks like a real name (e.g. `elissa@...` → Elissa)
3. "byName" pattern in prefix (e.g. `aestheticsbyeimear@` → Eimear)
4. Domain root starting with a known first name (e.g. `info@amyvermillion.com` → Amy)
5. CamelCase business name (first word only, if in known names list)
Falls back to "Hi," if none found.

## Outreach — contact form (1 template)

Same structure as email but shorter — no subject, adapted for a contact box.
Draft files: `{lead_id}-{business}-contact-form.txt`

## Niche angles — all covered

All 15 service niches + 5 e-commerce niches have specific Pinterest reasoning in `NICHE_ANGLES` dict in `outreach_generator.py`. None fall back to `FALLBACK_ANGLE`.

New niches added this session: health coaching, relationship coaching, financial coaching, mindset coaching, personal styling, home organizing.

---

## Contact form sender — technical notes

- `requestSubmit()` for form submission — bypasses newsletter overlays
- `navigator.webdriver` hidden — reduces Cloudflare bot detection
- `networkidle` wait after `domcontentloaded` — gives JS-rendered forms time to mount
- reCAPTCHA fields skipped
- JS eval fallback for hidden/framework-managed fields (HighLevel/msgsndr)
- Failed leads marked `form-failed` in notes → auto-skipped on future runs
- Type 1 failure (no form found) → `form-failed` flag only
- Type 2 failure (form found, couldn't fill) → added to `manual-forms.csv` + `form-failed` flag

---

## A-to-Z test results (2026-06-14)

Ran a full pipeline test on a small batch to verify efficiency:

| Step | Result |
|------|--------|
| Finder (6 queries) | 33 new leads added |
| Extraction (33 leads, ~12 min) | 26/33 contactable (79%) |
| Drafts generated | 22 |
| Emails sent | 5 (all personal-name inboxes) |
| Forms submitted | 4 |
| Total messaged | 9 from 33 leads (27%) |

Main finding: 79% contactable rate confirms filtering improvements are working. Remaining issue is that some service queries (nutritionist) returned institutional results — fixed with institutional keyword filter on titles/snippets.

---

## Known remaining issues

- **Massage Envy, chains** in massage therapist search — caught by institutional filter now
- **Therapist niche** is highest junk risk (many multi-therapist practices have solo-looking websites) — monitor quality
- **E-commerce quality** is lower than service niches — acceptable as lower priority
- **Contact form success rate** varies (~40–60% of attempts succeed) — Playwright limitation for JS-heavy forms
- **Apify Etsy actor** — broken, not used. Google search works fine as replacement

---

## API keys (all in .env)

- `ANTHROPIC_API_KEY` — Claude API
- `APIFY_API_KEY` + `APIFY_PROXY_PASSWORD` — Apify scraping proxy
- `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD` — email sending
- `SERPER_API_KEY` — Google search for leads
- `TAILWIND_API_KEY` — not used by lead-gen agent
- `HUNTER_API_KEY` — email enrichment (disabled, only 25/month free)
