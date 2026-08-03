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
PIN FORMAT: NUMBERED-LIST INFOGRAPHIC (not a photo pin)
═══════════════════════════════════════════════════════════════
Every pin is a numbered-list infographic — generated whole by an image model, text
baked directly into the image. This is Jane's own proven top-performing format:
eyebrow label -> big serif headline -> numbered icon list -> bottom URL bar -> tagline.
There is no background photo and no separate design_brief — the substance of the
pin IS the list of real, specific, actionable items about the keyword.

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
1. Is pin_headline short and big-text-friendly (2-5 words — this is rendered LARGE on the
   image, not a full sentence, NOT the seo_title)?
1b. Does seo_title have the keyword in the first 4 words?
2. Does the keyword appear in the first sentence of the description?
3. Is the CTA appropriate for this keyword type — product keyword or educational keyword?
   If PM=0 (variation_split is 0 PRODUCT + 5 EDUCATIONAL), do NOT invent a product
   connection anywhere — no product mentions, no "shop my templates" CTAs. If there's
   no real, natural connection between this keyword and a product, don't force one.
4. Does destination_url match the product being promoted?
5. pin_items: are all items real, specific, and actionable, and grounded in the real post
   when one is supplied — not vague filler ("do X" not "think about X")? Would a reader
   who only sees the image (never clicks) walk away having actually learned something?
5b. accent_word: exactly one word from pin_headline, carries real weight, not a filler word?
5c. subtitle_bar: is it a genuine, specific hook — not a generic label like "tips to get
    found"? Could this exact line only apply to THIS post, not any post on the topic?
5d. item_order: does every variation in this topic show a genuinely different subset/order
    of pin_items from every other variation? If two variations would render the identical
    list, fix it before outputting.
6. Title under 100 characters?
7. Title makes a specific promise — not a generic label?
8. CTAs rotating — no two consecutive variations use the same CTA?
9. No third-person brand references ("Our X" not "The Switzertemplates X")?
10. Does the pin make sense for someone who sees it 6 months from now?

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
      "icon": "<a short, simple, literal visual concept for a thin line-art icon — e.g. 'a magnifying glass over a search bar'. Must be renderable as a single simple icon, not a scene.>"
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
      "eyebrow": "<ALL CAPS, 1-4 words, small label above the headline — e.g. 'HOW TO USE', 'THE COMPLETE GUIDE TO', 'STOP DOING THIS'>",
      "pin_headline": "<2-5 words. The BIG headline text on the pin image — short and punchy enough to render large, like a magazine cover word or two. NOT a sentence. NOT the seo_title. Examples: 'Pinterest SEO', 'Free Business Tools', 'Client-Ready Websites'.>",
      "accent_word": "<exactly one word from pin_headline to render in an italic accent color — the word that carries the most weight.>",
      "subtitle_bar": "<one line, 6-12 words, sits in a colored bar directly under the headline. This is the real scroll-stopping hook, not a generic label — write it the way you'd write pin_headline in a normal (non-infographic) pin: specific, curiosity-driven or benefit-led, grounded in something the real post actually says. 'Pinterest ranks pins on four factors — not just keywords' beats 'Tips to get found in search'. Never two variations with the same angle.>",
      "item_order": [<4 to 6 integers — 1-based indices into the topic's pin_items array above, in the order to display them for THIS variation. Choose a genuinely different subset and/or order for each of the 5 variations — drop a different item each time, reorder, whatever it takes so no two variations show an identical list. This is what keeps the 5 pin images visually distinct instead of looking like re-labeled duplicates.>],
      "tagline": "<one short italic line under the bottom bar, 4-10 words — e.g. 'More Pinterest tips for small business owners', or a soft product nudge for PRODUCT-type variations.>",
      "category_label": "<ALL CAPS, max 20 chars>",
      "seo_title": "<keyword in first 4 words, 50-100 chars, sentence case, benefit-led or action-led. This is Pinterest metadata only — never appears on the pin image itself. Example: 'Coach websites that win clients before the first call'>",
      "seo_description": "<keyword in first sentence, 150-300 chars, CTA at end>",
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
- pin_items (topic-level master list): 5-6 real, specific, actionable items about the
  keyword's topic, grounded in the real blog post above when one is supplied for that
  topic_id — the actual substance a reader learns from the pin image. Never generic.
  Each needs a short ALL CAPS title, a one-line description, and a simple literal icon.
- item_order (per variation): each of the 5 variations picks its own subset/order (4-6
  indices) from that topic's pin_items. No two variations in a topic may use the same
  subset in the same order — vary which item is dropped and how they're ordered so the
  5 pin images are genuinely different, not just re-labeled duplicates.
- pin_headline is the BIG text on the pin image — 2-5 words, not a sentence. NOT
  keyword-first. NOT the SEO title.
- subtitle_bar carries the real hook — specific, grounded in the post, not a generic
  label. Vary the angle across all 5 variations (result-led, problem-led, number-led,
  question-led — like a real direct-response headline, not filler).
- eyebrow, tagline, accent_word: also vary the wording across all 5 variations so the 5
  pins don't read identically. No two variations should use the same eyebrow phrasing.
- If variation_split is "0 PRODUCT + 5 EDUCATIONAL", every variation must be EDUCATIONAL —
  do not invent a product tie-in that isn't real.
- seo_title is Pinterest metadata — keyword in first 4 words, benefit-led, sentence case.
  Completely different from pin_headline.
- Keyword must appear in first sentence of every seo_description
- Rotate CTAs — no two consecutive variations in the same topic use the same CTA
- Use CTAs from the expert document only (no "Shop at switzertemplates.com" — too corporate)
- Populate destination_url from the URL mapping — never leave it null
- Title structures must vary across the 5 variations — no two the same
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
    required_var   = {"id", "type", "pin_headline", "seo_title",
                      "seo_description", "destination_url"}
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
