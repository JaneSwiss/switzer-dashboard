# Blog SEO Agent — Status & Lessons Learned

*Last updated: 2026-09-21*

---

## Current State

- **Posts written:** 59 total in `dashboard_data.json` → `blog_seo_agent.posts`
- **Posts published on Wix:** ~33 live; ~26 sitting as unpublished drafts
- **Keyword masterlist:** `keywords/switzertemplates_keyword_masterlist.csv` — 162 rows

---

## Known Issues / Permanent Fixes Applied

### 1. Internal crosslinks: `<a href>` does NOT render in Wix
**Problem:** Wix's Ricos conversion strips `<a href>` tags from crosslinks. Posts show the text but no hyperlink.

**Fix:** Replace all internal `/post/` links with bold + visible URL format:
```html
<strong>anchor text [https://www.switzertemplates.com/post/slug]</strong>
```
Jane then manually adds the hyperlink in the Wix editor and deletes the bracketed URL before publishing.

**Applies to:** ALL internal blog-to-blog crosslinks. External links (CTAs to product pages) also affected — use same format OR confirm Ricos preserves them (currently unverified).

---

### 2. CTA rules — which product to link per post type

| Post topic | CTA 1 | CTA 2 |
|---|---|---|
| Ecommerce / selling / boutique / Shopify | `https://www.switzertemplates.com/shopify-theme-templates` | Pinterest services (see below) |
| Service / coaching / general business | `https://www.switzertemplates.com/premade-wix-website-templates-for-sale` | Pinterest services (see below) |
| Branding / design / social media | `https://www.switzertemplates.com/branding-packages` | Pinterest services (see below) |

**Pinterest services CTA** — add to every business/marketing post:
```
URL: https://pinterest.switzertemplates.com/
Text: Jane's done-for-you Pinterest marketing service
```

**Never use** `business-template-bundles` (3-in-1 bundle) as a CTA in blog posts.

---

### 3. First sentence: keyword must be inside the first `<p>` tag
**Problem:** Blog agent repeatedly places the keyword in bold italic OUTSIDE the first `<p>` tag — as floating text after the H1, with the hook paragraph following separately.

**Required format:**
```html
<h1>TITLE</h1>
<p><strong><em>Keyword phrase</em></strong> rest of first sentence here. Hook continues in same paragraph.</p>
```

**Wrong format the agent keeps producing:**
```html
<h1>TITLE</h1>
<strong><em>Keyword phrase</em></strong> rest of first sentence.
<p>Hook paragraph starts here.</p>
```

If the agent produces the wrong format, the keyword floats before the first `<p>` and must be manually merged into it.

---

### 4. Crosslink source: use `dashboard_data.json`, not the live blog page
**Problem fixed 2026-09-21:** Agent used to scrape `https://www.switzertemplates.com/blog` for crosslink candidates — only returned ~9 posts due to Wix lazy-loading (71 posts live).

**Fix applied in `blog_seo_agent.py` lines ~958-994:** Now reads `dashboard_data.json` → `blog_seo_agent.posts` array, which tracks all 59 posts.

---

### 5. Wix drafts: each push creates a NEW draft
Running `publish_to_wix.py <slug>` without a draft_id always creates a new draft. To UPDATE an existing draft without duplicates:
```
python3 publish_to_wix.py <slug> <full-draft-id>
```
Draft IDs are returned after each push. Save them to `dashboard_data.json` → `blog_seo_agent.posts[*].wix_draft_id` (currently not being saved — should be added).

---

## Current Wix Draft State (as of 2026-09-21)

The 8 posts written 2026-09-20 have multiple draft versions in Wix due to being pushed 3 times (once without crosslinks, once with, once with fixed CTAs). The **correct/current** draft IDs are:

| Slug | Draft ID |
|---|---|
| small-business-ideas-for-women | `3044ef7b-5917-4e3c-9215-e881c5e46e07` |
| home-business-ideas-for-women | `c1591020-ff00-4a83-9fcf-09fe2d2df542` |
| how-to-sell-clothes-online | `7f011845-7720-4e08-afe9-fe6c89503193` |
| online-business-ideas-for-women | `18a45000-7b95-458f-bf7d-9386e1db8358` |
| side-business-ideas-for-women | `f0b870ab-8736-42e2-9683-3c22eca4b850` |
| unique-business-ideas-for-women | `8d2a1c32-6040-4b16-a171-a03d4763185e` |
| what-to-sell-online | `0b7788c7-f2d8-456d-916d-5c2ac9556c3f` |
| how-to-start-an-online-boutique | `6fb3cb55-de0b-42da-8aa8-8a4582beb3ff` |

Jane needs to delete the older duplicate drafts for these 8 posts from Wix Blog → Drafts.

---

## Next Actions

- [ ] Fix `publish_to_wix.py` to save returned draft IDs back to `dashboard_data.json`
- [ ] Fix `blog_seo_agent.py` prompt to enforce keyword inside first `<p>` tag
- [ ] Consider fixing `blog_seo_agent.py` to generate crosslinks in bold+URL format from the start instead of `<a href>`
- [ ] Batch publish the 26 unpublished drafts (see Phase 1 of traffic growth plan)
