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
_PM_SPLIT: dict[int, tuple[int, int]] = {
    3: (4, 1),
    2: (3, 2),
    1: (2, 3),
    0: (1, 4),
}


def _load_context() -> dict[str, str]:
    files = {
        "expert":   "pinterest-expert.md",
        "products": "product-catalog.md",
        "audience": "target-audience.md",
        "voice":    "brand-voice.md",
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
1. Is pin_headline a short punchy magazine-cover line (5-12 words, NOT keyword-first, NOT the seo_title)?
1b. Does seo_title have the keyword in the first 4 words?
2. Does the keyword appear in the first sentence of the description?
3. Is the CTA appropriate for this keyword type — product keyword or educational keyword?
4. Does destination_url match the product being promoted?
5. Design brief: describes a lifestyle/editorial scene with a real person — never a product or device screen?
5b. highlight_words: 1-2 words only, carries real emotional or commercial weight, not a filler word?
6. Title under 100 characters?
7. Title makes a specific promise — not a generic label?
8. CTAs rotating — no two consecutive variations use the same CTA?
9. No third-person brand references ("Our X" not "The Switzertemplates X")?
10. Does the pin make sense for someone who sees it 6 months from now?

If any check fails, rewrite before outputting. Do not output until all 10 pass.

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
  "variations": [
    {{
      "id": "<topic_id><a-e>",
      "type": "<PRODUCT|EDUCATIONAL>",
      "pin_headline": "<5-12 words. Text displayed ON the pin image. Short, punchy, human — like a magazine cover line. Must stop the scroll and make the reader feel seen or curious. NOT keyword-first, NOT SEO copy. Emotional and direct. Examples: 'Your brand is saying things you didn't intend', 'The website that works while you sleep', 'What clients notice before they read a word', 'This is why browsers don't become buyers'. Never generic. Never the SEO title.>",
      "category_label": "<ALL CAPS, max 20 chars>",
      "seo_title": "<keyword in first 4 words, 50-100 chars, sentence case, benefit-led or action-led. This is Pinterest metadata only — never appears on the pin image itself. Example: 'Coach websites that win clients before the first call'>",
      "seo_description": "<keyword in first sentence, 150-300 chars, CTA at end>",
      "design_brief": "<50+ words. Start with the MOOD keyword. Then write a specific, cinematic scene for Gemini to generate. CRITICAL: the 5 briefs in a topic must be visually distinct — different subject, angle, props and composition every time. Rotate through these scene types: a woman working at a desk, a close-up of hands holding coffee or writing, an overhead flat lay of a workspace, a woman walking or standing outdoors in a professional setting, a woman seated reading or thinking. Always business-adjacent. Never two similar compositions in the same topic. Never reference a screen or device showing content. MOOD per variation letter: a=BRIGHT AIRY WHITE (pure white/cream, bright daylight, ultra-clean), b=WARM DARK MOODY (espresso browns, dramatic low light, dark warm shadows), c=BEIGE NEUTRAL (sandy beige/ivory, warm afternoon light, soft matte), d=COOL GREY (cool grey, overcast light, polished, no warmth), e=EARTHY BROWN (rich wood/brown tones, amber lamp light). State the mood in the first line of the brief.>",
      "highlight_words": ["<1-2 words from the pin_headline that carry the most emotional or commercial weight. Chosen deliberately — the word/s the audience will feel or act on. Never a conjunction, preposition, article, or filler word. Examples: in 'Your website should win clients before you even speak to them' → ['win'] or ['win', 'clients']. In 'The gap between looking established and looking DIY is smaller than you think' → ['established']. In 'Wix website template to look professional and attract more clients' → ['professional', 'clients']. Always an array even if only 1 word.>"],
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
    for i, k in enumerate(batch):
        pm        = k["product_match"]
        split     = _PM_SPLIT.get(pm, (2, 3))
        split_str = f"{split[0]} PRODUCT + {split[1]} EDUCATIONAL"
        kw_lines.append(
            f"  topic_id={start_id + i}  "
            f"keyword=\"{k['keyword']}\"  "
            f"volume={k['volume']:,}  "
            f"PM={pm}  "
            f"maps_to=\"{k['maps_to_product']}\"  "
            f"variation_split=\"{split_str}\""
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

Rules:
- pin_headline is the text ON the pin image — short, punchy, magazine cover line. NOT
  keyword-first. NOT the SEO title. Make the reader feel seen or curious. 5-12 words.
- seo_title is Pinterest metadata — keyword in first 4 words, benefit-led, sentence case.
  Completely different from pin_headline.
- Keyword must appear in first sentence of every seo_description
- Rotate CTAs — no two consecutive variations in the same topic use the same CTA
- Use CTAs from the expert document only (no "Shop at switzertemplates.com" — too corporate)
- Populate destination_url from the URL mapping — never leave it null
- Design brief must describe a lifestyle or editorial scene with a real person (woman at a desk,
  in a coffee shop, close-up of hands on a keyboard, woman reviewing documents, professional
  woman in neutral clothing). Warm earthy tones, soft moody lighting. Never reference a product,
  laptop screen, tablet screen, or any device showing content. The scene sets a mood — it does
  not show the product.
- highlight_words: choose 1-2 words from the headline that carry the most emotional or
  commercial weight — the word/s the audience will feel or respond to. Never a conjunction,
  preposition, article, or filler. Always an array. Chosen deliberately, not randomly.
- design_brief: write 5 visually distinct scenes — different subject, angle, composition
  and setting in every brief. CRITICAL: never two similar scenes in the same topic.
  Rotate through: woman at a desk, close-up of hands/coffee/notebook, overhead flat lay,
  woman walking or standing in an outdoor or architectural setting, portrait of woman
  thinking or reading. Always business-adjacent. Never reference a screen showing content.
  Mood per variation (state in first line of brief):
  a=BRIGHT AIRY WHITE  b=WARM DARK MOODY  c=BEIGE NEUTRAL  d=COOL GREY  e=EARTHY BROWN
- Title structures must vary across the 5 variations — no two the same
- Run all 10 quality checks before outputting each variation

Return ONLY a JSON array of {len(batch)} objects. No markdown. Start [ end ].{avoid}"""


def _stream_call(client: anthropic.Anthropic, system: str,
                 user: str, max_tokens: int) -> list[dict]:
    raw = ""
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        for chunk in stream.text_stream:
            raw += chunk
        if stream.get_final_message().stop_reason == "max_tokens":
            print("  Warning: hit max_tokens — partial recovery attempted.")
    return _parse(raw)


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
                      "seo_description", "design_brief", "destination_url"}
    valid = []
    for t in topics:
        if not isinstance(t, dict) or required_topic - set(t.keys()):
            continue
        # topic name is always the keyword — enforce
        t["topic"] = t["keyword"].strip().title()
        clean_vars = []
        for v in t.get("variations", []):
            if isinstance(v, dict) and not (required_var - set(v.keys())):
                # Ensure destination_url is populated — fall back to product map
                if not v.get("destination_url"):
                    maps_to = t.get("maps_to_product", "")
                    v["destination_url"] = PRODUCT_URLS.get(maps_to, "https://www.switzertemplates.com")
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
