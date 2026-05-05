from __future__ import annotations

import os
import json
import re
import anthropic


def _load_context_files(context: dict) -> str:
    """Condense context into a prompt excerpt."""
    return f"""
BRAND VOICE (abridged):
{context.get('brand_voice', '')[:1800]}

VISUAL STYLE:
{context.get('visual_style', '')[:800]}

PRODUCT CATALOG (abridged):
{context.get('product_catalog', '')[:1200]}

TARGET AUDIENCE (abridged):
{context.get('target_audience', '')[:1000]}
"""


SYSTEM_PROMPT = """You are the Pinterest copy writer for Switzertemplates.
You write on-brand Pinterest pin copy following the brand voice exactly.

Brand rules (non-negotiable):
- Tone: practical, human, benefit-led, grounded. Never fluffy, vague, or robotic.
- Short sentences. Every word earns its place.
- Use regular dashes ( - ) not em dashes.
- Connect design to a business outcome, always.
- Never use banned words: certainly, delve, embark, enlightening, craft, imagine,
  realm, game-changer, illuminate, unlock, discover, pivotal, skyrocket, boost,
  groundbreaking, cutting-edge, remarkable, landscape, clarity without benefit.
- Speak to female small business owners, coaches, consultants.

For pin_headline:
- The text printed ON the pin - must stop the scroll
- 5-15 words, all lowercase
- A frustration, realisation, or ambition - not a product pitch
- Examples: "your brand tells clients if you're worth hiring before you say a word"
  / "the reason your instagram isn't converting has nothing to do with your captions"

For category_label:
- Max 20 characters, ALL CAPS
- E.g. "BRANDING TIPS", "FOR COACHES", "BUSINESS TIPS", "WEB DESIGN", "SMALL BIZ"

For seo_title:
- 50-100 characters, include primary keyword naturally in the first half
- Benefit-led or problem-led. No clickbait, no question marks.
- Examples: "Branding kit for coaches - look professional and get more clients"
  / "Save time using business coach templates for your content"

For seo_description:
- 150-300 characters
- Lead with the main benefit or pain point
- Include 2-3 natural keywords
- End with: "Click to browse" or "Shop at switzertemplates.com"
- Never repeat the title word-for-word

For photo_concept:
- Describe a specific editorial-style background photo (not text, not logos)
- Must be business lifestyle: woman at laptop, desk flatlay, clean workspace,
  office interior, reading scene
- Emphasise: warm earthy tones, soft moody lighting, editorial quality
- Subject placed upper or right side of frame with negative space lower-left
- One specific, concrete scene (e.g. "A woman in a cream linen shirt working
  at a minimal white desk with a warm-toned neutral background, soft natural
  side lighting, laptop and a small plant visible, shallow depth of field,
  editorial magazine quality")
"""


def _placeholder_copy(topics: list[str]) -> list[dict]:
    """Generate placeholder copy for pipeline testing (no API call)."""
    samples = [
        ("BRANDING TIPS", "your brand tells clients if you're worth hiring before you say a word"),
        ("FOR COACHES", "the reason your instagram isn't converting has nothing to do with your captions"),
        ("BUSINESS TIPS", "a scattered brand is costing you clients before they even reach out"),
        ("WEB DESIGN", "your website is working for you 24/7 - or it isn't"),
        ("FOR SERVICE BIZ", "looking inconsistent online is the fastest way to lose a client's trust"),
        ("SMALL BIZ", "most business owners spend months on branding they could fix in a weekend"),
        ("FOR COACHES", "your templates should save you time, not create more decisions"),
        ("BUSINESS TIPS", "the gap between looking established and looking DIY is smaller than you think"),
        ("BRANDING TIPS", "consistency is what makes a brand feel credible before a word is spoken"),
        ("FOR COACHES", "you can't charge premium prices with a budget-looking brand"),
    ]
    results = []
    for i, topic in enumerate(topics):
        label, headline = samples[i % len(samples)]
        results.append({
            "topic": topic,
            "category_label": label,
            "pin_headline": headline,
            "seo_title": f"{topic.capitalize()} - look professional and attract more clients",
            "seo_description": (
                f"Get {topic} that make your business look established from day one. "
                f"Ready to customise in Canva - no design skills needed. "
                f"Shop at switzertemplates.com"
            ),
            "photo_concept": (
                "A woman in a cream linen shirt working at a minimal white desk, "
                "warm earthy neutral background, soft natural side lighting, "
                "laptop and small plant visible, editorial magazine quality, "
                "subject in upper-right, generous negative space lower-left"
            ),
        })
    return results


def generate_copy_batch(topics: list[str], context: dict, placeholder: bool = False) -> list[dict]:
    """
    Generate copy for all topics in one Claude call.
    Returns a list of dicts, one per topic, in the same order as input.
    """
    if placeholder:
        return _placeholder_copy(topics)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment.")

    client = anthropic.Anthropic(api_key=api_key)
    context_block = _load_context_files(context)

    topics_json = json.dumps(topics, ensure_ascii=False, indent=2)

    user_prompt = f"""
{context_block}

---

Generate Pinterest pin copy for each of these {len(topics)} topics.

Topics:
{topics_json}

Return ONLY a valid JSON array (no markdown, no explanation) with one object per topic.
Each object must have exactly these keys:
  "topic"            - the original topic string
  "category_label"   - all-caps label (≤20 chars)
  "pin_headline"     - text on the pin (lowercase, 5-15 words, hook)
  "seo_title"        - Pinterest SEO title (50-100 chars)
  "seo_description"  - Pinterest description (150-300 chars, ends with CTA)
  "photo_concept"    - specific background photo scene for image generation

Vary the category_labels and headline angles across pins - no two should feel alike.
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        results = json.loads(raw)
    except json.JSONDecodeError as e:
        # Try to extract JSON array from response
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            results = json.loads(match.group())
        else:
            raise RuntimeError(
                f"Claude returned invalid JSON.\nError: {e}\nRaw output:\n{raw[:500]}"
            )

    # Ensure we have one result per topic; pad with error entries if needed
    if len(results) < len(topics):
        for i in range(len(results), len(topics)):
            results.append({
                "topic": topics[i],
                "category_label": "BUSINESS TIPS",
                "pin_headline": topics[i],
                "seo_title": topics[i][:100],
                "seo_description": f"{topics[i]} - shop at switzertemplates.com",
                "photo_concept": (
                    "A woman working at a minimal desk, warm earthy tones, "
                    "soft natural lighting, editorial style"
                ),
            })

    return results[:len(topics)]
