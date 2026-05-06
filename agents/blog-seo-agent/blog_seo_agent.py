#!/usr/bin/env python3
"""
Blog SEO Agent — Switzertemplates
Picks the next keyword from the masterlist, researches competitors via ValueSERP,
writes a complete blog post via Claude, saves output, and logs completion.

Run with:
    python agents/blog-seo-agent/blog_seo_agent.py
"""

import csv
import json
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Optional

import anthropic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


# ── paths ─────────────────────────────────────────────────────────────────────

ROOT        = Path(__file__).resolve().parents[2]
AGENT_DIR   = Path(__file__).resolve().parent
KEYWORDS_FILE   = AGENT_DIR / "keywords" / "switzertemplates_keyword_masterlist.csv"
OUTPUT_DIR      = AGENT_DIR / "output"
LOGS_DIR        = AGENT_DIR / "logs"
COMPLETED_LOG   = LOGS_DIR / "completed.json"
ERROR_LOG       = LOGS_DIR / "errors.json"
BRAND_VOICE_FILE    = ROOT / "context" / "brand-voice.md"
STYLE_EXAMPLES_FILE = ROOT / "context" / "content-style-examples.md"

load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY")
VALUESERP_API_KEY   = os.getenv("VALUESERP_API_KEY")

BANNED_WORDS = [
    "certainly", "delve", "embark", "enlightening", "esteemed", "shed light",
    "craft", "imagine", "realm", "game-changer", "illuminate", "unlock",
    "discover", "pivotal", "skyrocket", "abyss", "folks", "furthermore",
    "harness", "groundbreaking", "cutting-edge", "remarkable", "glimpse",
    "navigating", "landscape", "stark", "moreover", "boost",
    "you've got this", "level up", "exciting news", "have you ever wondered",
]

FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ── shared helpers ─────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def log_error(stage: str, keyword: str, message: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    errors = []
    if ERROR_LOG.exists():
        try:
            errors = json.loads(ERROR_LOG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    errors.append({
        "date": date.today().isoformat(),
        "stage": stage,
        "keyword": keyword,
        "error": message,
    })
    ERROR_LOG.write_text(json.dumps(errors, indent=2), encoding="utf-8")


def read_context_files() -> "tuple[str, str]":
    brand_voice     = BRAND_VOICE_FILE.read_text(encoding="utf-8")
    style_examples  = STYLE_EXAMPLES_FILE.read_text(encoding="utf-8")
    return brand_voice, style_examples


# ── module 1: keyword loader ───────────────────────────────────────────────────

def load_next_keyword() -> Optional[dict]:
    """
    Read the keyword masterlist CSV, skip any keyword whose slug already has
    a matching .txt in output/, sort remaining rows by Priority Tier
    (P1 → P2 → P3 → P4), and return the top row as a dict.
    Returns None if the file is missing or all keywords are written.
    """
    if not KEYWORDS_FILE.exists():
        print(f"Keyword masterlist not found: {KEYWORDS_FILE}")
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written_slugs = (
        {p.stem for p in OUTPUT_DIR.glob("*.txt")}
        | {p.stem for p in OUTPUT_DIR.glob("*.html")}
    )

    rows = []
    with KEYWORDS_FILE.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row = {k.strip(): v.strip() for k, v in row.items()}
            keyword = (
                row.get("Keyword")
                or row.get("keyword")
                or row.get("KEYWORD")
                or ""
            )
            if not keyword:
                continue
            slug = slugify(keyword)
            if slug in written_slugs:
                continue
            rows.append({**row, "_keyword": keyword, "_slug": slug})

    if not rows:
        print("All keywords have been written. Nothing to do.")
        return None

    # Identify the priority tier column (flexible naming)
    tier_col = next(
        (k for k in rows[0] if "tier" in k.lower() or "priority" in k.lower()),
        None,
    )
    tier_order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}

    def tier_key(r):
        if tier_col:
            return tier_order.get(r.get(tier_col, "P4").strip()[:2].upper(), 9)
        return 9

    rows.sort(key=tier_key)
    return rows[0]


# ── module 2: competitor research ─────────────────────────────────────────────

def fetch_serp(keyword: str) -> "list[dict]":
    """Call ValueSERP and return the organic_results list."""
    params = {
        "api_key": VALUESERP_API_KEY,
        "q": keyword,
        "gl": "us",
        "hl": "en",
        "num": 10,
    }
    try:
        resp = requests.get(
            "https://api.valueserp.com/search",
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("organic_results", [])
    except Exception as e:
        log_error("serp_fetch", keyword, str(e))
        print(f"  ValueSERP call failed: {e}")
        return []


def fetch_page(url: str) -> dict:
    """
    GET a competitor URL and extract structural content.
    Returns a result dict with status="ok" on success or status="blocked (reason)"
    on any failure. Never retries.
    """
    result = {
        "url": url,
        "title": "",
        "h1": "",
        "h2s": [],
        "h3s": [],
        "word_count": 0,
        "opening_paragraph": "",
        "status": "ok",
    }
    try:
        resp = requests.get(url, headers=FETCH_HEADERS, timeout=12)
        if resp.status_code != 200:
            result["status"] = f"blocked ({resp.status_code})"
            return result

        soup = BeautifulSoup(resp.text, "html.parser")

        result["title"] = (
            soup.title.string.strip() if soup.title and soup.title.string else ""
        )
        h1 = soup.find("h1")
        result["h1"] = h1.get_text(strip=True) if h1 else ""
        result["h2s"] = [h.get_text(strip=True) for h in soup.find_all("h2")]
        result["h3s"] = [h.get_text(strip=True) for h in soup.find_all("h3")]

        body_text = soup.get_text(separator=" ")
        result["word_count"] = len(body_text.split())

        first_p = soup.find("p")
        result["opening_paragraph"] = (
            first_p.get_text(strip=True)[:300] if first_p else ""
        )

    except Exception as e:
        result["status"] = f"blocked ({type(e).__name__}: {e})"

    return result


def research_competitors(keyword: str) -> "list[dict]":
    """Run SERP lookup then page fetch for each organic result."""
    print(f"  Fetching SERP for: {keyword}")
    organic = fetch_serp(keyword)

    if not organic:
        print("  No organic results returned from ValueSERP.")
        return []

    competitors = []
    for item in organic:
        url = item.get("link", "")
        if not url:
            continue
        print(f"  Fetching: {url[:75]}...")
        page = fetch_page(url)
        page["serp_title"]   = item.get("title", "")
        page["serp_snippet"] = item.get("snippet", "")
        competitors.append(page)
        time.sleep(0.5)

    ok_count = sum(1 for c in competitors if c["status"] == "ok")
    print(f"  Done - {ok_count}/{len(competitors)} pages fetched successfully.")
    return competitors


# ── module 3: blog post writer ─────────────────────────────────────────────────

def _build_competitor_summary(competitors: "list[dict]") -> str:
    lines = []
    for i, c in enumerate(competitors, 1):
        if c["status"] != "ok":
            lines.append(f"Competitor {i}: {c['url']} — {c['status']}")
            continue
        h2_text = "\n".join(f"    - {h}" for h in c["h2s"][:6]) or "    (none extracted)"
        lines.append(
            f"Competitor {i}: {c['url']}\n"
            f"  Title: {c['title']}\n"
            f"  H1: {c['h1']}\n"
            f"  H2s:\n{h2_text}\n"
            f"  Approx word count: {c['word_count']}\n"
            f"  Opening paragraph: {c['opening_paragraph']}"
        )
    return "\n\n".join(lines) if lines else "(No competitor data available.)"


def build_prompt(
    keyword_row: dict,
    competitors: list[dict],
    brand_voice: str,
    style_examples: str,
) -> str:
    keyword = keyword_row["_keyword"]

    tier_col = next(
        (k for k in keyword_row if "tier" in k.lower() or "priority" in k.lower()),
        None,
    )
    tier = keyword_row.get(tier_col, "").strip() if tier_col else ""

    competitor_summary = _build_competitor_summary(competitors)
    banned_list = ", ".join(BANNED_WORDS)

    return f"""You are the Blog SEO Agent for Switzertemplates.

Your job: write one complete, publish-ready blog post for switzertemplates.com.

TARGET KEYWORD: {keyword}
PRIORITY TIER: {tier}

---

BRAND VOICE AND STYLE — read every rule, apply all of them:

{brand_voice}

---

STYLE EXAMPLES — study the writing patterns, do not copy the text:

{style_examples}

---

COMPETITOR RESEARCH — understand what is already ranking, then write something better: more specific, more useful, more human:

{competitor_summary}

---

BLOG POST STRUCTURE:

1. Title
   - Contains the exact keyword naturally
   - Benefit-led, not clickbait
   - Under 60 characters for SEO
   - Sentence case only (capitalize first word and proper nouns only)
   - Always capitalize proper nouns and brand names exactly as they appear (e.g. Canva, Wix, Instagram, Pinterest, Etsy, Flodesk)

2. Introduction (100-150 words)
   - Opens with the reader's real frustration or situation
   - Must include the exact keyword naturally within the first paragraph
   - No "In this post I will..." or "Today we're going to cover..."
   - No grand opening statements
   - Start somewhere honest and move quickly to what the post delivers

3. Body: 4-6 sections with H2 headings
   - Each section: 150-250 words
   - One idea per section, fully delivered before moving on
   - Short sentences. One idea per sentence where possible.
   - Personal examples woven in naturally where they fit — never forced
   - H2 headings in sentence case

4. Mid-post CTA (one only)
   - Appears inside the body section where it fits most naturally
   - Tied directly to the problem that section is discussing
   - Format: "If you want a done-for-you version, the Switzertemplates [product name] includes [what it includes] - [specific benefit]."
   - Never a hard sell. Introduce it as a helpful option and move on.

5. Conclusion (100-150 words)
   - No "In conclusion" or "To wrap up"
   - Grounded, simple close — gives the reader something to do or think about
   - Must include the exact keyword naturally within the conclusion
   - Ends with a final CTA linking to a relevant product or the Etsy shop
   - CTA is action-led and specific, not "click here" or "shop now"

TARGET LENGTH: 1,200-1,800 words total.

---

NON-NEGOTIABLE VOICE RULES:

- Short sentences. Active voice. Plain language throughout.
- Use "you" and "your" constantly — this is always about the reader's business.
- Regular dashes ( - ) only. Never em dashes ( — ).
- Brackets for asides (like this) — never em dashes for asides.
- Sentence case for all headings. Do not capitalize every word.
- Always capitalize proper nouns and brand names: Canva, Wix, Instagram, Pinterest, Etsy, Flodesk, Google, etc.
- Use American English spelling throughout: color (not colour), recognize (not recognise), optimize (not optimise), customize (not customise), favorite (not favourite), center (not centre), etc.
- No rhetorical question-then-answer patterns.
- No "In today's post..." or "Let's talk about..." or "Let's dive in" openers.
- No announcing what you are about to teach — just teach it.
- Every sentence earns its place. Cut anything that does not add value.
- Light warmth and a small aside are welcome when they land naturally — never in CTAs or product mentions.
- Product mentions feel like recommendations, not pitches.

BANNED WORDS — do not use any of these under any circumstances:
{banned_list}

Also never use: "You've got this", "Level up", "Exciting news!", "Have you ever wondered", or the words clarity / alignment / journey / strategy without a concrete benefit immediately following.

---

OUTPUT FORMAT:

Return ONLY the blog post as clean HTML body content.
No preamble. No "Here is the HTML:". No meta-commentary at the start or end.
No <html>, <head>, or <body> tags — just the content that goes inside <body>.

Use these tags and no others:
- <h1> for the post title (one only, on the first line)
- <h2> for each section heading
- <p> for every paragraph
- <div class="cta"> for CTA blocks — any paragraph that mentions Switzertemplates products, links to the shop, or directs the reader to buy or browse

No markdown. No inline styles. No extra attributes. Clean semantic HTML only.
"""


def check_banned_words(text: str) -> list[str]:
    plain = re.sub(r"<[^>]+>", " ", text)
    lower = plain.lower()
    return [w for w in BANNED_WORDS if w.lower() in lower]


def write_blog_post(keyword_row: dict, competitors: list[dict]) -> str:
    """Call Claude to write the post. If banned words are found, request a revision."""
    brand_voice, style_examples = read_context_files()
    prompt = build_prompt(keyword_row, competitors, brand_voice, style_examples)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print("  Calling Claude (claude-opus-4-5) to write blog post...")

    initial = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    post_text = initial.content[0].text.strip()

    hits = check_banned_words(post_text)
    if hits:
        print(f"  Banned words found: {hits} - requesting revision...")
        revision_prompt = (
            f"The blog post contains these banned words: {hits}.\n"
            f"Rewrite the affected sentences to remove every instance of those words entirely. "
            f"Do not replace them with synonyms from the banned list. "
            f"Return only the complete revised blog post - no preamble.\n\n"
            f"{post_text}"
        )
        revised = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": post_text},
                {"role": "user", "content": revision_prompt},
            ],
        )
        post_text = revised.content[0].text.strip()

        still_hit = check_banned_words(post_text)
        if still_hit:
            log_error("banned_words", keyword_row["_keyword"], f"Banned words remain after revision: {still_hit}")
            print(f"  Banned words remain after revision: {still_hit} — logged and continuing.")

    return post_text


