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

For scene_type and photo_concept:
- scene_type must be one of exactly: person, flat_lay, workspace, hands_only
- Use the following as the structural foundation for every design brief.
  Fill in only the topic-specific creative details (action, props, setting).
  Keep the composition structure intact.

person template:
"[MOOD keyword first]. Medium-close editorial photograph for a Pinterest marketing pin.
A woman [specific business-related action — working on a laptop, writing in a journal,
on a phone call, reading documents, scrolling her phone] at [specific setting].
Shot on an 85mm lens, tight chest-up framing. Her face and shoulders occupy the upper
third of the frame. The lower portion of the frame is filled with [specific desk surface
props — coffee cup, notebook, pen, planner etc.] — richly textured, styled, and detailed.
Quiet luxury, feminine, sophisticated, magazine quality."

flat_lay template:
"[MOOD keyword first]. Strict 90-degree overhead top-down editorial photograph for a
Pinterest marketing pin. A styled desk flat lay — [specific objects relevant to the topic,
e.g. open notebook with gold pen, ceramic espresso cup, closed planner, dried pampas grass].
Objects arranged across the entire frame edge to edge. Every corner filled with styled
elements, nothing empty. No person, no hands. Warm cream tones, quiet luxury, feminine,
magazine quality."

workspace template:
"[MOOD keyword first]. Medium-close editorial photograph for a Pinterest marketing pin.
A styled home office corner shot from a slight low angle looking up. A warm cream wall
behind the desk holds [specific wall element — framed minimalist art print, floating shelf
with objects, trailing plant]. The desk surface has [specific props relevant to the topic].
Props and styled elements fill the frame from the desk surface up to the wall element —
nothing empty, no plain ceiling, no blank upper area. Quiet luxury, feminine, sophisticated,
magazine quality."

hands_only template:
"[MOOD keyword first]. Macro close-up editorial photograph for a Pinterest marketing pin.
Shot on an 85mm lens. A pair of female hands with neutral nails actively [specific action —
writing in a notebook, typing on a keyboard, holding a ceramic coffee cup, turning a page].
The desk surface beneath shows [specific surface texture and props]. The entire frame filled
with hands, surface, and props — nothing empty. No face visible anywhere. Quiet luxury,
feminine, sophisticated, magazine quality."

Hard rules:
- Never write a brief where the woman is simply standing, walking, or posing.
  Every person scene must show active business behaviour.
- Never describe what is on any screen or device.

Distribution rule: Across the 5 variations in every topic, you must use each of these
scene types at least once: person, flat_lay, workspace, hands_only. The 5th variation
can be any type that best suits the topic.

For layout:
- One of exactly: A, B, C, D
- A — subject on left third, text box on right. Use for person or hands_only scenes only.
- B — subject on right third, text box on left. Use for person or hands_only scenes only.
- C — flat lay overhead, text box centered. Use only for flat_lay scenes.
- D — workspace shot, text box in upper third. Use only for workspace scenes.

Layout assignment rule:
- Variations a and b: assign A or B (alternate: if a=A then b=B, if a=B then b=A).
  Never assign layout C or D to a person or hands_only scene.
- Variation c: must always use layout C.
- Variation d: must always use layout D.
- Variation e: any layout that matches its scene type.
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
  "scene_type"       - one of: person, flat_lay, workspace, hands_only
  "layout"           - one of: A, B, C, D

Vary the category_labels and headline angles across pins - no two should feel alike.
"""

    _REQUIRED_SCENE_TYPES = {"person", "flat_lay", "workspace", "hands_only"}
    _MAX_RETRIES = 3

    for attempt in range(_MAX_RETRIES):
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
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                try:
                    results = json.loads(match.group())
                except json.JSONDecodeError:
                    if attempt < _MAX_RETRIES - 1:
                        print(f"  JSON parse failed (attempt {attempt + 1}), retrying...")
                        continue
                    raise RuntimeError(
                        f"Claude returned invalid JSON.\nError: {e}\nRaw output:\n{raw[:500]}"
                    )
            else:
                if attempt < _MAX_RETRIES - 1:
                    print(f"  JSON parse failed (attempt {attempt + 1}), retrying...")
                    continue
                raise RuntimeError(
                    f"Claude returned invalid JSON.\nError: {e}\nRaw output:\n{raw[:500]}"
                )

        # Scene type validation — only when generating a full 5-variation topic batch
        if len(results) >= 4:
            present = {r.get("scene_type", "") for r in results}
            missing = _REQUIRED_SCENE_TYPES - present
            if missing:
                if attempt < _MAX_RETRIES - 1:
                    print(f"  Scene type validation failed (attempt {attempt + 1}): "
                          f"missing {missing}. Retrying...")
                    continue
                else:
                    print(f"  Warning: scene types still missing after {_MAX_RETRIES} attempts: "
                          f"{missing}. Using response as-is.")

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
                    "scene_type": "person",
                })

        return results[:len(topics)]

    raise RuntimeError(f"Failed to generate valid copy after {_MAX_RETRIES} attempts.")
