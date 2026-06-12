# Lead-gen agent — STATUS

Last updated: 2026-06-12

---

## What this agent does

Cold outreach pipeline for Jane's **Pinterest strategy consulting service** (NOT branding kits/templates).
Finds small business owners who have no Pinterest presence, generates personalised outreach, sends via email or website contact form.

Target: any small business owner (product sellers, coaches, service businesses — all valid).
Pitch: Pinterest strategy packages → pinterest.switzertemplates.com

---

## Daily routine (just tell me "send today's outreach" and I run all of this)

1. Send 15–50 emails to leads with direct email addresses
2. Submit as many contact forms as possible to leads without email addresses
3. If queue is running low: extract contact info from the next batch of leads, then generate drafts

---

## Pipeline stages

```
web_search_finder.py         → finds new leads via Google (Serper API)
website_contact_extractor.py → scrapes websites to find email or contact URL
outreach_generator.py        → generates personalised draft per lead (Claude)
email_sender.py              → sends emails via Gmail SMTP
contact_form_sender.py       → submits contact forms via Playwright (headless Chrome)
```

Lead tracker CSV: `outputs/leads/lead-tracker.csv`
Sent log (append-only): `outputs/leads/sent-emails.log`
Outreach drafts: `outputs/leads/outreach-drafts/`

---

## Contacts book

Permanent, human-readable record of all qualified leads. Open in Google Sheets.

File: `outputs/leads/contacts-book.csv`
Script: `python3 skills/lead-gen-agent/export_contacts.py`

Columns: business_name, owner_name, niche, website, email, contact_form_url, source, messaged, date_messaged, response

Re-run this script at the end of each session to keep the file current.

**As of 2026-06-12:** 431 contacts — 158 messaged, 273 not yet contacted, 264 have email, 167 have contact form URL.

---

## Current queue (as of 2026-06-12)

| Stage | Count |
|-------|-------|
| Ready to email (have email, not sent) | ~151 |
| Ready for contact form (have URL + draft) | ~17 |
| Have contact URL but need draft generated | ~22 |
| Need contact extraction from website | ~332 |
| Already messaged | ~178 |
| Total in tracker | ~945 |

---

## Tools and limits

| Tool | Purpose | Limit |
|------|---------|-------|
| Serper.dev | Google search for new leads | 2,500 searches/month free. Each run = ~250. Run 2–3x/week to stay free |
| Apify residential proxy | Website scraping (contact extractor only) | $8/GB. ~$0.05/day at current pace. Plan: $29/month, $13 spent |
| Gmail SMTP | Email sending | 500/day hard limit. Currently sending 15–50/day |
| Playwright (local) | Contact form submission | No external limit. ~45s per attempt. Runs on Jane's Mac |
| Anthropic API (Sonnet 4.6) | Outreach draft generation | ~$0.01/draft. 50 drafts/day ≈ $0.50/day |
| Hunter.io | Email enrichment from domains | 25 searches/month free. Currently disabled (HUNTER_ENRICHER_ENABLED=false) |

**Total daily cost at full scale: ~$0.25–$0.62/day (~$7–20/month)**

---

## What's working

- **Email sending** — reliable. Gmail SMTP, App Password auth. Duplicate prevention via append-only sent-emails.log
- **Contact form submission** — works for Shopify, WordPress, standard HTML forms (~25% success rate across all attempts)
- **Lead finding** — web_search_finder.py uses Serper (Google) across 19 niches × 47 locations
- **Draft generation** — personalised opener + body via Claude. Greeting extracts first name from owner_name, email prefix, or business name

## What doesn't work / known issues

- **Etsy actor (Apify)** — broken, returns 0 results. Switched to Google search for Etsy-type product sellers
- **Contact forms with iframes** — Typeform, JotForm, Calendly embedded forms can't be filled (not in main DOM). These get `form-failed` flag and are auto-skipped
- **Heavy Cloudflare sites** — some sites block headless Playwright even with webdriver flag hidden. Auto-skipped after failure
- **HighLevel/msgsndr forms** — hidden modal forms. Some now work via JS eval fallback
- **Hunter.io enricher** — disabled. Only 25 free/month, not worth enabling until paid plan
- **Apify Etsy actor** — actor ID 7uBnuXg56t3U0h5Nl needs shop name extraction fix (shop names buried in listing URLs). Not worth fixing — Google search works fine

---

## Junk filtering (3 layers)

1. **Entry (web_search_finder)** — `SKIP_DOMAINS` blocks directories, chains, booking platforms before leads enter tracker
2. **Pre-scrape (website_contact_extractor)** — `_BAD_EMAIL_DOMAINS` skips known bad sites before fetching
3. **Pre-send (email_sender + contact_form_sender)** — `_is_sendable_email()` blocks generic inboxes (admin@, reception@, etc.) and known platform domains

### Bad email prefixes (skip these inboxes)
hiring, jobs, recruitment, careers, noreply, no-reply, board, support, billing, frontdesk, admin, reception, customercare, clientconnect, intake, concierge, studio, enquiries, enquiry, comments, feedback, press, media, partnerships, wholesale, orders

---

## Outreach message (current template)

```
{greeting}

{opener} I noticed you don't have a Pinterest presence — which is worth looking into for your type of business.

My name is Jane. I work with business owners to build Pinterest strategies that drive consistent, long-term traffic to their websites. I also run Switzer Templates (28,000+ sales), and Pinterest is my main traffic driver.

I offer two packages tailored to your niche: https://pinterest.switzertemplates.com/ Each includes a full audit and a strategy built around what's actually working in your industry.

There's also a free Pinterest starter guide here if you want to explore first: switzertemplates.myflodesk.com/pinterest-guidebook

Happy to answer any questions.

Regards,
Jane
```

Greeting: "Hi {FirstName}," — extracted from owner_name → email prefix → domain root → CamelCase business name (first word only if in known first names list). Falls back to "Hi," if no name found.

---

## Contact form sender — technical notes

File: `contact_form_sender.py`

Key fixes applied 2026-06-12:
- `state="attached"` in wait_for_selector (was "visible" — caused forms below fold to time out)
- `requestSubmit()` for form submission — bypasses newsletter popup overlays
- `navigator.webdriver` hidden via init_script — reduces Cloudflare bot detection
- `networkidle` wait after domcontentloaded — gives JS-rendered forms time to mount
- reCAPTCHA textareas skipped (both in fill loop and fallback query)
- `"re"` removed from `_SUBJECT_HINTS` (was matching "g-recaptcha-response")
- JS eval fallback for hidden/framework-managed fields (HighLevel/msgsndr)
- Failed leads marked with `form-failed` in notes → auto-skipped on future runs

---

## API keys (all in .env)

- `ANTHROPIC_API_KEY` — Claude API
- `APIFY_API_KEY` + `APIFY_PROXY_PASSWORD` — Apify scraping proxy
- `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD` — email sending
- `SERPER_API_KEY` — Google search for leads
- `HUNTER_API_KEY` — email enrichment (currently disabled)
