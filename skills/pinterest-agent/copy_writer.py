"""
Pinterest Agent — Copy Writer
Generates 5 pin variations per keyword using Claude.

The SYSTEM_PROMPT is built from context/pinterest-expert.md — the expert
document is the single source of truth for every copy and design decision.
No rules are hardcoded here; they all live in the expert file.
"""
from __future__ import annotations

import os
import re
import json
import anthropic
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


PROJECT_ROOT = Path(__file__).parent.parent.parent
CONTEXT_DIR  = PROJECT_ROOT / "context"

# Product URL mapping — kept here to enforce correctness programmatically
PRODUCT_URLS: dict[str, str] = {
    "Instagram Template Pack":  "https://www.switzertemplates.com/instagram-templates",
    "Full Branding Kit":        "https://www.switzertemplates.com/branding-packages",
    "Premade Wix Website":      "https://www.switzertemplates.com/premade-wix-website-templates-for-sale",
    "3-in-1 Business Bundle":   "https://www.switzertemplates.com/business-template-bundles",
    "Design Vault":             "https://www.switzertemplates.com/join-design-vault",
    "Audience — all products":  "https://www.switzertemplates.com/blog",
    "educational":              "https://www.switzertemplates.com/blog",
}

# PM score → variation split (product pins, educational pins)
# PM=0 means "no direct product match" — 0 product pins, not 1. Forcing a
# product pin at PM=0 means Claude has to invent a connection that isn't
# really there (e.g. pitching Instagram templates on a "pinterest seo" pin),
# which reads as an unconvincing, off-topic pitch.
_PM_SPLIT: dict[int, tuple[int, int]] = {
    3: (4, 1),
    2: (3, 2),
    1: (2, 3),
    0: (0, 5),
}


def _load_context() -> dict[str, str]:
    files = {
        "expert":       "pinterest-expert.md",
        "products":     "product-catalog.md",
        "audience":     "target-audience.md",
        "voice":        "brand-voice.md",
        "visual_style": "pin-visual-style.md",
    }
    return {
        key: (CONTEXT_DIR / fname).read_text()
        if (CONTEXT_DIR / fname).exists() else ""
        for key, fname in files.items()
    }


