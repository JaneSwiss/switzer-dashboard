"""
Pinterest Pins — Writer

Mirrors blog_seo_agent.write_blog_post()'s proven shape: one Claude call, fully
grounded in real content, with hardcoded rules instead of a living context
document — then a deterministic validation pass, same role as
check_banned_words(), with a one-shot revision retry on violation.

Deliberately NOT built on skills/pinterest-agent/copy_writer.py or
context/pinterest-expert.md — clean build, no inherited patch history.

Grounded in post_sections.py's real, untruncated post structure (see that
module's docstring for why the old 4000-char excerpt was a real bug), plus
Jane's own real approved reference pins, transcribed directly below rather
than left as unread images.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, parse_qsl, urlsplit, urlunsplit

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from post_sections import extract_post_sections, sections_as_text

load_dotenv(ROOT / ".env")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

MODEL = "claude-opus-4-5"

TITLE_ANGLES = ["benefit-led", "problem-led", "result-led", "comparison-led", "transformation-led"]

# Real examples of Jane's actual approved pin titles/descriptions, transcribed
# directly from agents/general-manager/switzertemplates-pins/titles-descriptions-CTAs/
# (not left as unread images). Trimmed to a diverse, on-voice selection.
REAL_REFERENCE_EXAMPLES = """
1. "Pinterest marketing is the free traffic strategy your business is sleeping on"
   Most business owners are pouring money into ads when pinterest marketing could be doing the same job for free. Pinterest is a search engine, not a social media platform - and that one shift changes everything. Learn more on my blog.

2. "The pinterest marketing strategy that drove 50k monthly visitors without a single ad"
   No paid ads. No viral moments. Just a consistent pinterest marketing strategy built around keywords, good pin design, and a posting schedule that never stops working. The full breakdown is on my blog - go check it out.

3. "You don't need more followers - you need a better pinterest marketing strategy"
   Follower count means almost nothing on Pinterest. What matters is keywords, boards, and pins that show up in search. That's what a real pinterest marketing strategy is built around. Get in touch to learn more about how to set this up for your business.

4. "The Pinterest for small business strategy that gets real results"
   Getting real results from Pinterest for small business comes down to three things - the right keywords, a consistent posting plan, and pins that are built to convert. Most small businesses skip at least one of these. Fix all three and your traffic changes fast. Get the strategy that covers all of it! #pinterestforsmallbusiness #pinterestmarketingstrategy #smallbusiness

5. "How often you actually need to pin for Pinterest marketing to work"
   One of the biggest questions in Pinterest marketing is how often to post. Your Pinterest marketing strategy should include a consistent pinning schedule - but consistency beats volume every time. You don't need to post 30 pins a day to see results. Find out the right rhythm for your account. Get your custom strategy today! #pinterestmarketing #pinterestmarketingstrategy #pinterestgrowth

6. "Your done for you Pinterest marketing strategy starts here"
   Not everyone has time to figure out Pinterest marketing from scratch. A done-for-you Pinterest marketing strategy takes the guesswork out completely - keywords researched, boards set up, and a content plan ready to go. You show up and post. Everything else is handled. See what's included and get started! #pinterestmarketingstrategy #pinterestmarketing #doneforyou
"""

# The on-image headline is a SEPARATE, short field — not the full seo_title.
# Jane's own literal examples of what she wants rendered on the pin design itself.
GOOD_IMAGE_HEADLINES = """
"Shopify vs Wix for ecommerce - an honest comparison"
"Shopify vs Wix for ecommerce - which one to choose"
"Which platform fits your ecommerce business"
"""
BAD_IMAGE_HEADLINES = """
"One question that settles the Shopify vs Wix decision faster than any feature list" (too long, reads like a sentence)
"Why most Shopify vs Wix comparisons fail coaches and service providers completely" (too long, awkward)
"""

SYSTEM_PROMPT = f"""You write Pinterest pin copy for Switzertemplates — premium branding kits,
premade Wix websites, and business bundles for female small business owners. That's service
providers and coaches, but just as often product-based and ecommerce sellers — let the post's
own topic decide who the examples/framing speak to, never default to coaching/service framing
for a post that's naturally about products, ecommerce, or shipping. Practical, human,
benefit-led tone. Never robotic, never generic AI-sounding.

You will be given the REAL, FULL text of an already-published blog post (every section,
not a summary) and must write 5 pin variations from it. Ground everything in what the post
actually says — never invent generic advice the post doesn't cover.