# ── module 4: output ───────────────────────────────────────────────────────────

IMAGE_PROMPT_SYSTEM = """You are generating image and infographic prompts for SwitzerTemplates blog posts.
Read the blog post content carefully before writing any prompt.
Every prompt must be specific to that post's topic, audience, and message.
Never default to the same scene or layout across posts.

---

BRAND COLOURS (use hex codes explicitly):
- Background: warm cream #F8F5F2
- Headings: near-black #262427
- Nodes, accents, borders: chocolate brown #8D6E63
- Connecting lines and rules: muted sand #A5988E
- Supporting text and secondary labels: warm taupe #BBB0AA

BRAND FONTS (infographics only - never write font names as visible text in the image):
- Headings and main labels: Noto Serif Display Light, sentence case
- Numbers, secondary labels, supporting phrases: Montserrat Regular,
  lowercase or small all caps with generous letter spacing

---

PHOTOGRAPHY RULES:

Read the blog post topic first. Choose a scene that directly reflects
what the reader is doing or trying to achieve. Never default to a
generic flat lay when the topic calls for something more specific.

SCENE DIRECTION BY TOPIC:
- Ecommerce / selling products: female entrepreneur packing orders,
  photographing products, reviewing sales on laptop, surrounded by
  packaging and product samples
- Branding / visual identity: mood board work, colour swatches,
  brand materials on desk, design work in progress
- Instagram / social media: phone in hand, content creation setup,
  scrolling or photographing
- Website templates: laptop open showing clean website, someone
  reviewing their site from behind or side
- Business planning: focused work at a beautiful desk, notebooks,
  planning materials
- Email marketing / funnels: laptop work, focused and calm energy
- Pinterest / SEO: content planning, analytics on screen (no
  readable text), pinning content
- General business: stylish female entrepreneur in a luxurious
  interior, working, on a call, or reviewing documents

PEOPLE - when including a person:
- Always female, face never visible - back, side profile, or
  hands and wrists only
- Business outfits: oversized blazers, tailored coats, wide-leg
  trousers, high heels
- Hair polished - low bun, loose waves, or claw clip
- When showing hands: long gel nails in nude, white French, or
  deep toned. Gold jewellery - rings, bracelets, gold watch or
  gold bangle

SIGNATURE PROPS (use selectively, not all at once):
- Starbucks iced latte or matcha in clear cup with green straw
- Apple MacBook in silver or space grey
- Apple AirPods Max in silver or space grey
- Productivity Planner by Intelligent Change - black linen hardcover
  with gold foil title and yellow and grey ribbon bookmarks, OR
  grey linen hardcover with silver foil title
- Matcha latte or latte in a ceramic or glass cup
- Gold jewellery as detail
- Tortoiseshell claw clip or hair accessories

SURFACES AND INTERIORS:
- Dark oak wood, marble, travertine, concrete - not always cream linen
- Luxurious interiors: arched mirrors, bouclé chairs, statement desks,
  large windows, clothes rails visible in background
- Mix of light cream scenes and dark moody chocolate brown scenes

PHOTOGRAPHY STYLE:
- Warm, editorial, quiet luxury - real and lived-in, not staged
- Natural window light with directional shadows, never studio lighting
- Kodak Portra 400 film aesthetic: warm colour grading, visible grain,
  slightly soft, not digitally sharp
- 35mm or 50mm lens, shallow depth of field
- Intentionally imperfect: one object slightly overlapping another,
  one element partially cropped at frame edge, uneven light with
  one corner brighter, visible surface texture
- Signs of real use: half-drunk coffee, pen rolled slightly off centre
- Something blurry in the foreground pulling depth into the shot
- Candid, not arranged - feels genuinely real

STRICT TEXT RULES FOR ALL PHOTOS:
- No text, writing, words, or labels anywhere in the image
- All notebooks completely blank and closed
- All screens face away or show only a dark reflection with no
  readable content
- No readable typography on any surface or object
End every photo prompt with this line:
no text, no words, no writing, no labels, no bright colours,
no gradients, no studio lighting, no stock photography look,
no digital sharpening, no visible screens with text.

Format: landscape, 16:9 ratio, high resolution.

---

INFOGRAPHIC RULES:

Read the post content first. Choose the layout that best fits what
the content is communicating. VARIETY IS MANDATORY - never use the
same layout twice in a row. No two consecutive posts should have
the same infographic structure. The layout must emerge from the
content, not from a default template.

Ask yourself before choosing: what shape or structure makes this
content clearest and most visually interesting?

LAYOUT MENU - choose freely based on content:

1. SERPENTINE FLOW CURVE
   When to use: journeys, discovery, evolution, things that rise
   and fall, before and after
   How: single thin S-curve or wave in muted sand #A5988E, small
   filled dots in chocolate brown #8D6E63 at natural points,
   labels alternating above and below. Noto Serif Display Light
   headings, Montserrat supporting phrases in warm taupe.

2. VERTICAL SPINE WITH ALTERNATING CONTENT
   When to use: sequential steps, processes, design stages
   How: thin vertical line in muted sand #A5988E down the centre,
   content alternates left and right at each point. Small precise
   dots as punctuation only - not large nodes. Numbers in Montserrat
   small all caps warm taupe, headings in Noto Serif near-black.

3. VENN DIAGRAM
   When to use: overlapping concepts, frameworks, intersecting ideas
   How: 2 or 3 thin hairline circles in muted sand #A5988E, no fill
   except very soft warm tint in overlap, labels inside circles in
   Noto Serif Display Light near-black, annotations outside in
   Montserrat lowercase warm taupe.

4. RADIAL DOT MAP
   When to use: one central concept with surrounding related ideas,
   word clusters, concept maps
   How: central word or phrase in Noto Serif Display Light large,
   thin hairline lines radiating outward in muted sand, small filled
   dots in chocolate brown at line ends, labels in Montserrat small
   all caps warm taupe.

5. ROUNDED PILL LIST
   When to use: lists of tips, steps, or items that benefit from
   visual separation and a softer feel
   How: items sit inside vertical or horizontal rounded rectangle
   outlines, thin hairline border in muted sand #A5988E, no fill.
   Number in Montserrat small warm taupe, heading in Noto Serif
   near-black, phrase in Montserrat lowercase warm taupe inside
   each pill.

6. TWO COLUMN COMPARISON
   When to use: contrasting two ideas, before vs after, myth vs truth
   How: canvas divided into two halves by a thin hairline in muted
   sand. Each half has its own heading in Noto Serif Display Light
   and list items in Montserrat lowercase. Optional: one side on
   cream, other side on deep sage or charcoal for contrast.

7. STARBURST CENTREPIECE
   When to use: a central concept that radiates outward, frameworks
   with one core idea
   How: thin decorative starburst or sunburst outline in muted sand
   #A5988E at the centre, central label in Noto Serif Display Light
   near-black, radiating labels in Montserrat small all caps
   warm taupe around the outside.

8. PYRAMID
   When to use: hierarchies, priorities, levels of importance
   How: thin hairline triangle in muted sand #A5988E divided into
   horizontal sections by thin rules, labels inside each section
   in Noto Serif Display Light near-black, secondary text in
   Montserrat lowercase warm taupe.

9. PURE TYPOGRAPHY GRID
   When to use: lists or frameworks where the words themselves are
   the strongest element, no visual anchor needed
   How: clean 2 or 3 column grid, thin hairline rules in muted sand
   dividing columns, each cell has number in Montserrat small warm
   taupe, heading in Noto Serif Display Light near-black, phrase in
   Montserrat lowercase warm taupe. Open negative space used
   intentionally.

10. HORIZONTAL ALTERNATING TIMELINE
    When to use: step by step processes where rhythm and alternation
    help the reader follow along
    How: thin horizontal line in muted sand across centre, small
    precise dots in chocolate brown at each point, odd items above,
    even items below. Number in Montserrat small chocolate brown,
    heading in Noto Serif Display Light near-black, phrase in
    Montserrat lowercase warm taupe.

RULES FOR ALL INFOGRAPHIC LAYOUTS:
- No dominant title - headings and subheadings only
- Noto Serif Display Light for all headings - sentence case,
  light weight, never bold
- Montserrat Regular for all numbers, labels, supporting phrases
- Thin hairline strokes only - never thick lines or filled shapes
  except small precise dots as punctuation
- Background: warm cream #F8F5F2 with subtle paper texture
  (deep sage or charcoal background acceptable when content calls
  for it - Venn diagrams, comparison layouts)
- Generous empty space - never fill the canvas entirely
- No gradients, no drop shadows, no decorative frames or boxes
  unless they are the chosen layout (rounded pills)
- No bright colours, no clipart icons, no background patterns
- No bold or heavy font weights anywhere
- Maximum 2 font styles
- Small dot or diamond ornaments between sections only when they
  add rhythm - nothing else decorative
- Feels like it was drawn by a thoughtful human designer, not
  generated by AI
- Format: landscape, 16:9 ratio always

---

OUTPUT FORMAT:
Return prompts in this exact format with no preamble:

HERO IMAGE:
[Topic-relevant scene using specific props and setting that match
the post content. Not a generic flat lay unless the topic genuinely
calls for it.]

SUPPORTING IMAGE 2:
[Different angle, moment, or mood from the same topic. Vary the
composition from the hero - if hero is overhead, this should be
elevated angle or close-up. Mix light and dark scenes.]

SUPPORTING IMAGE 3 (optional):
[Only include if it adds something genuinely distinct from the
first two. Skip if redundant.]

INFOGRAPHIC:
[State in one sentence which layout you chose and why. Then write
the full prompt including exact content points from the post.
Never use placeholder text. Never repeat the same layout as the
previous infographic you generated.]
"""


