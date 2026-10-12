# Blog SEO Agent — Status & Lessons Learned

*Last updated: 2026-10-12*

---

## Current State

- **Posts written:** 59 total in `dashboard_data.json` → `blog_seo_agent.posts`
- **Posts published on Wix:** ~33 live; ~26 sitting as unpublished Wix drafts (13 cleaned and re-pushed 2026-10-12)
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

## Current Wix Draft State (as of 2026-10-12)

All unpublished draft posts have been cleaned (DALL-E placeholders removed, broken crosslinks fixed, inline images generated) and re-pushed 2026-10-12. Current draft IDs:

| Slug | Draft ID | Status |
|---|---|---|
| small-business-ideas-for-women | `3044ef7b-5917-4e3c-9215-e881c5e46e07` | pushed 2026-09-21 |
| home-business-ideas-for-women | `c1591020-ff00-4a83-9fcf-09fe2d2df542` | pushed 2026-09-21 |
| how-to-sell-clothes-online | `7f011845-7720-4e08-afe9-fe6c89503193` | pushed 2026-09-21 |
| online-business-ideas-for-women | `18a45000-7b95-458f-bf7d-9386e1db8358` | pushed 2026-09-21 |
| side-business-ideas-for-women | `f0b870ab-8736-42e2-9683-3c22eca4b850` | cleaned + re-pushed 2026-10-12 |
| unique-business-ideas-for-women | `8d2a1c32-6040-4b16-a171-a03d4763185e` | cleaned + re-pushed 2026-10-12 |
| what-to-sell-online | `0b7788c7-f2d8-456d-916d-5c2ac9556c3f` | cleaned + re-pushed 2026-10-12 |
| how-to-start-an-online-boutique | `6fb3cb55-de0b-42da-8aa8-8a4582beb3ff` | cleaned + re-pushed 2026-10-12 |
| how-to-create-pins-on-pinterest | `6e8b0583-a572-4f3a-95d1-0a00eca93079` | cleaned + re-pushed 2026-10-12 |
| how-to-earn-money-from-pinterest | `9e9d160b-34f3-4173-aa85-2ee9afc75967` | cleaned + re-pushed 2026-10-12 |
| how-to-get-followers-on-pinterest | `fc0927b6-cfa1-4453-a18c-a2c2b668a620` | cleaned + re-pushed 2026-10-12 |
| how-to-make-a-pinterest-board | `0d9cbdbc-11ed-4d02-99df-a4624fa51a36` | cleaned + re-pushed 2026-10-12 |
| how-to-start-a-pinterest-page | `99609a71-dccf-4d64-b9f2-7a97a8a7ac0d` | cleaned + re-pushed 2026-10-12 |
| pinterest-tips-for-beginners | `19a9c8a9-1deb-463e-89e7-ae6e144a512e` | cleaned + re-pushed 2026-10-12 |
| pinterest-marketing-manager | `89e0be44-3f4f-4747-a482-f60e3696fba5` | cleaned + re-pushed 2026-10-12 |
| shopify-themes | `4d20a165-e430-4518-8299-e37b58ef5a75` | cleaned + re-pushed 2026-10-12 |
| shopify-website-design-templates | `29c9f74d-444a-4aec-a399-2d29142b56a8` | cleaned + re-pushed 2026-10-12 |
| pinterest-marketing-strategy | `f706734f-e549-4517-a67e-0f6d8375e311` | cleaned + re-pushed 2026-10-12 |
| selling-on-pinterest | `3497e677-edbd-48b5-9cfa-a0c21276ba47` | cleaned + re-pushed 2026-10-12 |

Jane may have old duplicate drafts in Wix for some posts — safe to delete any that aren't in the IDs above.

---

## Bugs Fixed in blog_seo_agent.py (2026-10-12)

### Bug A — Failed inline images became visible DALL-E prompt boxes
**Root cause:** When `generate_inline_images()` failed (OpenAI $0 balance), it kept the `[DALLE: ...]` marker in the HTML. `_assemble_html()` then rendered it as a visible blue box with the prompt text.

**Fix — two places:**
1. `generate_inline_images()` line ~1680: on exception, now appends `""` instead of `m.group(0)` — silently drops the marker.
2. `_assemble_html()` line ~1875: replaces `dalle_block()` render function with a silent `re.sub(r'\[DALLE:.*?\]', '', content)` — any surviving marker is stripped, never rendered.

### Bug B — Third-person "Jane's" CTA language
**Fix lines ~811, 822:** Removed "Jane's" from Pinterest and Shopify service CTA descriptions in the system prompt. Now reads "done-for-you Pinterest marketing service" and "premade Shopify themes" without the third-person attribution.

---

## Permanent Limitations

**13 already-PUBLISHED live posts still have DALL-E boxes in Wix:** These posts were published before the bug was found. Can't re-push via API (never push to live posts). Jane must manually remove the blue DALL-E prompt boxes in the Wix editor for each affected live post.

---

## Next Actions

- [ ] Fix `publish_to_wix.py` to save returned draft IDs back to `dashboard_data.json`
- [ ] Fix `blog_seo_agent.py` prompt to enforce keyword inside first `<p>` tag
- [ ] Consider fixing `blog_seo_agent.py` to generate crosslinks in bold+URL format from the start instead of `<a href>`
- [ ] Jane publishes the ~19 cleaned unpublished Wix drafts (see traffic growth plan Phase 1)
- [ ] Jane manually removes DALL-E placeholder boxes from the ~13 affected live posts in Wix editor