def _build_system_prompt(ctx: dict[str, str]) -> str:
    return f"""You are the Pinterest copy agent for Switzertemplates.
The Pinterest Expert document below is your single source of truth.
Every decision you make — keyword placement, title structure, CTA choice,
design brief specificity, destination URL, variation ratio — must follow
the rules defined in it exactly.

═══════════════════════════════════════════════════════════════
PINTEREST EXPERT DOCUMENT (read fully before writing anything)
═══════════════════════════════════════════════════════════════
{ctx["expert"]}

═══════════════════════════════════════════════════════════════
PRODUCT CATALOG
═══════════════════════════════════════════════════════════════
{ctx["products"][:2500]}

═══════════════════════════════════════════════════════════════
TARGET AUDIENCE
═══════════════════════════════════════════════════════════════
{ctx["audience"][:1200]}

═══════════════════════════════════════════════════════════════
BRAND VOICE RULES
═══════════════════════════════════════════════════════════════
{ctx["voice"][:800]}

═══════════════════════════════════════════════════════════════
PIN FORMAT: COPY FIRST, DESIGN TEXT DERIVED FROM COPY
═══════════════════════════════════════════════════════════════
Every pin is a numbered-list infographic, generated whole by an image model,
text baked directly into the image. But the ORDER of thinking matters:

1. Write seo_title first — a real, full-sentence, outcome-led title (see the
   Title principles in the expert document). This is the actual copy. Get it
   right before touching anything else.
2. Only then derive eyebrow + headline from that title — a visual split or
   shortening of the SAME sentence, never a separately-invented label. If
   eyebrow + headline don't reconstruct (or closely echo) the seo_title when
   read together, that's a failure — go back and fix it.
3. subtitle_bar is the same idea, in a fuller line.

This is Jane's own proven top-performing format: eyebrow (optional) -> headline
-> numbered icon list -> bottom bar. Nothing renders below the bottom bar, and
no decorative leaf/floral/sparkle accents or divider lines anywhere — those read
as generic AI-image-gen filler, not a custom design. There is no background
photo — the substance of the pin IS the real copy, visually translated.

When a REAL BLOG POST is supplied for a keyword below, every pin_item and every
piece of copy for that topic must be grounded in what that post actually says —
its real specifics, numbers, and arguments — not generic advice reinvented from
the keyword alone. This is the single biggest quality lever: copy that quotes or
closely paraphrases something the post actually says reads as specific and useful;
copy invented from a bare keyword reads as generic stock advice. When no post is
supplied, write from real subject-matter knowledge, still avoiding generic filler.

═══════════════════════════════════════════════════════════════
PRODUCT URL MAPPING (populate destination_url from this exactly)
═══════════════════════════════════════════════════════════════
Instagram Template Pack    → https://www.switzertemplates.com/instagram-templates
Full Branding Kit          → https://www.switzertemplates.com/branding-packages
Premade Wix Website        → https://www.switzertemplates.com/premade-wix-website-templates-for-sale
3-in-1 Business Bundle     → https://www.switzertemplates.com/business-template-bundles
Design Vault               → https://www.switzertemplates.com/join-design-vault
Educational pins           → https://www.switzertemplates.com/blog

═══════════════════════════════════════════════════════════════
MANDATORY QUALITY CHECKS (run on every variation before outputting)
═══════════════════════════════════════════════════════════════
1. Is seo_title a full sentence (8-15 words), leading with an OUTCOME or CLAIM —
   not a summary of what the post covers? "Domain quality matters for SEO" is a
   content-descriptor and FAILS. "Learn Pinterest SEO the right way and get lots
   of traffic" passes.
1b. Does seo_title have the keyword in the first 4 words?
1c. Check seo_title for internal contradiction — does it claim "not just X" while
    X is itself something the pin covers? Rewrite if so.
2. Do eyebrow + headline, read together, reconstruct or closely echo seo_title as
   one sentence? If they read as two unrelated fragments, fix it.
3. Is the CTA appropriate for this keyword type, and does it actually match
   destination_url (never promise Etsy when the link goes to switzertemplates.com)?
   If PM=0 (variation_split is 0 PRODUCT + 5 EDUCATIONAL), do NOT invent a product
   connection anywhere — no product mentions, no product CTAs.
4. Does destination_url match the product being promoted?
5. pin_items: are all items real, specific, and actionable, and grounded in the real post
   when one is supplied — not vague filler ("do X" not "think about X")? Would a reader
   who only sees the image (never clicks) walk away having actually learned something?
5b. subtitle_bar: is it a genuine, specific hook — not a generic label like "tips to get
    found"? Could this exact line only apply to THIS post, not any post on the topic?
5c. item_order: does every variation in this topic show a genuinely different subset/order
    of pin_items from every other variation? If two variations would render the identical
    list, fix it before outputting.
6. Is seo_title under 100 characters?
7. Does every field use sentence case (first word capitalised, rest lowercase except
   proper nouns) or ALL CAPS (eyebrow only) — never Title Case anywhere, in any field?
8. CTAs rotating — no two variations in the same topic use the same CTA?
9. No third-person brand references ("Our X" not "The Switzertemplates X")?
10. Does each variation in the topic use a different TITLE ANGLE (benefit-led,
    problem-led, result-led, comparison-led, transformation-led) than the others?
11. Is the tactic/keyword itself ever the verb's subject performing an action —
    "Pinterest SEO built...", "Pinterest SEO turned...", "Pinterest SEO beats..."?
    A tactic can't act. Either a person acts ("you learn...", "I turned...") or
    it's a noun phrase being described ("the strategy that...", "the habit that...").
    Check the Style reference section's examples in the expert document — copy
    that grammatical pattern exactly, don't reinvent it.
12. Does any title/description compare Pinterest to Instagram, TikTok, or any
    other platform? Permanently banned, no exceptions — see "What this agent
    must never do" in the expert document.
13. Does the pin make sense for someone who sees it 6 months from now?

If any check fails, rewrite before outputting. Do not output until all checks pass.

═══════════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════════
Return ONLY a valid JSON array. No markdown. No explanation. Start with [ end with ]

Each element:
{{
  "topic_id": <integer>,
  "keyword": "<exact keyword — unchanged>",
  "keyword_volume": <integer>,
  "final_score": <float>,
  "product_match": <0-3>,
  "maps_to_product": "<product name>",
  "variation_split": "<e.g. 4 PRODUCT + 1 EDUCATIONAL>",
  "blog": {{
    "existing_post_likely": <true|false>,
    "note": "<if true: 'check blog for existing post'>",
    "blog_post_needed": <true|false>,
    "brief_for_blog_agent": "<if needed: 2-sentence brief>"
  }},
  "pin_items": [
    {{
      "title": "<ALL CAPS, 2-5 words, a specific real step or fact — e.g. 'THINK SEARCH, NOT SOCIAL'>",
      "description": "<one line, 8-14 words, plain and concrete — no fluff, no filler>",
      "icon": "<a short, simple, literal visual concept the designer can use if useful — e.g. 'a magnifying glass over a search bar'. A single concrete object or action, not a scene. The image prompt decides the actual rendering style (line art, full-color illustration, or none) based on the reference pin for that variation — this is just a content idea, not a strict style instruction.>"
    }}
    // 5 to 6 items total — the master list of real, factual substance for this topic,
    // grounded in the real blog post when one is supplied above. Each of the 5
    // variations below selects its own subset/order via item_order, so no two
    // pins in a topic show the identical set of items in the identical order —
    // that visual repetition reads as spam/duplicate content to Pinterest.
    // Never generic ("be consistent") — always specific and actionable.
  ],
  "variations": [
    {{
      "id": "<topic_id><a-e>",
      "type": "<PRODUCT|EDUCATIONAL>",
      "title_angle": "<one of: benefit-led | problem-led | result-led | comparison-led | transformation-led. Must differ from every other variation in this topic.>",
      "seo_title": "<THE MASTER COPY. Full sentence, 8-15 words, keyword in first 4 words, sentence case. Leads with an outcome/claim, not a content summary. This is Pinterest metadata AND the source every design-text field below is derived from. Example: 'Learn Pinterest SEO the right way and get lots of traffic'.>",
      "eyebrow": "<ALL CAPS. A lead-in fragment of seo_title — NOT the bare keyword, NOT a generic label. Read together with headline it must reconstruct seo_title as one sentence. Leave this as an empty string \"\" for some variations (real Pinterest pins mix eyebrow+headline with headline-only — don't use eyebrow on every single variation). Example: seo_title 'Learn Pinterest SEO the right way and get lots of traffic' -> eyebrow 'LEARN PINTEREST SEO'.>",
      "headline": "<Sentence case. The remainder of seo_title after the eyebrow (or, when eyebrow is empty, the punchiest fragment of seo_title standing alone). Continuing the example above -> headline 'The right way'. When eyebrow is empty, headline might be the full claim shortened, e.g. 'Pins that actually rank'.>",
      "subtitle_bar": "<one line, 6-14 words, sentence case, sits in a colored bar under the headline. The rest of seo_title's claim/context that didn't fit in eyebrow+headline — same sentence, not a new idea. Never a generic label like 'tips to get found'.>",
      "cta": "<the exact CTA phrase, naming the destination directly per the CTA rules in the expert document — e.g. 'Learn more on my blog!', 'Read more at switzertemplates.com!'. Must be embedded verbatim at the end of seo_description too. Rotate — no two variations in this topic use the same cta.>",
      "item_order": [<4 to 6 integers — 1-based indices into the topic's pin_items array above, in the order to display them for THIS variation. Choose a genuinely different subset and/or order for each of the 5 variations — drop a different item each time, reorder, whatever it takes so no two variations show an identical list. This is what keeps the 5 pin images visually distinct instead of looking like re-labeled duplicates.>],
      "category_label": "<ALL CAPS, max 20 chars>",
      "seo_description": "<keyword in first sentence, 150-300 chars, 2-4 punchy sentences naming a real specific/proof point, ends with the exact cta text above, then 2-3 hashtags>",
      "destination_url": "<exact URL from the product URL mapping above>"
    }}
  ]
}}"""