def generate_image_prompts(keyword: str, post_html: str) -> str:
    """Make a second Claude call to generate Nano Banana Pro image prompts for the post."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    plain_text = re.sub(r"<[^>]+>", " ", post_html)

    user_prompt = (
        f'Generate image prompts for a blog post about "{keyword}".\n\n'
        f"POST CONTENT:\n{plain_text[:3000]}\n\n"
        f"Generate:\n"
        f"- 1 hero image prompt (rectangular, landscape, 16:9)\n"
        f"- 1-2 supporting image prompts (rectangular, landscape, 16:9)\n"
        f"- 1 infographic prompt\n\n"
        f"Each prompt must be specific to this post's topic, mood, and visual concept — not generic.\n"
        f"Make each prompt detailed enough to paste directly into an AI image generator.\n\n"
        f"Format your response exactly like this, with no preamble:\n\n"
        f"HERO IMAGE:\n[detailed prompt]\n\n"
        f"SUPPORTING IMAGE 2:\n[detailed prompt]\n\n"
        f"SUPPORTING IMAGE 3 (optional):\n[detailed prompt]\n\n"
        f"INFOGRAPHIC:\n[detailed prompt]"
    )

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=IMAGE_PROMPT_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


def _assemble_html(title: str, body_content: str, image_prompts: str) -> str:
    safe_prompts = image_prompts.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 780px; margin: 60px auto; padding: 0 24px; color: #2d2d2d; line-height: 1.8; }}
  h1 {{ font-size: 2em; margin-bottom: 8px; }}
  h2 {{ font-size: 1.3em; margin-top: 48px; margin-bottom: 12px; border-bottom: 1px solid #e0d9d0; padding-bottom: 6px; }}
  p {{ margin: 0 0 20px 0; }}
  .cta {{ background: #f5f0ea; border-left: 3px solid #b5896a; padding: 16px 20px; margin: 32px 0; }}
  .image-prompts {{ background: #f9f9f7; border: 1px solid #e0d9d0; padding: 24px; margin-top: 60px; font-family: monospace; font-size: 0.9em; line-height: 1.6; white-space: pre-wrap; }}
  .image-prompts h3 {{ font-family: Georgia, serif; font-size: 1em; margin-bottom: 16px; color: #888; letter-spacing: 0.05em; text-transform: uppercase; }}
</style>
</head>
<body>
{body_content}
<div class="image-prompts">
<h3>Image Prompts for Nano Banana Pro</h3>
{safe_prompts}
</div>
</body>
</html>"""


