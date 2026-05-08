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

FORMATTING RULES - apply these exactly:

Title: Write in ALL CAPS literally. Example: HOW TO BUILD A BRAND THAT CONVERTS

Section headings: Write in ALL CAPS literally on their own line with a blank line
before and after. Example: WHY MOST BUSINESS PLANS END UP IN A DRAWER
Do NOT use ## or any markdown header symbols. Just the heading in capitals.

Emphasis:
- Use **bold** for important statements the reader must not miss
- Use ***bold italic*** for the single most important insight in each section
- Use *italic* for questions, callouts, and personal asides

Standalone questions: each on its own line as *italic text*
Example: *What does your customer have before they find you?*

Lists: when presenting 3 or more distinct items, format as HTML list:
<ul><li>item one</li><li>item two</li><li>item three</li></ul>
Only use for genuinely list-like content - not regular paragraphs.

Emojis: add 1-2 maximum where completely natural inline.
Good: 📥 before a download link, ✅ before a key checklist item.
Never at the start of a heading. Never forced.

CTAs: wrap the linked product or action phrase in **bold**

Do not use em dashes. Do not use markdown headers (##).
Write headings as plain ALL CAPS text on their own line.

Structure:
- Introduction (100-150 words): opens with the reader's real frustration or situation.
  Must include the exact keyword naturally. No "In this post I will..." openers.
- Body: 4-6 sections, each 150-250 words, one idea per section fully delivered.
  Personal examples woven in naturally.
- Mid-post CTA: one only, tied to the problem the section is discussing.
  Never a hard sell. Introduce it as a helpful option.
- Conclusion (100-150 words): no "In conclusion". Must include the exact keyword.
  Ends with a final CTA to a relevant product or the Etsy shop.

TARGET LENGTH: 1,200-1,800 words total.

---

NON-NEGOTIABLE VOICE RULES:

- Short sentences. Active voice. Plain language throughout.
- Use "you" and "your" constantly — this is always about the reader's business.
- Regular dashes ( - ) only. Never em dashes ( — ).
- Brackets for asides (like this) — never em dashes for asides.
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

Return ONLY the blog post as plain text using the FORMATTING RULES above.
No preamble. No "Here is the post:". No meta-commentary at the start or end.
No HTML tags. Start with the title in ALL CAPS on the first line.
Use markdown bold (**), bold italic (***), and italic (*) exactly as specified.
Write section headings in ALL CAPS on their own line with a blank line before and after.
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

IMAGE_PROMPT_SYSTEM = """You are generating image prompts for SwitzerTemplates blog posts.
Read the blog post content carefully. Every prompt must be specific to the post topic.

THE FEMALE CHARACTER (when a person appears):
- Always has long chocolate brown hair - this is non-negotiable
- Face never visible - back, side profile only
- Business outfits: oversized blazers, tailored coats, wide-leg trousers, high heels
- Hands: long gel nails in nude or white French, gold jewellery - rings, bangles, watch

SETTING VARIETY - rotate between these, never use the same setting twice in one post:
- White marble desk with gold accents, bright airy room
- Warm beige travertine surface, soft natural light
- Light grey minimal interior, large windows
- Cream linen surface, warm morning light
- Dark oak desk ONLY if explicitly relevant to the post topic - not the default

SIGNATURE PROPS (use 2-3 per image, varied across the 3 photos):
- Starbucks iced latte or matcha in clear cup with green straw
- Apple MacBook in silver or space grey
- Apple AirPods Max in silver
- Productivity Planner by Intelligent Change - black linen hardcover with gold foil
- Gold jewellery as detail
- Tortoiseshell claw clip

PHOTOGRAPHY STYLE (all images):
- Warm editorial quiet luxury - real and lived-in, not staged
- Kodak Portra 400: warm colour grading, visible grain, slightly soft
- Natural window light with directional shadows, never studio lighting
- 35mm or 50mm lens, shallow depth of field
- Intentionally imperfect: one element cropped at frame edge, uneven light,
  visible surface texture, signs of real use
- Format: landscape, 16:9 ratio, high resolution

---

PROMPT 1 - GENERAL LIFESTYLE:
A warm editorial scene relevant to the post theme but not too specific.
The woman with long chocolate brown hair is present - back or side profile.
Choose a setting from the variety list above - not dark oak.
Include 2-3 signature props relevant to the mood of the post.
End with: no text, no words, no writing, no labels, no bright colours,
no gradients, no studio lighting, no stock photography look, no digital sharpening.

PROMPT 2 - TOPIC SPECIFIC (prop/action focused):
Directly illustrates what the post is about. No person needed - just the relevant
objects and context. Examples by topic:
- Branding post: colour swatches, font cards, mood board elements on a desk
- Business plan post: printed A4 pages being written on, planner open
- Ecommerce post: products being packaged, shipping materials, small product boxes
- Instagram post: phone showing a clean Instagram feed, content creation setup
- Website template post: laptop open showing a clean minimal website design
- AI tools post: hands holding iPad showing an AI tool dashboard
For this prompt, visible screen content and relevant graphics ARE allowed -
they add context and relevance. No need to hide screens or blur content.
Be specific about what is on the screen or in the scene.

PROMPT 3 - TOPIC SPECIFIC (person + action):
The woman with long chocolate brown hair doing something directly related to the post.
Mid-action, not posed. Examples:
- Branding post: woman arranging colour swatches or reviewing brand board on iPad
- Business plan post: woman writing in a planner, pen in hand
- Ecommerce post: woman with long brown hair packing small products at a desk
- Instagram post: woman scrolling phone, content visible on screen
- Website template post: woman reviewing website on MacBook from behind
Back or side profile only. Include a relevant prop from the post topic.
For this prompt, visible screen content IS allowed.

PROMPT 4 - INFOGRAPHIC:
Format: landscape, 16:9 ratio always. Never portrait.

Use this layout for all infographics unless the content specifically
requires otherwise:

HORIZONTAL ALTERNATING TIMELINE:
- Background: warm cream #F8F5F2
- A thin horizontal line in muted sand #A5988E runs across the exact
  centre of the image
- Nodes: tiny filled circles only - no larger than 8px equivalent.
  They are punctuation marks on the line, not dominant shapes.
  Small, restrained, understated. Never large or bold.
- Items 01, 03, 05 are centred above the line, node touching the
  bottom of the text block
- Items 02, 04 are centred below the line, node touching the top
  of the text block

Each text block reads top to bottom in this exact order:
1. Number: Montserrat Regular, very small, generous letter spacing,
   chocolate brown #8D6E63 - strictly this colour, not blue, not grey
2. Heading: Noto Serif Display Light, all caps, medium size,
   near-black #262427 - strictly this colour, not blue, not charcoal
3. Supporting phrase: Montserrat Regular, lowercase, very small,
   warm taupe #BBB0AA, centred below the heading

Numbers are small and secondary. Headings are the main focus.
Supporting phrases are quiet and minimal.
Each block is compact, centred, and well-proportioned.
Generous horizontal spacing between the 5 nodes.
Generous vertical space between text blocks and the centre line.

Strictly forbidden in every infographic:
- No gradients
- No drop shadows
- No decorative borders or boxes
- No bright colours
- No clipart-style icons
- No background patterns
- No bold or heavy font weights
- No more than 2 font styles
- No thick lines of any kind
- No blue or grey tones in the numbers or headings

Feels like: designed by a professional human graphic designer.
Clean, spacious, refined, editorial.

---

OUTPUT FORMAT - return exactly this structure, no preamble:

PROMPT 1 - GENERAL LIFESTYLE:
[prompt]

PROMPT 2 - TOPIC SPECIFIC (props/objects):
[prompt]

PROMPT 3 - TOPIC SPECIFIC (person + action):
[prompt]

PROMPT 4 - INFOGRAPHIC:
[one sentence explaining layout choice and why]
[full prompt with all content points from the post]
"""


def generate_image_prompts(keyword: str, post_html: str) -> str:
    """Make a second Claude call to generate Nano Banana Pro image prompts for the post."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    plain_text = re.sub(r"<[^>]+>", " ", post_html)

    user_prompt = (
        f'Generate image prompts for a blog post about "{keyword}".\n\n'
        f"POST CONTENT:\n{plain_text[:3000]}\n\n"
        f"Read the post content carefully. Every prompt must be specific to this "
        f"post's topic, audience, and message. Follow the output format exactly."
    )

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=IMAGE_PROMPT_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


def _assemble_html(title: str, post_html: str, image_prompts: str) -> str:
    css = """
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body {
        font-family: Georgia, 'Times New Roman', serif;
        font-size: 17px;
        line-height: 1.85;
        color: #1a1a1a;
        background: #ffffff;
      }
      .post {
        max-width: 740px;
        margin: 0 auto;
        padding: 3.5rem 2rem 5rem;
      }
      h1 {
        font-family: Arial, Helvetica, sans-serif;
        font-size: 22px;
        font-weight: 700;
        letter-spacing: 0.05em;
        line-height: 1.3;
        text-transform: uppercase;
        margin: 0 0 2rem;
        color: #1a1a1a;
      }
      h3 {
        font-family: Arial, Helvetica, sans-serif;
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin: 3rem 0 0.75rem;
        color: #1a1a1a;
      }
      p {
        margin: 0 0 1.25rem;
      }
      p:empty { display: none; }
      strong { font-weight: 700; }
      em { font-style: italic; }
      a { color: #1a1a1a; text-decoration: underline; }
      ul {
        margin: 0 0 1.25rem 1.5rem;
        padding: 0;
      }
      ul li {
        margin-bottom: 0.4rem;
      }
      hr {
        border: none;
        border-top: 1px solid #e5e5e5;
        margin: 2.5rem 0;
      }
      .cta-block {
        background: #f7f5f2;
        border-radius: 6px;
        padding: 1.25rem 1.5rem;
        margin: 2rem 0;
        font-size: 16px;
      }
      .closing-note {
        font-style: italic;
        color: #666;
        font-size: 15px;
        margin-top: 2rem;
      }
      .image-prompts {
        background: #f9f9f7;
        border: 1px solid #e8e4de;
        border-radius: 6px;
        padding: 1.75rem 2rem;
        margin-top: 4rem;
        font-family: 'Courier New', monospace;
        font-size: 13px;
        line-height: 1.65;
        white-space: pre-wrap;
        color: #444;
      }
      .image-prompts-title {
        font-family: Arial, Helvetica, sans-serif;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #999;
        margin-bottom: 1.25rem;
      }
    </style>
    """

    # Process the post content
    import re

    content = post_html

    # Convert ALL CAPS lines that are headings to h3
    lines = content.split('\n')
    processed = []
    for line in lines:
        stripped = line.strip()
        # Detect ALL CAPS heading lines (not inside tags, not empty, mostly uppercase)
        if (stripped and
            not stripped.startswith('<') and
            len(stripped) > 3 and
            sum(1 for c in stripped if c.isupper()) / max(sum(1 for c in stripped if c.isalpha()), 1) > 0.8 and
            not stripped.startswith('http')):
            processed.append(f'<h3>{stripped}</h3>')
        else:
            processed.append(line)
    content = '\n'.join(processed)

    # Wrap loose paragraphs (lines not already in tags)
    paragraphs = content.split('\n\n')
    wrapped = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if para.startswith('<'):
            wrapped.append(para)
        else:
            # Handle line breaks within paragraph as separate <p> tags
            sub_lines = [l.strip() for l in para.split('\n') if l.strip()]
            for sub in sub_lines:
                if sub.startswith('<'):
                    wrapped.append(sub)
                else:
                    wrapped.append(f'<p>{sub}</p>')
    content = '\n'.join(wrapped)

    # Convert markdown bold-italic ***text*** to <strong><em>
    content = re.sub(r'\*\*\*(.*?)\*\*\*', r'<strong><em>\1</em></strong>', content)
    # Convert markdown bold **text** to <strong>
    content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
    # Convert markdown italic *text* to <em>
    content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', content)

    safe_prompts = image_prompts.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
{css}
</head>
<body>
<div class="post">
<h1>{title}</h1>
{content}
<hr>
<p class="closing-note">Let me know in the comments below if you want me to cover any branding or marketing topics in more depth, and I'll make sure to create a blog post about it in the future.</p>
<div class="image-prompts">
<div class="image-prompts-title">Image Prompts for Nano Banana Pro</div>
{safe_prompts}
</div>
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


def reformat_existing_post(slug: str) -> None:
    """
    Reads an existing post HTML, runs a Claude formatting pass to add proper
    formatting markers, generates new image prompts, reassembles with the new
    _assemble_html template, and saves as output/<slug>-v2.html.
    Does not touch completed.json or the original file.
    """
    original_path = OUTPUT_DIR / f"{slug}.html"
    if not original_path.exists():
        print(f"  File not found: {original_path}")
        return

    print(f"  Reading: {original_path}")
    raw = original_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")

    # Extract title from <h1>
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else slug.replace("-", " ")
    keyword = slug.replace("-", " ")

    # Remove image-prompts div, h1, closing-note — collect remaining body HTML
    body = soup.find("body")
    if not body:
        print("  Could not parse body content.")
        return

    for div in body.find_all("div", class_="image-prompts"):
        div.decompose()
    for div in body.find_all("div", class_="image-prompts-title"):
        div.decompose()
    for p in body.find_all("p", class_="closing-note"):
        p.decompose()
    if h1:
        h1.decompose()

    # Get plain text for the formatting call
    body_text = body.get_text(separator="\n").strip()

    # Claude pass 1: add formatting markers to the existing content
    print(f"  Reformatting content for: {keyword}")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    formatting_prompt = f"""You are reformatting an existing SwitzerTemplates blog post to add proper formatting markers.

The post is about: {slug.replace("-", " ")}

FORMATTING RULES TO APPLY:

- Section headings: rewrite every heading in ALL CAPS letters literally.
  Example: "What branding means for small business" becomes
  "WHAT BRANDING MEANS FOR SMALL BUSINESS".
  No markdown symbols. Just the heading text written entirely in capital
  letters on its own line, with a blank line before and after it.

- Use **bold** for important statements the reader must not miss

- Use ***bold italic*** for the single most important insight in each section

- Use *italic* for questions, callouts, and personal asides

- Standalone questions: format each on its own line as *italic text*
  Example: *What does your customer have before they find you?*

- Lists: where the post already has 3 or more items listed within a paragraph,
  convert them to a proper HTML unordered list using <ul><li>item</li></ul> tags.
  Only convert genuinely list-like content - not regular paragraphs.
  Each list item should be concise - one line per item.

- Emojis: add 1-2 maximum where they feel completely natural inline.
  Good uses: 📥 before a download link, ✅ before a key checklist item.
  Never at the start of a heading. Never forced.

- CTAs: wrap the linked product name or action phrase in **bold**

- Do NOT change the actual words, sentences, or meaning - only add formatting markers
- Do NOT add new content - only format what is already there
- Do NOT include the post title - only return the body content
- Keep all paragraph breaks as they are

PROMPT 4 - INFOGRAPHIC NOTES (context only - do not generate infographic here):
- Nodes must be tiny - small filled dots only, never large circles

Return only the reformatted post body. No preamble. No commentary. Just the body.

EXISTING POST CONTENT:
{body_text}"""

    try:
        fmt_response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            messages=[{"role": "user", "content": formatting_prompt}],
        )
        formatted_body = fmt_response.content[0].text.strip()
    except Exception as e:
        print(f"  Formatting pass failed: {e}")
        return

    # Claude pass 2: generate new image prompts
    print(f"  Generating new image prompts for: {keyword}")
    try:
        image_prompts = generate_image_prompts(keyword, formatted_body)
    except Exception as e:
        print(f"  Image prompt generation failed: {e}")
        return

    # Assemble with new HTML template
    full_html = _assemble_html(title, formatted_body, image_prompts)

    # Save as v2 — never overwrites original
    v2_path = OUTPUT_DIR / f"{slug}-v2.html"
    v2_path.write_text(full_html, encoding="utf-8")
    print(f"  Saved: {v2_path}")
    print(f"  Done.")


if __name__ == "__main__":
    reformat_existing_post("branding-for-business")