CASE RULE (strict): sentence case or ALL CAPS only, everywhere — titles, headlines, item
titles, descriptions. Never Title Case. Example: "pins that actually rank" or
"PINS THAT ACTUALLY RANK" — never "Pins That Actually Rank". Exceptions: the pronoun "I",
real proper nouns (Pinterest, Etsy, Instagram, Wix, Shopify, Canva, Google, Jane,
Switzertemplates), and acronyms (SEO, DIY, URL, CTA, FAQ) always stay capitalized regardless
of position.

TITLE ANGLES — rotate a genuinely different angle across the 5 variations, not the same
angle reworded 5 times: {", ".join(TITLE_ANGLES)}.

TWO DIFFERENT TITLE FIELDS — do not confuse these:
- seo_title: a full, natural sentence (8-15 words) for Pinterest's own SEO/search — this is
  what shows in the Pinterest feed and search results, not baked into the image.
- image_headline: SHORT — a few words to one short phrase, close to the actual keyword, NOT
  a full sentence, NOT a clever tagline. This is the text rendered directly on the pin design.
  Good examples: {GOOD_IMAGE_HEADLINES}
  Bad examples — too long, reads like a sentence, never do this: {BAD_IMAGE_HEADLINES}

PIN ITEMS — the real substance, grounded in the actual post sections given to you. Pull from
what the post really argues, in the post's own real structure. If the post has genuinely
two-sided/comparison content (e.g. two parallel sections each making the case for a different
option), it's fine for items to reflect that real contrast — but every item must be a distinct,
real point from the post, never an invented restatement of a point already used. 3 to 6 items,
whichever number the real content actually supports — do not pad to a fixed number and do not
force items that aren't really there. Each item: a short ALL CAPS title (2-5 words) and one
brief, natural-sounding line of description (a real sentence a person would say, not 3
unrelated nouns stitched together with corporate phrasing).

CTA — rotate across the 5 variations, always naming the real destination. Approved patterns,
drawn from Jane's real examples: "Learn more on my blog.", "Get more info on my blog.",
"The full breakdown is on my blog - go check it out.", "Get in touch to learn more.". Using no
explicit CTA (closing on the value statement instead) is also valid — use it occasionally, not
never.

NEVER DO THIS — the tactic/topic itself as the grammatical subject performing an action:
wrong: "Pinterest SEO beats keyword stuffing", "Shopify vs Wix settles the debate". These read
as AI-generated. Right: address the reader directly ("you", "your") or use a real noun phrase.