def save_output(keyword_row: dict, post_html: str, image_prompts: str) -> str:
    """
    Assemble and write the post to output/<slug>.html, append to completed.json,
    and print a terminal summary. Returns the output filename.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # extract title from the <h1> tag for the HTML <title> element
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", post_html, re.IGNORECASE)
    title = title_match.group(1) if title_match else keyword_row["_keyword"]

    slug     = keyword_row["_slug"]
    filename = f"{slug}.html"
    out_path = OUTPUT_DIR / filename

    full_html = _assemble_html(title, post_html, image_prompts)
    out_path.write_text(full_html, encoding="utf-8")

    plain_text = re.sub(r"<[^>]+>", " ", post_html)
    word_count = len(plain_text.split())

    completed = []
    if COMPLETED_LOG.exists():
        try:
            completed = json.loads(COMPLETED_LOG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    completed.append({
        "keyword":         keyword_row["_keyword"],
        "date_written":    date.today().isoformat(),
        "word_count":      word_count,
        "output_filename": filename,
    })
    COMPLETED_LOG.write_text(json.dumps(completed, indent=2), encoding="utf-8")

    print(f"  Saved  : {out_path}")
    print(f"  Words  : {word_count:,}")
    print(f"  Log    : {COMPLETED_LOG}")

    return filename


# ── module 5: run ──────────────────────────────────────────────────────────────

def run():
    print("=" * 50)
    print("  Blog SEO Agent — Switzertemplates")
    print("=" * 50)

    # module 1
    print("\n[1/4] Loading next keyword...")
    try:
        keyword_row = load_next_keyword()
    except Exception as e:
        log_error("keyword_loader", "", str(e))
        print(f"  Keyword loader failed: {e}")
        return

    if keyword_row is None:
        return

    keyword = keyword_row["_keyword"]
    print(f"  Keyword : {keyword}")
    print(f"  Slug    : {keyword_row['_slug']}")

    # module 2
    print("\n[2/4] Researching competitors...")
    try:
        competitors = research_competitors(keyword)
    except Exception as e:
        log_error("competitor_research", keyword, str(e))
        print(f"  Competitor research failed: {e} — continuing without data.")
        competitors = []

    # module 3
    print("\n[3/4] Writing blog post...")
    try:
        post_html = write_blog_post(keyword_row, competitors)
    except Exception as e:
        log_error("blog_writer", keyword, str(e))
        print(f"  Blog post writing failed: {e}")
        return

    print("  Generating image prompts...")
    try:
        image_prompts = generate_image_prompts(keyword, post_html)
    except Exception as e:
        log_error("image_prompts", keyword, str(e))
        print(f"  Image prompt generation failed: {e} — saving post without prompts.")
        image_prompts = "(Image prompt generation failed.)"

    # module 4
    print("\n[4/4] Saving output...")
    try:
        filename = save_output(keyword_row, post_html, image_prompts)
    except Exception as e:
        log_error("output", keyword, str(e))
        print(f"  Output save failed: {e}")
        return

    plain_text = re.sub(r"<[^>]+>", " ", post_html)
    word_count = len(plain_text.split())
    print(f"\n{'=' * 50}")
    print(f"  Done.")
    print(f"  Keyword  : {keyword}")
    print(f"  File     : agents/blog-seo-agent/output/{filename}")
    print(f"  Words    : {word_count:,}")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    run()