def _build_user_prompt(
    batch: list[dict],
    start_id: int,
    analytics_context: str,
    avoid_keywords: list[str],
) -> str:
    kw_lines = []
    post_blocks = []
    for i, k in enumerate(batch):
        pm        = k["product_match"]
        split     = _PM_SPLIT.get(pm, (2, 3))
        split_str = f"{split[0]} PRODUCT + {split[1]} EDUCATIONAL"
        topic_id  = start_id + i
        kw_lines.append(
            f"  topic_id={topic_id}  "
            f"keyword=\"{k['keyword']}\"  "
            f"volume={k['volume']:,}  "
            f"PM={pm}  "
            f"maps_to=\"{k['maps_to_product']}\"  "
            f"variation_split=\"{split_str}\""
        )
        excerpt = (k.get("post_excerpt") or "").strip()
        if excerpt:
            post_blocks.append(
                f"--- REAL BLOG POST for topic_id={topic_id} (\"{k['keyword']}\") ---\n"
                f"{excerpt[:3000]}\n"
            )

    posts_section = ""
    if post_blocks:
        posts_section = (
            "\n\nREAL BLOG POSTS — ground pin_items and subtitle_bar in these, use real "
            "specifics from the text, don't reinvent generic advice:\n" + "\n".join(post_blocks)
        )

    avoid = ""
    if avoid_keywords:
        avoid = "\n\nALREADY GENERATED — do NOT repeat these keywords:\n" + \
                ", ".join(f'"{k}"' for k in avoid_keywords[:40])

    return f"""Generate exactly {len(batch)} topic entries.

ANALYTICS FROM YOUR OWN PINTEREST ACCOUNT:
{analytics_context}

Use the analytics above to inform title structure choices. If a particular
structure dominates the top performers, favour it in new pin titles.

KEYWORDS TO PROCESS (topic_id, keyword, funnel stage, variation split):
{chr(10).join(kw_lines)}
{posts_section}

Rules:
- WRITE seo_title FIRST, for every variation, before touching eyebrow/headline/
  subtitle_bar. Those three are DERIVED from seo_title, not invented separately.
  seo_title is a full sentence (8-15 words) that leads with an outcome or claim —
  never a summary of what the post covers. Study the "Style reference" section
  in the expert document closely — copy that exact pattern, don't paraphrase it
  from memory. In particular: the tactic/keyword is NEVER the verb's subject
  ("Pinterest SEO built/turned/beats..." is always wrong) — a person acts, or
  the tactic is described as a noun phrase ("the strategy that...").
- NEVER compare Pinterest to Instagram, TikTok, or any other platform, in any
  field. If using the comparison-led angle, compare two things from within the
  topic itself, not platform vs. platform.
- Each of the 5 variations uses a different title_angle (benefit-led, problem-led,
  result-led, comparison-led, transformation-led) — no two the same.
- eyebrow + headline must reconstruct seo_title as one sentence when read together.
  Leave eyebrow as "" for 1-2 of the 5 variations — don't use the eyebrow+headline
  shape on every single one, real pins mix headline-only in too.
- pin_items (topic-level master list): 5-6 real, specific, actionable items about the
  keyword's topic, grounded in the real blog post above when one is supplied for that
  topic_id — the actual substance a reader learns from the pin image. Never generic.
  Each needs a short ALL CAPS title, a one-line description, and a simple literal icon.
- item_order (per variation): each of the 5 variations picks its own subset/order (4-6
  indices) from that topic's pin_items. No two variations in a topic may use the same
  subset in the same order — vary which item is dropped and how they're ordered so the
  5 pin images are genuinely different, not just re-labeled duplicates.
- cta: write the exact phrase per the CTA rules in the expert document — it names the
  destination directly ("Learn more on my blog!", "at switzertemplates.com!"). Embed
  it verbatim at the end of seo_description. Rotate — no two variations share one.
- If variation_split is "0 PRODUCT + 5 EDUCATIONAL", every variation must be EDUCATIONAL —
  do not invent a product tie-in that isn't real.
- Keyword must appear in first sentence of every seo_description
- Populate destination_url from the URL mapping — never leave it null
- Sentence case everywhere except eyebrow (ALL CAPS) and category_label (ALL CAPS) —
  never Title Case in any field, anywhere.
- Run all quality checks before outputting each variation

Return ONLY a JSON array of {len(batch)} objects. No markdown. Start [ end ].{avoid}"""