NEVER compare Pinterest to Instagram, TikTok, or any other platform — describe Pinterest (or
the post's actual topic) standalone.

STYLE REFERENCE — Jane's own real approved pins, match this tone and format exactly:
{REAL_REFERENCE_EXAMPLES}

OUTPUT — return ONLY a JSON array of exactly 5 objects, no preamble, no markdown fences:
[
  {{
    "id": "a",
    "title_angle": "benefit-led",
    "seo_title": "...",
    "seo_description": "150-300 characters, ends with the CTA, then 2-3 hashtags",
    "image_headline": "...",
    "image_eyebrow": "optional short all-caps label above the headline, or empty string",
    "cta": "...",
    "pin_items": [
      {{"title": "ALL CAPS SHORT TITLE", "description": "one natural sentence", "icon": "a short concrete visual idea"}}
    ]
  }}
]
Use ids a, b, c, d, e for the 5 variations."""


_PROPER_NOUNS = {"pinterest", "etsy", "instagram", "canva", "wix", "shopify", "google",
                  "tiktok", "facebook", "flodesk", "tailwind", "jane", "switzertemplates"}
_ACRONYMS = {"seo", "diy", "url", "cta", "faq", "ai", "pdf", "ugc", "roi"}


def _enforce_case(text: str, upper: bool = False) -> str:
    if not text:
        return text
    words = text.split(" ")
    out = []
    for i, w in enumerate(words):
        core = re.sub(r"[^\w'-]", "", w)
        lower_core = core.lower()
        if upper:
            # ALL CAPS mode: proper nouns/acronyms go full-caps too, matching the
            # surrounding case (e.g. "WIX BUILT-IN FEATURES", not "Wix BUILT-IN...").
            out.append(w.replace(core, core.upper(), 1) if core else w)
        elif lower_core == "i":
            out.append(w.replace(core, "I", 1) if core else w)
        elif lower_core in _ACRONYMS:
            out.append(w.replace(core, core.upper(), 1) if core else w)
        elif lower_core in _PROPER_NOUNS:
            out.append(w.replace(core, core.capitalize(), 1) if core else w)
        elif i == 0 and core:
            out.append(w.replace(core, core[0].upper() + core[1:].lower(), 1))
        else:
            out.append(w.lower() if core else w)
    return " ".join(out)


_PERSONIFICATION_VERBS = r"(beats?|outperforms?|crushes?|wins?|settles?|solves?|fixes?|built|turns?|drives?)"


def _find_personification(text: str) -> bool:
    """Heuristic: topic/tactic phrase immediately followed by an action verb with no
    'you'/'your'/'I' between them — the tactic-as-agent pattern banned above."""
    lower = text.lower()
    match = re.search(rf"^\s*[\w\s]{{2,40}}\b{_PERSONIFICATION_VERBS}\b", lower)
    if not match:
        return False
    prefix = lower[:match.start(1)]
    return not any(w in prefix.split() for w in ("you", "your", "i"))


def _find_duplicate_items(variations: list) -> list:
    seen = {}
    dupes = []
    for v in variations:
        for item in v.get("pin_items", []):
            key = item.get("description", "").strip().lower()[:40]
            if not key:
                continue
            if key in seen and seen[key] != v["id"]:
                dupes.append((seen[key], v["id"], item.get("title", "")))
            seen.setdefault(key, v["id"])
    return dupes


def validate_and_fix(variations: list, client: anthropic.Anthropic) -> list:
    """Deterministic checks (same role as blog_seo_agent.check_banned_words), with one
    revision retry via Claude if real issues are found — same pattern, not just a log."""
    issues = []
    for v in variations:
        if _find_personification(v.get("seo_title", "")):
            issues.append(f'"{v["id"]}" seo_title reads as tactic-as-agent: "{v["seo_title"]}"')
        if _find_personification(v.get("image_headline", "")):
            issues.append(f'"{v["id"]}" image_headline reads as tactic-as-agent: "{v["image_headline"]}"')

    dupes = _find_duplicate_items(variations)
    for a, b, title in dupes:
        issues.append(f'variations "{a}" and "{b}" both use a near-identical item ("{title}") — make each variation distinct')

    if issues:
        print(f"  Validation found {len(issues)} issue(s), requesting a fix...")
        revision_prompt = (
            f"Fix these specific issues in the pin variations below, changing only what's "
            f"needed to fix them — leave everything else as-is:\n"
            + "\n".join(f"- {i}" for i in issues)
            + f"\n\nReturn ONLY the corrected JSON array, same shape as before.\n\n"
            + json.dumps(variations, indent=2)
        )
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=4096,
                messages=[{"role": "user", "content": revision_prompt}],
            )
            variations = _parse_json_array(resp.content[0].text)
        except Exception as e:
            print(f"  Revision pass failed: {e} — keeping original, flagged issues remain.")

    # Case enforcement is deterministic — always applied, not left to the model.
    for v in variations:
        v["seo_title"] = _enforce_case(v.get("seo_title", ""))
        v["image_headline"] = _enforce_case(v.get("image_headline", ""))
        v["image_eyebrow"] = _enforce_case(v.get("image_eyebrow", ""), upper=True)
        for item in v.get("pin_items", []):
            item["title"] = _enforce_case(item.get("title", ""), upper=True)
            item["description"] = _enforce_case(item.get("description", ""))

    return variations


def _parse_json_array(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def _tag_utm(url: str, slug: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.update({"utm_source": "pinterest", "utm_medium": "social", "utm_campaign": slug})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def write_pins(slug: str, keyword: str) -> list:
    """
    One Claude call, grounded in the real full post (post_sections.py) — mirrors
    write_blog_post()'s single well-grounded call. Returns 5 validated variations.
    """
    post = extract_post_sections(slug)
    if not post["sections"]:
        raise RuntimeError(f"No post found/parsed for slug '{slug}' — cannot write grounded pin copy.")

    sections_text = sections_as_text(post["sections"])
    user_prompt = (
        f'Write 5 Pinterest pin variations for this post.\n\n'
        f'KEYWORD: {keyword}\n'
        f'POST TITLE: {post["title"]}\n\n'
        f'REAL POST CONTENT (every section, use this, not outside knowledge):\n{sections_text}'
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=MODEL, max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    variations = _parse_json_array(resp.content[0].text)
    variations = validate_and_fix(variations, client)

    dest_url = _tag_utm(post["url"], slug)
    for v in variations:
        v["destination_url"] = dest_url
        v["keyword"] = keyword
        v["slug"] = slug

    return variations