def _stream_call(client: anthropic.Anthropic, system: str,
                 user: str, max_tokens: int) -> list[dict]:
    raw = ""
    with client.messages.stream(
        model="claude-opus-4-5",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        for chunk in stream.text_stream:
            raw += chunk
        if stream.get_final_message().stop_reason == "max_tokens":
            print("  Warning: hit max_tokens — partial recovery attempted.")
    return _parse(raw)


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


# Names/brands — rendered as Capitalized (first letter up, rest as given).
_PROPER_NOUNS = {
    "pinterest", "etsy", "instagram", "canva", "wix", "google",
    "tiktok", "facebook", "shopify", "flodesk", "tailwind",
    "jane", "switzertemplates",
}

# Acronyms — rendered FULL UPPERCASE wherever they appear, not just word 1.
# Add to this list (not _PROPER_NOUNS) for any new all-caps abbreviation.
_ACRONYMS = {"seo", "diy", "url", "cta", "faq", "ai", "pdf", "ugc", "roi"}


def _enforce_case(text: str, upper: bool = False) -> str:
    """
    Guarantees sentence case (or ALL CAPS) regardless of what Claude actually
    returns — Title Case ("Pins That Actually Rank") is a hard rule violation,
    not a style preference, so it's fixed here programmatically rather than
    trusted to the model. Same principle as the UTM tagging below.

    Real names/brands and acronyms are preserved correctly wherever they fall
    in the sentence — "I", "Jane", "Pinterest", "SEO" never get force-lowercased
    just because they're not the first word. Anything NOT on these two lists
    still gets lowercased (that's what actually fixes Title Case); if a new
    name or acronym needs preserving, add it to the relevant set above.
    """
    if not text:
        return text
    if upper:
        return text.upper()
    words = text.split(" ")
    fixed = []
    for i, word in enumerate(words):
        prefix, core, suffix = "", word, ""
        while core and not core[0].isalpha():
            prefix += core[0]
            core = core[1:]
        while core and not core[-1].isalpha():
            suffix = core[-1] + suffix
            core = core[:-1]
        if not core:
            fixed.append(word)
            continue
        lower_core = core.lower()
        if lower_core == "i":
            # standalone pronoun "I" is always capitalized, any position
            new_core = "I"
        elif lower_core in _ACRONYMS:
            new_core = core.upper()
        elif lower_core in _PROPER_NOUNS:
            new_core = core[0].upper() + core[1:].lower()
        elif i == 0:
            new_core = core[0].upper() + core[1:].lower()
        else:
            new_core = core.lower()
        fixed.append(prefix + new_core + suffix)
    return " ".join(fixed)


def _add_utm(url: str, campaign: str) -> str:
    """Appends utm_source=pinterest&utm_medium=social&utm_campaign={campaign} to a
    destination URL — applied here, once, guaranteed, rather than trusting Claude to
    add it correctly in its own generated output."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["utm_source"] = "pinterest"
    query["utm_medium"] = "social"
    query["utm_campaign"] = campaign
    return urlunsplit(parts._replace(query=urlencode(query)))


def _parse(raw: str) -> list[dict]:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        raw = match.group()

    try:
        topics = json.loads(raw)
    except json.JSONDecodeError:
        try:
            last = raw.rfind("\n  },\n")
            if last == -1:
                last = raw.rfind("\n  }")
            if last > 0:
                topics = json.loads(raw[:last + 4] + "\n]")
                print(f"  Recovered {len(topics)} complete topics from truncated response.")
            else:
                raise ValueError("no recovery point")
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"Could not parse Claude response: {e}\n{raw[:300]}")

    required_topic = {"topic_id", "keyword", "variations"}
    required_var   = {"id", "type", "seo_title", "headline",
                      "seo_description", "destination_url", "cta"}
    valid = []
    for t in topics:
        if not isinstance(t, dict) or required_topic - set(t.keys()):
            continue
        # topic name is always the keyword — enforce
        t["topic"] = t["keyword"].strip().title()
        # pin_items is the substance of the infographic — required to render anything.
        # Missing/empty is a real gap, not silently droppable, but shouldn't kill the
        # whole topic either — downstream image generation fails per-pin and is logged.
        if not t.get("pin_items"):
            print(f"  Warning: '{t['keyword']}' has no pin_items — pins for this topic will fail to render.")
            t["pin_items"] = []
        for item in t["pin_items"]:
            if isinstance(item, dict):
                item["title"] = _enforce_case(item.get("title", ""), upper=True)
                item["description"] = _enforce_case(item.get("description", ""))
        clean_vars = []
        for v in t.get("variations", []):
            if isinstance(v, dict) and not (required_var - set(v.keys())):
                # Ensure destination_url is populated — fall back to product map
                if not v.get("destination_url"):
                    maps_to = t.get("maps_to_product", "")
                    v["destination_url"] = PRODUCT_URLS.get(maps_to, "https://www.switzertemplates.com")
                # Tag every destination URL for attribution, regardless of whether it
                # came from Claude directly or the fallback above — guaranteed, not
                # left to the model to remember.
                v["destination_url"] = _add_utm(v["destination_url"], _slugify(t["keyword"]))
                # Resolve this variation's item_order into an actual subset/order of the
                # topic's master pin_items, so each variation's copy_data is self-contained
                # for the image generator. Falls back to the full list in order if Claude
                # omitted item_order or gave something unusable — still renders correctly,
                # just without the intended per-variation visual variety.
                order = v.get("item_order")
                selected = []
                if isinstance(order, list):
                    for idx in order:
                        try:
                            i = int(idx) - 1
                        except (TypeError, ValueError):
                            continue
                        if 0 <= i < len(t["pin_items"]):
                            selected.append(t["pin_items"][i])
                v["pin_items"] = selected or t["pin_items"]
                # Hard rule: sentence case or ALL CAPS, never Title Case — guaranteed
                # here regardless of what Claude actually returned.
                v["seo_title"]    = _enforce_case(v.get("seo_title", ""))
                v["eyebrow"]      = _enforce_case(v.get("eyebrow", ""), upper=True)
                v["headline"]     = _enforce_case(v.get("headline", ""))
                v["subtitle_bar"] = _enforce_case(v.get("subtitle_bar", ""))
                v["cta"]          = _enforce_case(v.get("cta", ""))
                v["category_label"] = _enforce_case(v.get("category_label", ""), upper=True)
                clean_vars.append(v)
        if not clean_vars:
            continue
        t["variations"] = clean_vars
        valid.append(t)

    return valid


def generate(
    ranked: list[dict],
    analytics_context: str,
    top_n: int = 27,
    batch_size: int = 10,
) -> list[dict]:
    """
    Generate pin variations for the top_n keywords.
    Batches into groups of batch_size to stay within token limits.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set.")

    ctx    = _load_context()
    system = _build_system_prompt(ctx)
    client = anthropic.Anthropic(api_key=api_key)

    targets  = ranked[:top_n]
    all_done: list[dict] = []

    for batch_start in range(0, len(targets), batch_size):
        batch    = targets[batch_start:batch_start + batch_size]
        start_id = batch_start + 1
        avoid    = [t["keyword"] for t in all_done]

        print(f"  Generating topics {start_id}–{start_id + len(batch) - 1} "
              f"({len(batch)} keywords, streaming)...")

        user   = _build_user_prompt(batch, start_id, analytics_context, avoid)
        result = _stream_call(client, system, user, max_tokens=18000)

        # Re-number to prevent collisions
        for i, t in enumerate(result):
            t["topic_id"] = batch_start + i + 1
            for v in t.get("variations", []):
                old    = str(v.get("id", ""))
                letter = old[-1] if old and old[-1].isalpha() else chr(97 + i % 26)
                v["id"] = f"{t['topic_id']}{letter}"

        all_done.extend(result)
        print(f"  Batch done: {len(result)} topics generated.")

    return all_done
