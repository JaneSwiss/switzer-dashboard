#!/usr/bin/env python3
"""
Blog SEO Agent — Switzertemplates
Picks the next keyword from the masterlist, researches competitors via ValueSERP,
writes a complete blog post via Claude, saves output, and logs completion.

Run with:
    python agents/blog-seo-agent/blog_seo_agent.py
"""

import csv
import hashlib
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Optional

import anthropic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from openai_images import generate_image_bytes


# ── paths ─────────────────────────────────────────────────────────────────────

ROOT        = Path(__file__).resolve().parents[2]
AGENT_DIR   = Path(__file__).resolve().parent
KEYWORDS_FILE   = AGENT_DIR / "keywords" / "switzertemplates_keyword_masterlist.csv"
OUTPUT_DIR      = ROOT / "posts"
LOGS_DIR        = AGENT_DIR / "logs"
COMPLETED_LOG   = LOGS_DIR / "completed.json"
ERROR_LOG       = LOGS_DIR / "errors.json"
BRAND_VOICE_FILE      = ROOT / "context" / "brand-voice.md"
STYLE_EXAMPLES_FILE   = ROOT / "context" / "content-style-examples.md"
PUBLISHED_POSTS_FILE  = ROOT / "context" / "published-posts.json"

load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY")
VALUESERP_API_KEY   = os.getenv("VALUESERP_API_KEY")
BING_API_KEY        = os.getenv("BING_API_KEY", "")
INDEXNOW_KEY        = os.getenv("INDEXNOW_KEY", "")
BLOG_BASE_URL       = os.getenv("BLOG_BASE_URL", "https://www.switzertemplates.com/blog")
SITE_URL            = "https://www.switzertemplates.com"
IMAGE_OUTPUT_DIR    = ROOT / "posts" / "images"

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
    posts_dir = ROOT / "posts"
    written_slugs = (
        {p.stem for p in OUTPUT_DIR.glob("*.txt")}
        | {p.stem.replace("-v2", "") for p in OUTPUT_DIR.glob("*.html")}
        | ({p.stem for p in posts_dir.glob("*.html")} if posts_dir.exists() else set())
        | {"canva-branding-kit", "starting-a-business-plan-template"}
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


def fetch_paa(keyword: str) -> "list[str]":
    """
    Fetch Google 'People Also Ask' questions for the keyword via ValueSERP.
    Returns a list of question strings — real questions real people type into Google.
    """
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
        return [
            item.get("question", "")
            for item in resp.json().get("related_questions", [])
            if item.get("question")
        ]
    except Exception as e:
        log_error("paa_fetch", keyword, str(e))
        return []


def fetch_reddit_questions(keyword: str) -> "list[str]":
    """
    Search Reddit via ValueSERP for real discussion threads about the keyword.
    Returns thread titles that are questions or describe a problem/situation.
    """
    params = {
        "api_key": VALUESERP_API_KEY,
        "q": f"{keyword} site:reddit.com",
        "gl": "us",
        "hl": "en",
        "num": 8,
    }
    try:
        resp = requests.get(
            "https://api.valueserp.com/search",
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        question_words = {"how", "what", "why", "when", "which", "can", "should", "is", "are", "does", "do", "will"}
        questions = []
        for r in resp.json().get("organic_results", []):
            title = r.get("title", "").strip()
            if title and ("?" in title or any(title.lower().startswith(w) for w in question_words)):
                questions.append(title)
        return questions[:6]
    except Exception as e:
        log_error("reddit_questions", keyword, str(e))
        return []


def gather_faq_questions(keyword: str) -> str:
    """
    Collect real questions about the keyword from Google PAA and Reddit.
    Returns a formatted string ready to include in the writing prompt.
    This ensures the blog FAQ is based on questions real people actually ask —
    not generic AI-generated filler.
    """
    paa = fetch_paa(keyword)
    time.sleep(0.4)
    reddit = fetch_reddit_questions(keyword)

    sections = []
    if paa:
        sections.append("GOOGLE 'PEOPLE ALSO ASK' (real questions from Google search):")
        for q in paa:
            sections.append(f"- {q}")
    if reddit:
        if sections:
            sections.append("")
        sections.append("REAL QUESTIONS FROM REDDIT THREADS:")
        for q in reddit:
            sections.append(f"- {q}")

    return "\n".join(sections) if sections else ""


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
        "body_excerpt": "",
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

        # Extract first 8 meaningful paragraphs for deeper content analysis
        meaningful_paras = [
            p.get_text(strip=True)
            for p in soup.find_all("p")
            if len(p.get_text(strip=True)) > 60
        ]
        result["body_excerpt"] = " ".join(meaningful_paras[:8])[:2000]

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


# ── module 2b: research helpers ───────────────────────────────────────────────

def count_words(text: str) -> int:
    """Count words after stripping HTML tags and markdown markers."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\*+", " ", clean)
    return len(clean.split())


def calculate_target_length(competitors: "list[dict]") -> "tuple[int, int]":
    """
    Return (min_words, target_words) based on competitor page word counts.
    Competitor word counts include nav/footer so we apply a 0.6 discount
    to estimate article-only length before scaling.
    Absolute floor is 1,800 words.
    """
    FLOOR = 1800
    raw_counts = [
        c["word_count"] for c in competitors
        if c["status"] == "ok" and c["word_count"] > 800
    ]
    if not raw_counts:
        return FLOOR, 2000

    # Discount page word count to approximate article-only length
    article_counts = [int(w * 0.6) for w in raw_counts]
    avg = sum(article_counts) / len(article_counts)
    top = max(article_counts)

    # Target = 10% above average, but at least match the longest competitor
    target = max(FLOOR, int(avg * 1.1), min(top, 3500))
    return FLOOR, target


def gather_research_snippets(keyword: str) -> str:
    """
    Run two extra SERP searches to collect recent snippets about the keyword.
    Uses SERP snippets only — no additional page fetches needed.
    Returns a formatted string ready to include in the research brief.
    """
    queries = [
        f"{keyword} statistics data 2025 2026",
        f"{keyword} tips examples guide",
    ]
    all_snippets = []
    for query in queries:
        results = fetch_serp(query)
        for r in results[:5]:
            snippet = r.get("snippet", "").strip()
            title = r.get("title", "").strip()
            url = r.get("link", "").strip()
            if snippet and len(snippet) > 40:
                all_snippets.append(f"[{title}]\n{snippet}\nSource: {url}")
        time.sleep(0.4)
    return "\n\n".join(all_snippets) if all_snippets else ""


def synthesize_research(
    keyword: str,
    competitors: "list[dict]",
    snippets: str,
    target_words: int,
) -> str:
    """
    One Claude call that turns competitor data + SERP snippets into a structured
    research brief. This brief is fed into the writing prompt so the post is
    genuinely more informative than what is currently ranking.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    competitor_summary = _build_competitor_summary(competitors)

    research_prompt = f"""You are a content researcher for Switzertemplates, a digital product business for female small business owners — service providers and coaches, but just as often product-based and ecommerce sellers. Let the keyword decide which of these this brief should speak to; don't default to coaching/service framing for topics that are naturally about products, ecommerce, or shipping.

Keyword to write about: {keyword}
Target post length: {target_words} words minimum

COMPETITOR CONTENT (top Google results):
{competitor_summary}

SUPPLEMENTARY RESEARCH SNIPPETS (recent web sources):
{snippets if snippets else "(No supplementary snippets retrieved.)"}

Create a research brief that the blog writer will use to write a post that is more specific, more useful, and more current than anything currently ranking. Include:

1. KEY INSIGHTS (5-8 points): The most important, specific, actionable things someone searching for "{keyword}" needs to know right now. Be concrete. No vague generalities.

2. CURRENT DATA & STATS (2025-2026): Any specific numbers, percentages, or facts from the research above that belong in the post. Flag the source URL for each. If no concrete stats were found, say so — do not invent numbers.

3. REAL EXAMPLES: Specific, relatable examples tailored to whichever small business owners this keyword is actually for — a Shopify/ecommerce keyword gets product-seller examples (inventory, shipping, checkout), a coaching/service keyword gets service-provider examples. Match the example to the topic, not a fixed default. Show what this looks like in practice.

4. ACTIONABLE STEPS: A concrete step-by-step breakdown the reader can actually follow. Not theory — real actions.

5. COMPETITOR GAPS: What are these competitor posts NOT covering well? Where is the advice thin, generic, or outdated? These are the areas where our post wins.

6. UNIQUE ANGLES (2-3): Fresh angles or perspectives that would make this post stand out and feel genuinely more useful to the reader.

7. DEPTH NOTE: Based on the competitor word counts, note what depth is needed to compete on this keyword.

Be specific and grounded. This brief will be handed directly to the writer. Return only the research brief — no preamble."""

    resp = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2500,
        messages=[{"role": "user", "content": research_prompt}],
    )
    return resp.content[0].text.strip()


# ── module 3: blog post writer ─────────────────────────────────────────────────

def _build_competitor_summary(competitors: "list[dict]") -> str:
    lines = []
    for i, c in enumerate(competitors, 1):
        if c["status"] != "ok":
            lines.append(f"Competitor {i}: {c['url']} — {c['status']}")
            continue
        h2_text = "\n".join(f"    - {h}" for h in c["h2s"][:8]) or "    (none extracted)"
        excerpt = c.get("body_excerpt", "")
        excerpt_preview = (excerpt[:600] + "...") if len(excerpt) > 600 else excerpt
        lines.append(
            f"Competitor {i}: {c['url']}\n"
            f"  Title: {c['title']}\n"
            f"  H1: {c['h1']}\n"
            f"  H2s:\n{h2_text}\n"
            f"  Approx word count: {c['word_count']}\n"
            f"  Opening paragraph: {c['opening_paragraph']}\n"
            f"  Body excerpt: {excerpt_preview}"
        )
    return "\n\n".join(lines) if lines else "(No competitor data available.)"


def get_existing_post_angles(keyword: str) -> str:
    """
    Find already-written posts on the same topic and extract their title,
    opening paragraph, and section headings so the new post can take a
    genuinely different angle and cover different ground.
    Matches on shared content pillar words (e.g. 'pinterest', 'coaching', 'branding').
    Scans both OUTPUT_DIR (current pipeline output) and the root posts/ directory
    (the actual published archive) — checking only one of these misses most posts.
    Returns a formatted string for the prompt, or empty string if nothing relevant found.
    """
    search_dirs = [d for d in (OUTPUT_DIR, ROOT / "posts") if d.exists()]
    if not search_dirs:
        return ""

    # Determine topic words from the keyword
    topic_words = {w.lower() for w in keyword.split() if len(w) > 3}
    topic_words -= {"with", "from", "your", "that", "this", "have", "will", "make"}

    seen_slugs = set()
    angles = []
    for directory in search_dirs:
        for html_path in directory.glob("*.html"):
            slug = html_path.stem
            if slug in seen_slugs:
                continue
            slug_words = set(slug.replace("-", " ").split())
            # Skip if no overlap with topic words
            if not topic_words & slug_words:
                continue
            seen_slugs.add(slug)
            try:
                from bs4 import BeautifulSoup as _BS
                soup = _BS(html_path.read_text(encoding="utf-8"), "html.parser")
                for el in soup.find_all("div", class_="image-prompts"):
                    el.decompose()
                h1 = soup.find("h1")
                title = h1.get_text(strip=True) if h1 else slug.replace("-", " ")
                # Get first meaningful paragraph
                paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 60]
                opening = paras[0][:300] if paras else ""
                # Section headings (h3) so the new post can cover different subtopics,
                # not just open differently
                headings = [h.get_text(strip=True) for h in soup.find_all("h3")][:8]
                if title and opening:
                    entry = f'- Post: "{title}"\n  Opening: "{opening}"'
                    if headings:
                        entry += f"\n  Sections covered: {', '.join(headings)}"
                    angles.append(entry)
            except Exception:
                continue

    if not angles:
        return ""

    return (
        "PREVIOUSLY WRITTEN POSTS ON THIS TOPIC — avoid repeating their angles, hooks, "
        "comparisons, structure, or section topics:\n\n"
        + "\n\n".join(angles)
        + "\n\nFor every item above: your post must open with a COMPLETELY DIFFERENT hook, "
        "use different examples, avoid the same comparisons, and cover DIFFERENT subtopics "
        "in the body sections than the ones already listed above. "
        "If a previous post leads with an income statistic, lead with something else entirely. "
        "Find an angle or subset of the topic the previous posts haven't covered yet — "
        "a different use case, a different stage of the reader's journey, a more specific "
        "audience, or a more advanced/beginner take. "
        "The reader may have read all previous posts — make this one teach them something new."
    )


def build_prompt(
    keyword_row: dict,
    competitors: list[dict],
    brand_voice: str,
    style_examples: str,
    research_brief: str = "",
    target_words: int = 2000,
    faq_questions: str = "",
    existing_angles: str = "",
    published_posts_list: str = "",
) -> str:
    keyword = keyword_row["_keyword"]

    tier_col = next(
        (k for k in keyword_row if "tier" in k.lower() or "priority" in k.lower()),
        None,
    )
    tier = keyword_row.get(tier_col, "").strip() if tier_col else ""

    # Notes column: pin/content inspiration uploaded by Jane
    notes = (keyword_row.get("Notes") or "").strip()

    competitor_summary = _build_competitor_summary(competitors)
    banned_list = ", ".join(BANNED_WORDS)

    notes_block = (
        "\nPIN INSPIRATION FROM JANE'S RESEARCH — angles and themes that already perform well on Pinterest for this keyword:\n"
        + notes
        + "\n\nUse these to inform the post's angle and what topics resonate with this audience.\n"
        + "Do not copy any titles or descriptions directly. Use them to understand what the reader cares about and what kind of content drives clicks for this keyword.\n\n---\n"
    ) if notes else ""

    faq_block = (
        "\nREAL QUESTIONS PEOPLE ASK — sourced from Google 'People Also Ask' and Reddit threads.\n"
        "These are the actual questions real people type. Use them as the basis for the FAQ section.\n"
        "Do not copy wording verbatim — rewrite each question naturally in your own words if needed.\n"
        "Only use questions that genuinely fit this post. Skip any that are off-topic or redundant.\n\n"
        + faq_questions
        + "\n\n---\n"
    ) if faq_questions else ""

    angles_block = (
        "\n" + existing_angles + "\n\n---\n"
    ) if existing_angles else ""

    # Body section count and per-section target scale with overall target length
    if target_words >= 3000:
        section_count = "6-8"
        section_words = "200-350"
    elif target_words >= 2500:
        section_count = "6-7"
        section_words = "200-300"
    else:
        section_count = "5-6"
        section_words = "200-250"

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

RESEARCH BRIEF — this was compiled from competitor analysis and live web research.
Use the insights, examples, data points, and actionable steps in this brief to make the post genuinely valuable and more useful than what is currently ranking.
Do not repeat competitor content — use this brief to go deeper, be more specific, and cover gaps competitors miss:

{research_brief if research_brief else "(No research brief available — write from general knowledge.)"}

---
{notes_block}{faq_block}{angles_block}COMPETITOR RESEARCH — structure and depth reference only (do not copy content):

{competitor_summary}

---

COMPETING SERVICES — NEVER MENTION:
Never recommend, name, or describe any third-party service that competes with Switzertemplates offerings.
This includes: Pinterest management agencies, Pinterest VAs, Pinterest management services offered by others,
branding agencies, website design agencies, Canva design services offered by competitors, or any
done-for-you service that Jane herself offers. If a post covers a topic where such services exist
(e.g. "how to make money on pinterest"), do NOT include "offer Pinterest management services" or similar
as a method or suggestion. The only Pinterest services to mention are Jane's own at pinterest.switzertemplates.com.

CTA RELEVANCE — CRITICAL:
Every CTA must be directly relevant to the post topic. Do not insert unrelated product CTAs.
- Pinterest posts → CTA to pinterest.switzertemplates.com only
- Website template posts → CTA to the Wix website templates page only
- Branding posts → CTA to the branding packages page only
- Do NOT add a branding kit CTA inside a Pinterest post
- Do NOT add a website template CTA inside an email marketing post
- The CTA must feel like a natural next step for someone who just read the post

---

INFORMATION CURRENCY — CRITICAL:
The current year is 2026. All information, advice, tools, statistics, and examples must be current as of 2026.
Do not write "2025" anywhere in the post — not in the title, not in headings, not in the body.
If a year must appear in the title or a heading, use 2026.
Do not include outdated platform features, deprecated tools, or old statistics.
If the research brief contains specific data points or stats with sources, use them.
If you reference a statistic or fact, make sure it reflects how these platforms and tools work today.

---

DEPTH AND VALUE REQUIREMENTS — CRITICAL:
Every section must deliver real, specific value. No generic advice that could apply to any business or topic.
- Include at least 2-3 concrete, real-world examples throughout the post, tailored to whichever small business owners this specific keyword is actually for — don't default to coaches/service providers when the topic is naturally about product-based or ecommerce businesses (e.g. a Shopify vs Wix post should draw examples from both product sellers and service providers, not just one)
- Include at least one actionable step-by-step breakdown in its own section
- Use specific numbers, percentages, or data points where the research brief provides them
- Call out at least one common mistake or misconception the reader is likely making right now
- Give the reader something they can act on today — not just theory

---

FORMATTING RULES - apply these exactly:

Title: Write in ALL CAPS literally. Example: HOW TO BUILD A BRAND THAT CONVERTS

Section headings: Write in ALL CAPS literally, same as the title. Mark each heading
by starting its line with "### " so it can be detected and converted to a proper
heading. Put a blank line before and after.
RIGHT example: ### WHY MOST BUSINESS PLANS END UP IN A DRAWER
WRONG (do not do this — Title Case, only first letter of each word capitalized):
### Why Most Business Plans End Up In A Drawer
This ALL CAPS rule applies to the title and EVERY section heading, including the
FAQ heading. Body text — every sentence, every paragraph — is the opposite: never
ALL CAPS, never Title Case. Capitalize only the first word of each sentence and
proper nouns (Pinterest, Wix, Canva, Etsy, Instagram, Google, etc). This distinction
matters: headings are always ALL CAPS, body text is always plain sentence case —
never mix the two up.

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

Do not use em dashes.
Write headings in ALL CAPS, each starting with "### " — see FORMATTING RULES above.

Structure:
- Introduction (150-200 words): the FIRST 1-2 sentences must give a direct, clear answer
  to the post's main question. State the answer plainly upfront — do not bury it.
  Example: "The fastest way to build a coaching business website is to start with a
  premade template, customise it to your brand, and publish it in a day rather than
  spending weeks building from scratch." Then open up to the reader's situation and
  frustration. Must include the exact keyword naturally. No "In this post I will..." openers.
- Body: {section_count} sections, each {section_words} words, one idea per section fully delivered.
  At least one section must be a step-by-step breakdown with numbered or listed steps.
  At least one section must include a real example showing what good looks like in practice.
  Personal examples woven in naturally.
- Mid-post CTA: one only, tied to the problem the section is discussing.
  Never a hard sell. Introduce it as a helpful option.
- FAQ SECTION — FREQUENTLY ASKED QUESTIONS: place this second-to-last, before the conclusion.
  Include 4-6 Q&A pairs. Questions must be based on the real questions provided above
  (from Google PAA and Reddit) — not invented. Use only questions that genuinely fit
  the post. Reword naturally if needed. Each answer is 2-4 sentences, specific and useful.
  Format: question as *italic text* on its own line, answer as a normal paragraph below it.
  Section heading: "### FREQUENTLY ASKED QUESTIONS" (ALL CAPS, same as other headings).
- Conclusion (150-200 words): no "In conclusion". Must include the exact keyword.
  Ends with a final CTA to a relevant product or the Etsy shop.

TARGET LENGTH: minimum {target_words:,} words. Write to this target — do not cut short.
If you reach {target_words:,} words and the post still has more value to deliver, keep writing.

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
- NEVER open a post by comparing Pinterest to Instagram (or to any other platform).
  This comparison has been overused across previous posts and is permanently banned
  as an opening hook, regardless of whether this is the first post on the topic.
  Open with the keyword's actual subject instead — a direct answer, a specific
  problem, a concrete number, or a real scenario. Save platform comparisons (if
  ever genuinely useful) for deep in the body, never the opening.
- Every sentence earns its place. Cut anything that does not add value.
- Light warmth and a small aside are welcome when they land naturally — never in CTAs or product mentions.
- Product mentions feel like recommendations, not pitches.

BANNED WORDS — do not use any of these under any circumstances:
{banned_list}

Also never use: "You've got this", "Level up", "Exciting news!", "Have you ever wondered", or the words clarity / alignment / journey / strategy without a concrete benefit immediately following.

---

CTA MAPPING — apply the correct CTA based on the post topic. Use the exact URLs below,
including the tracking parameters on the end — do not shorten or drop them:
- Post about Pinterest (marketing, strategy, services, management, agency, scheduling, analytics, growth, affiliate):
  → Mid-post CTA AND conclusion CTA must both link to https://pinterest.switzertemplates.com/?utm_source=blog&utm_medium=content&utm_campaign={keyword_row['_slug']}
  → Present it as Jane's done-for-you Pinterest marketing service ($699 strategy / $1,299 full setup)
- Post about Wix websites or website templates:
  → CTA to https://www.switzertemplates.com/premade-wix-website-templates-for-sale?utm_source=blog&utm_medium=content&utm_campaign={keyword_row['_slug']}
- Post about branding or branding kits:
  → CTA to https://www.switzertemplates.com/branding-packages?utm_source=blog&utm_medium=content&utm_campaign={keyword_row['_slug']}
- Post about business bundles or complete online presence:
  → CTA to https://www.switzertemplates.com/business-template-bundles?utm_source=blog&utm_medium=content&utm_campaign={keyword_row['_slug']}
- Post about coaching business (not specifically Pinterest):
  → CTA to https://www.switzertemplates.com/business-template-bundles?utm_source=blog&utm_medium=content&utm_campaign={keyword_row['_slug']}
- Post about Shopify or choosing an ecommerce platform/theme:
  → CTA to https://www.switzertemplates.com/shopify-theme-templates?utm_source=blog&utm_medium=content&utm_campaign={keyword_row['_slug']}
  Present as Jane's premade Shopify themes — full luxury ecommerce website designs done
  for you, not just a basic framework, with a mega menu, slide-out cart drawer, free
  shipping progress bar, and cart upsell suggestions built in. Never state the exact price
  (it changes) — "affordable"/"budget-friendly" is fine.

CROSSLINKING — REQUIRED:
These are the pages currently live on switzertemplates.com. If 2 or more of them are
genuinely relevant to this post's topic, you MUST link to at least 2 of them (up to 3)
somewhere in the body — this is not optional when relevant candidates exist.
"Relevant" means a reader following the link would land on a page that meaningfully
extends what they just read — not just any page that shares a keyword.
Spread the links across different sections rather than clustering them in one paragraph.
Anchor text must be a natural phrase in the sentence, not the page title verbatim.
Use the exact URL. Format: <a href="URL">anchor text</a>
If fewer than 2 of the pages below are genuinely relevant to this specific post, link
to as many as genuinely fit (including zero) — never force a link to an unrelated page.

{published_posts_list}

---

DALL-E IMAGE PROMPTS — REQUIRED:
Wherever a screenshot, UI example, or visual illustration would help the reader understand a step, tip,
or concept, insert a DALL-E prompt inline using this exact format on its own line:

[DALLE: A realistic mockup screenshot of ...]

Rules for DALL-E prompts:
- Include one wherever a real screenshot would replace 50+ words of explanation
- Ideal locations: step-by-step sections, "what it looks like" moments, before/after examples, tool walkthroughs
- Each prompt must be detailed enough that an AI image generator produces a convincing, specific result
- Every prompt MUST include all of these elements:
  1. Interface name (e.g. "Pinterest analytics dashboard", "Canva pin editor", "Tailwind scheduling calendar")
  2. Exact color scheme (e.g. "Pinterest red #e60023 and white", "Canva purple and white", "clean white UI with grey sidebar")
  3. Specific data or content shown (e.g. "Impressions: 847,293 with upward blue trend line", "showing 3 pin templates in vertical format", "a scheduled queue with 7 pins for the week")
  4. Layout details (e.g. "left sidebar navigation, main content area with grid", "top toolbar, canvas in center, layers panel on right")
  5. Format: "Landscape 16:9, high resolution, realistic flat UI design"
- Aim for 4-5 DALL-E prompts per post (minimum 2 if the topic genuinely doesn't support
  more) — every important step or concept mentioned should get a real illustration
- Each prompt must directly illustrate what is being described in that specific paragraph or section — not a generic image. A reader looking at the prompt should immediately understand which part of the post it belongs to.
- BAD example (too vague): [DALLE: A screenshot of Pinterest showing pins]
- GOOD example: [DALLE: A realistic mockup screenshot of the Pinterest analytics dashboard. Pinterest red (#e60023) top navigation bar, white background. Main stats panel shows: Impressions 847,293 with an upward trending blue line graph, Engagements 12,847, Outbound clicks 4,521, all in large bold numbers. Left sidebar shows navigation: Overview, Audience insights, Video, Conversion insights. Data is clearly readable. Landscape 16:9, flat modern UI design.]

---

OUTPUT FORMAT:

Return ONLY the blog post as plain text using the FORMATTING RULES above.
No preamble. No "Here is the post:". No meta-commentary at the start or end.
Include <a href> crosslinks inline where relevant.
Include [DALLE: ...] prompts inline where a screenshot would help.
Start with the title in ALL CAPS on the first line.
Use markdown bold (**), bold italic (***), and italic (*) exactly as specified.
Write section headings in ALL CAPS, each starting with "### ", on their own line
with a blank line before and after. Body text is always plain sentence case —
never ALL CAPS, never Title Case.
"""


def check_banned_words(text: str) -> list[str]:
    # Strip [DALLE: ...] image prompts first — they legitimately use words like
    # "landscape" (aspect ratio) and "discover" that would otherwise false-positive
    # against actual blog prose.
    without_prompts = re.sub(r"\[DALLE:.*?\]", " ", text, flags=re.DOTALL)
    plain = re.sub(r"<[^>]+>", " ", without_prompts)
    lower = plain.lower()
    return [w for w in BANNED_WORDS if w.lower() in lower]


def write_blog_post(keyword_row: dict, competitors: list[dict]) -> str:
    """
    Research → synthesize → write → validate → (retry if needed).
    Runs a research pipeline before writing so every post is genuinely
    informative, current, and more useful than what is ranking.
    """
    keyword = keyword_row["_keyword"]
    brand_voice, style_examples = read_context_files()
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # ── Step A: calculate target length from competitor data ──────────────────
    min_words, target_words = calculate_target_length(competitors)
    print(f"  Word count target: {target_words:,} words (minimum {min_words:,})")

    # ── Step B: gather supplementary research snippets + FAQ questions ───────
    print("  Gathering research snippets and FAQ questions...")
    try:
        snippets = gather_research_snippets(keyword)
        snippet_count = snippets.count("\n\n") + 1 if snippets else 0
        print(f"  {snippet_count} research snippet(s) collected.")
    except Exception as e:
        log_error("research_snippets", keyword, str(e))
        print(f"  Research snippets failed: {e} — continuing without.")
        snippets = ""

    try:
        faq_questions = gather_faq_questions(keyword)
        faq_count = faq_questions.count("\n- ") if faq_questions else 0
        print(f"  {faq_count} real FAQ questions sourced from Google PAA + Reddit.")
    except Exception as e:
        log_error("faq_questions", keyword, str(e))
        print(f"  FAQ question gathering failed: {e} — FAQ will be skipped.")
        faq_questions = ""

    # ── Step C: synthesize research brief ────────────────────────────────────
    print("  Synthesizing research brief...")
    try:
        research_brief = synthesize_research(keyword, competitors, snippets, target_words)
    except Exception as e:
        log_error("research_synthesis", keyword, str(e))
        print(f"  Research synthesis failed: {e} — writing without brief.")
        research_brief = ""

    # ── Step D: write the post ────────────────────────────────────────────────
    # Load existing post angles so Claude doesn't repeat the same hooks
    existing_angles = get_existing_post_angles(keyword)
    if existing_angles:
        angle_count = existing_angles.count("- Post:")
        print(f"  Found {angle_count} existing post(s) on similar topic — will avoid repeating their angles.")

    # Scrape live blog for published post URLs — always current, no manual maintenance
    published_posts_list = ""
    try:
        print("  Fetching live blog posts for crosslinking...")
        blog_resp = requests.get(
            "https://www.switzertemplates.com/blog",
            headers=FETCH_HEADERS,
            timeout=15,
        )
        if blog_resp.status_code == 200:
            from bs4 import BeautifulSoup as _BS
            blog_soup = _BS(blog_resp.text, "html.parser")
            live_posts = []
            for a in blog_soup.find_all("a", href=True):
                href = a["href"]
                if "/post/" in href:
                    full_url = href if href.startswith("http") else f"https://www.switzertemplates.com{href}"
                    title = a.get_text(strip=True)
                    if full_url not in [p["url"] for p in live_posts] and title:
                        live_posts.append({"title": title, "url": full_url})
            if live_posts:
                published_posts_list = "\n".join(
                    f'- {p["title"]} → {p["url"]}' for p in live_posts
                )
                print(f"  Found {len(live_posts)} published posts for crosslinking.")
    except Exception as e:
        # Fall back to static file if scrape fails
        try:
            import json as _json
            if PUBLISHED_POSTS_FILE.exists():
                posts = _json.loads(PUBLISHED_POSTS_FILE.read_text(encoding="utf-8"))
                published_posts_list = "\n".join(
                    f'- {p["title"]} → {p["url"]}' for p in posts
                )
                print(f"  Live scrape failed ({e}), using static fallback list.")
        except Exception:
            pass

    prompt = build_prompt(
        keyword_row, competitors, brand_voice, style_examples,
        research_brief=research_brief,
        target_words=target_words,
        faq_questions=faq_questions,
        existing_angles=existing_angles,
        published_posts_list=published_posts_list,
    )

    print(f"  Calling Claude (claude-opus-4-5) to write blog post ({target_words:,}+ words)...")

    initial = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    post_text = initial.content[0].text.strip()

    # ── Step E: word count check — retry once if under minimum ───────────────
    wc = count_words(post_text)
    print(f"  Draft word count: {wc:,}")
    if wc < min_words:
        print(f"  Under {min_words:,} words — requesting an expansion pass...")
        expansion_prompt = (
            f"This blog post is {wc} words but must be at least {min_words} words. "
            f"Expand it by adding more specific examples, more actionable detail, and deeper "
            f"explanations in the sections that are currently thin. "
            f"Do not add filler or padding — every added sentence must deliver real value. "
            f"Return only the complete expanded blog post — no preamble.\n\n"
            f"{post_text}"
        )
        expanded = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=8000,
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": post_text},
                {"role": "user", "content": expansion_prompt},
            ],
        )
        post_text = expanded.content[0].text.strip()
        wc = count_words(post_text)
        print(f"  Expanded word count: {wc:,}")
        if wc < min_words:
            log_error("word_count", keyword, f"Post still under {min_words} words after expansion: {wc}")
            print(f"  Still under {min_words:,} words after expansion — logged and continuing.")

    # ── Step F: banned word check — revision pass if needed ──────────────────
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
            max_tokens=8000,
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": post_text},
                {"role": "user", "content": revision_prompt},
            ],
        )
        post_text = revised.content[0].text.strip()

        still_hit = check_banned_words(post_text)
        if still_hit:
            log_error("banned_words", keyword, f"Banned words remain after revision: {still_hit}")
            print(f"  Banned words remain after revision: {still_hit} — logged and continuing.")

    return post_text


# ── module 4: output ───────────────────────────────────────────────────────────

IMAGE_PROMPT_SYSTEM = """You are generating image prompts for SwitzerTemplates blog posts.
Read the blog post content carefully. Every prompt must be specific to the post topic.

VARIETY IS NON-NEGOTIABLE. Each of the 5 images must feel like it was shot on a different
day, in a completely different place, with a different mood. If two images could plausibly
be from the same photoshoot or the same room, you have failed the brief. Push hard to
choose genuinely different environments — not just different corners of the same aesthetic.

---

WOMAN CHARACTER (when required in Prompts 1 and 3):
She is a beautiful, model-looking woman. Every image must feel like a high-end editorial shoot.

HAIR — choose a different style per post, always voluminous and polished:
- Long, voluminous chocolate brown waves with soft movement and shine
- Thick, voluminous dark brown hair in a loose low bun with face-framing pieces falling out
- Long glossy dark brown hair, straight with a subtle blowout volume at the roots
- Voluminous chocolate brown hair half-up, rest falling in soft waves
- Long rich brown hair loosely tucked behind one ear, voluminous and healthy-looking
Never flat, never straggly. Always thick, full, model-quality hair.

FACE — never fully visible. Back of head, side profile with jaw/cheekbone only, or hands/wrists only.

OUTFIT — one woman image must use a BOLD outfit, one must use a NEUTRAL outfit. Never repeat.
  Bold options: chocolate brown tailored blazer, black fitted turtleneck, rust coloured chunky knit,
    camel oversized coat with belt, dark grey fitted blazer, deep burgundy wrap top,
    forest green silk blouse, ivory structured blazer with gold buttons
  Neutral options: oversized cream cashmere knit, crisp white linen shirt open at collar,
    beige belted trench coat, white oversized sweatshirt, soft sage green cardigan,
    pale grey ribbed turtleneck, oatmeal coloured linen co-ord

NAILS + JEWELLERY — always include, always vary the combination:
- Nail options: long gel nails in nude, white French tip, soft pink, sheer glazed, champagne beige,
  milky white, or ballet pink — always long and perfectly shaped
- Jewellery options (mix 2-3 per image, vary across posts):
  thin gold chain necklace, layered delicate gold necklaces, chunky gold chain bracelet,
  thin stacked gold rings, single statement gold ring, pearl drop earrings,
  small gold hoop earrings, delicate gold cuff bracelet, thin gold bangles,
  tortoiseshell hair clip, gold hair pin, silk hair scarf loosely tied

TOPIC-RELEVANT PEOPLE (allowed in Prompt 3 only, for certain topics):
If the post is about coaching, consulting, mentoring, business strategy, or team work:
Prompt 3 MAY show two women in a professional conversation — one seen from behind
or side, the other partially visible. Or a small group in a professional setting where
faces are not shown. Must feel editorial and real, never corporate stock photo.

---

ENVIRONMENTS — pick a completely different type for each of the 5 images. Never repeat
the same environment category. Every environment must feel distinct in colour, light, and mood.

INDOOR — HOME SPACES:
- Bright home office with white arched window, sheer curtains moving in breeze, morning light flooding in
- Cosy reading nook with built-in bookshelves floor to ceiling, warm amber lamp, velvet armchair
- Bedroom with linen duvet, morning light casting long shadows across cream sheets
- Kitchen island in white marble, pendant lights above, fresh flowers on the counter
- Living room sofa in bouclé cream fabric, afternoon sun through plantation shutters, rug visible
- Walk-in wardrobe or dressing room, full-length mirror, clothes visible in background, editorial mood
- Bathroom vanity with travertine tiles, luxe products arranged neatly, soft diffused light

INDOOR — PROFESSIONAL AND CREATIVE SPACES:
- Modern co-working space with exposed ceiling beams, warm Edison pendants, brick wall
- Minimalist photography studio, white curved cove backdrop, single beauty dish light from side
- Boutique hotel suite sitting room, curved Art Deco armchair, dramatic drapes, evening lamp glow
- Luxury brand showroom or concept store interior, editorial, objects on pedestals, gallery white walls
- Dark moody office with floor-to-ceiling dark shelving, leather chair, warm amber lamp only light source
- Mid-century modern workspace, walnut desk, pendant Arco lamp, minimal and warm
- Glass-walled penthouse office, city blurred behind full-height windows, clean modern desk

OUTDOOR SPACES:
- Rooftop terrace with city skyline, golden hour light, terracotta pots, olive tree in planter
- Stone courtyard in Mediterranean villa, bougainvillea blurred behind, dappled morning light
- European cobblestone street, archway visible behind, woman captured mid-stride, golden light
- Lush garden, hedgerow blurred background, wrought iron table, very soft diffused light
- Beach-adjacent poolside at a luxury villa, sun lounger, blue water blurred behind, warm
- Verdant hotel garden terrace, rattan furniture, greenery everywhere, warm dappled shade
- City rooftop at dusk, string lights beginning to glow, warm purple-orange sky behind

CAFÉ AND HOSPITALITY — maximum ONE per post:
- Sleek all-white café with marble counter, minimalist pendant, single flower stem in vase
- Parisian café with mirrored walls, rattan chairs, marble bistro table, warm afternoon light
- Japanese-inspired café with pale timber, ceramic objects, stone surfaces, calm zen aesthetic
- Luxury hotel lobby bar, dramatic high ceilings, low leather seating, soft indirect lighting
- Rooftop café bar, city view behind, warm golden hour, elegant glassware on the table
- Coastal café, light wood, linen napkins, sea light, relaxed editorial feel

---

COMPOSITIONS — pick a completely different one for each of the 5 prompts. Never repeat any:
1. From behind at a desk — seated, hair cascading down back, room stretching into background
2. Overhead flat lay — no person, props and jewellery arranged loosely on a textured surface
3. Hands-only close-up — long gel nails in frame, rings and bracelets visible, mid-task action
4. Wide shot — woman very small in grand environment, architecture or landscape is the subject
5. Side profile — jaw and cheekbone edge visible, voluminous hair lit from window behind
6. Mid-action — woman leaning over desk or turning, hair caught in motion, candid energy
7. Over-shoulder — camera just behind her shoulder, nails visible on laptop or phone, work ahead
8. Low floor angle — shot from below desk level looking up slightly, legs and hem of outfit visible
9. Walking away — full rear view mid-stride through a beautiful space, coat hem or hair moving
10. Window silhouette — back of head against bright window, hair as silhouette with rim light on edges
11. Reclining — woman lying on sofa or bed, shot from above at angle, hair spread, book or phone in hand
12. Mirror reflection — woman seen in a decorative mirror, back to camera, reflection shows confidence not face
13. Staircase — woman on wide staircase from below, looking up at landing, architectural drama
14. Reading or writing — intense focus, face angled down, hair falling forward, pen or book in hand
15. Standing at window — full figure from behind at floor-to-ceiling window, city or garden outside

DRINKS — rotate, never repeat across the 5 prompts:
- Starbucks iced latte in clear cup with green straw
- Starbucks matcha in clear cup with green straw
- Iced brown sugar oat latte in clear cup
- Latte in a ribbed clear glass tumbler
- Espresso in a small white ceramic cup on a gold-rimmed saucer
- Matcha in a handmade speckled ceramic bowl
- Stanley tumbler in cream, cloud, or rose quartz
- Iced coffee in a plain clear glass with ice cubes
- Sparkling water in a glass bottle with a paper straw
- Freshly poured champagne in a crystal flute
- Glass of rosé, condensation on the outside
- No drink — leave it out entirely

SIGNATURE PROPS (use 1-2 per image, vary across ALL 5 images — never repeat the same prop twice in one post):
TECH:
- Apple MacBook Pro open on desk, screen showing a crisp, legible design or analytics dashboard
- Apple iPhone 15 Pro in natural titanium, face down or screen lit with crisp, legible content
- Apple AirPods Max in silver resting beside the laptop
- iPad Pro in a cream leather folio case, open with crisp, legible content

STATIONERY + BOOKS:
- Productivity Planner by Intelligent Change — black linen hardcover, gold foil lettering
- Large format art or fashion coffee table book, cover partially visible
- Open linen-covered notebook, blank pages, fine-tip pen lying across it
- Stack of 3-4 hardcover books in neutral tones, spines aligned
- Printed brand mood board showing colour swatches, editorial photos, type samples

BOTANICALS + VESSELS:
- Bouquet of white peonies or garden roses in a fluted glass vase
- Single long-stem white orchid in a minimal ceramic vase
- Dried pampas grass in a tall travertine vase
- Eucalyptus and olive branch arrangement in clear glass
- Small potted fiddle-leaf fig or monstera visible in background corner

BEAUTY + PERSONAL:
- Small amber glass luxury perfume bottle with gold cap on marble surface
- Silk scarf loosely draped over the edge of a chair or desk
- Designer sunglasses folded on the edge of the desk or chair arm
- Gold compact mirror open on a surface
- Small gold or marble tray holding a ring, bracelet, and perfume

CANDLES + DECOR:
- Tall pillar candle in a gold or concrete holder, unlit
- Cluster of 3 varying height candles in linen-toned vessels
- Single sculptural ceramic object in matte taupe or cream
- Small abstract sculpture or art object as desk accessory

PHOTOGRAPHY STYLE (consistent across all images):
- Warm editorial quiet luxury — real and lived-in, never staged or styled-looking
- Kodak Portra 400: warm colour grading, visible film grain, slightly soft focus
- Natural window light or outdoor natural daylight, directional shadows visible
- Shallow depth of field, foreground or background element softly blurred
- Intentionally imperfect: one element slightly cropped at frame edge,
  uneven light falloff, visible surface texture, real-world signs of use
- Candid energy throughout — feels genuinely real, not composed for a photoshoot

---

PROMPT 1 - GENERAL LIFESTYLE (woman present, bold outfit):
Woman is the subject. Scene loosely relates to the post theme but is not too literal.
MUST use a bold outfit from the bold options list.
Choose one environment from the full library above — any category.
Choose one composition from the list above.
State clearly: composition chosen, environment chosen, outfit chosen, drink chosen.
End with: No decorative signage or typography elsewhere in the scene. If a device screen
is visible, it may show crisp, legible, realistic content — do not blur or obscure it.
No distorted AI text, no garbled words. No bright colours, no gradients, no studio lighting,
no stock photography look, no digital sharpening. Landscape 16:9, high resolution.

PROMPT 2 - TOPIC SPECIFIC (props/objects, no person):
Directly illustrates the post topic through objects and scene only — no person needed.
Must be in a completely different environment category from Prompt 1.
Screen content is allowed and encouraged — relevant, crisp, legible UI (Pinterest feed grid,
Canva workspace, Etsy dashboard, website template editor), real and readable, not blurred.
Printed materials may show real, legible text relevant to the topic.
State clearly: composition chosen and environment chosen.
End with: No distorted AI text, no garbled words, no bright colours,
no gradients, no studio lighting. Landscape 16:9, high resolution.

PROMPT 3 - TOPIC SPECIFIC (person or people, neutral outfit):
Woman doing something directly related to the post — mid-action, not posed.
OR, if the post is about coaching, consulting, or team topics: two women in
professional conversation, or a small group, faces not visible.
MUST use a neutral outfit from the neutral options list.
Must be in a completely different environment category from Prompts 1 and 2.
Back or side profile only (for single woman). Faces never visible.
State clearly: composition, environment, outfit, drink, and whether single woman or group.
End with: No decorative signage or typography elsewhere in the scene. If a device screen
is visible, it may show crisp, legible, realistic content — do not blur or obscure it.
No distorted AI text, no garbled words. No bright colours, no gradients, no studio lighting,
no stock photography look, no digital sharpening. Landscape 16:9, high resolution.

PROMPT 4 - TOPIC FOCUS:
This image must directly and literally illustrate what the blog post is about.
It must be completely different in type from Prompts 1, 2, and 3.
Choose the image concept that makes the post topic immediately obvious to a viewer:

- Post about a digital platform or tool (Pinterest, Instagram, Canva, Etsy, email marketing, AI):
  Show an iMac, open MacBook, or phone with a relevant, realistic interface on screen.
  The device is the hero of the image. Place it on a styled desk or surface.
  Screen shows a crisp, legible, realistic UI — a Pinterest feed grid, Canva workspace,
  dashboard analytics, or email inbox layout — with real, readable text and numbers.

- Post about business strategy, coaching, planning, or content:
  Show a flat lay of business tools directly relevant to the topic — open planner,
  brand strategy notes, printed templates, colour swatches, mood board clippings,
  sticky notes, or a structured workspace layout. Objects must clearly relate to the
  specific topic, not generic stationery.

- Post about branding, design, or visual identity:
  Show brand identity materials laid out on a surface — logo mockup cards, colour
  palette swatches, font samples on paper, or printed design assets. Styled and editorial.

- Post about ecommerce, digital products, or online selling:
  Show digital product packaging mockups, a product listing on screen, or a styled
  arrangement of digital product previews printed and laid flat.

No character required for this image. Focus entirely on the concept, tools, or environment.
Choose a completely different setting and composition from Prompts 1, 2, and 3.
Same warm editorial aesthetic — Kodak Portra 400, natural light, real and lived-in.
End with: No decorative signage or typography elsewhere in the scene. If a device screen
is visible, it may show crisp, legible, realistic content — do not blur or obscure it.
No distorted AI text, no garbled words. No bright colours, no gradients, no studio lighting.
Landscape 16:9, high resolution.

PROMPT 5 - PINTEREST PIN:
A portrait-format image designed specifically to be used as a Pinterest pin background.
It must directly relate to the post topic — a viewer glancing at the pin should
immediately understand the subject.

Choose a composition that fills a tall portrait frame naturally:
- Woman from behind at a styled desk, shot from mid-distance, vertical crop
- A strong vertical flat lay — objects stacked or arranged top-to-bottom
- A tall product or device shot — iMac on a styled desk filling the frame vertically
- A person mid-action in a vertical interior scene — standing at a desk, at a window
- An evocative scene — warm light, strong vertical lines, editorial feel

The bottom third of the image should be relatively clear or softly blurred — text will
be overlaid there. The top two thirds carry the visual weight.
Same woman character rules apply if a person is included (long chocolate brown hair,
back or side profile only, different outfit from all other prompts in this post).
Same warm editorial aesthetic. Kodak Portra 400, natural window light.
End with: No text, no words, no writing, no labels, no readable typography anywhere
in the image. No distorted AI text. No bright colours, no gradients, no studio lighting.
Portrait 9:16, high resolution.

PROMPT 6 - INFOGRAPHIC:
Choose the layout that best fits the post content. VARIETY IS MANDATORY.
Options: serpentine flow curve, vertical spine, Venn diagram, radial dot map,
rounded pill list, two-column comparison, floating object grid,
horizontal alternating timeline, pure typography grid.
Never use the same layout as the previous post.

Brand colours:
- Background: warm cream #F8F5F2
- Headings: near-black #262427
- Nodes/accents: chocolate brown #8D6E63
- Lines: muted sand #A5988E
- Supporting text: warm taupe #BBB0AA

Font rules:
- Headings: Noto Serif Display Light, near-black #262427.
  First word of each heading in italic. Only first word capitalised, rest lowercase.
- Numbers: Montserrat Regular, small, all caps, warm taupe #BBB0AA
- Supporting phrases: Montserrat Regular, lowercase, warm taupe #BBB0AA
- Never write font names as visible text in the image
- Never bold any text. Thin hairlines only. Generous whitespace.
- Feels hand-designed and elegant, not generated. Landscape 16:9.

---

OUTPUT FORMAT - return exactly this, no preamble:

PROMPT 1 - GENERAL LIFESTYLE:
[prompt - state which composition, setting and drink you chose]

PROMPT 2 - TOPIC SPECIFIC (props/objects):
[prompt - state which composition and setting you chose]

PROMPT 3 - TOPIC SPECIFIC (person + action):
[prompt - state which composition, setting, outfit and drink you chose]

PROMPT 4 - TOPIC FOCUS:
[prompt - state which concept type you chose and why it fits this post topic]

PROMPT 5 - PINTEREST PIN:
[prompt - state which composition you chose and describe the vertical framing]

PROMPT 6 - INFOGRAPHIC:
[one sentence: layout chosen and why]
[full infographic prompt with all content points from the post]
"""


# Composition options that include the woman character — excludes "Overhead flat lay",
# which is explicitly a no-person composition (that's Prompt 2's territory).
# Every entry now bakes in a specific, non-laptop-default activity — composition alone
# wasn't enough. Entries that left the activity open (e.g. old "Side profile") reliably
# got filled in by Claude as "seated, typing on a laptop" regardless of what composition/
# environment were assigned — confirmed on a real generated cover for shopify-store-template.
_PERSON_COMPOSITIONS = [
    "From behind at a desk — seated, hands resting on a closed notebook (no laptop), hair cascading down back, room stretching into background",
    "Hands-only close-up — long gel nails in frame, holding or examining a small physical object relevant to the topic, not a device",
    "Wide shot — woman very small in grand environment, architecture or landscape is the subject, no task visible",
    "Side profile — jaw and cheekbone edge visible, holding a cup in both hands, looking toward the light, voluminous hair lit from window behind",
    "Mid-action — woman turning or mid-stride, hair caught in motion, candid energy, no device visible",
    "Over-shoulder — camera just behind her shoulder, scrolling on a phone held up at an angle, work ahead",
    "Low floor angle — shot from below desk level looking up slightly, legs and hem of outfit visible, hand resting on desk edge",
    "Walking away — full rear view mid-stride through a beautiful space, coat hem or hair moving",
    "Window silhouette — back of head against bright window, holding a warm drink, hair as silhouette with rim light on edges",
    "Reclining — woman lying on sofa or bed, shot from above at angle, hair spread, book or phone in hand",
    "Mirror reflection — woman seen in a decorative mirror, back to camera, reflection shows confidence not face",
    "Staircase — woman on wide staircase from below, looking up at landing, architectural drama, no task visible",
    "Reading or writing — intense focus, face angled down, hair falling forward, pen or book in hand, no laptop",
    "Standing at window — full figure from behind at floor-to-ceiling window, city or garden outside, no task visible",
]

_ENVIRONMENTS = [
    "Bright home office with white arched window, sheer curtains moving in breeze, morning light flooding in",
    "Cosy reading nook with built-in bookshelves floor to ceiling, warm amber lamp, velvet armchair",
    "Bedroom with linen duvet, morning light casting long shadows across cream sheets",
    "Kitchen island in white marble, pendant lights above, fresh flowers on the counter",
    "Living room sofa in bouclé cream fabric, afternoon sun through plantation shutters, rug visible",
    "Walk-in wardrobe or dressing room, full-length mirror, clothes visible in background, editorial mood",
    "Bathroom vanity with travertine tiles, luxe products arranged neatly, soft diffused light",
    "Modern co-working space with exposed ceiling beams, warm Edison pendants, brick wall",
    "Minimalist photography studio, white curved cove backdrop, single beauty dish light from side",
    "Boutique hotel suite sitting room, curved Art Deco armchair, dramatic drapes, warm lamp glow blended with soft daylight from a nearby window",
    "Luxury brand showroom or concept store interior, editorial, objects on pedestals, gallery white walls",
    "Moody office with floor-to-ceiling dark shelving, leather chair, warm amber lamp plus soft window light so the space still reads clearly",
    "Mid-century modern workspace, walnut desk, pendant Arco lamp, minimal and warm",
    "Glass-walled penthouse office, city blurred behind full-height windows, clean modern desk",
    "Rooftop terrace with city skyline, golden hour light, terracotta pots, olive tree in planter",
    "Stone courtyard in Mediterranean villa, bougainvillea blurred behind, dappled morning light",
    "European cobblestone street, archway visible behind, woman captured mid-stride, golden light",
    "Lush garden, hedgerow blurred background, wrought iron table, very soft diffused light",
    "Beach-adjacent poolside at a luxury villa, sun lounger, blue water blurred behind, warm",
    "Verdant hotel garden terrace, rattan furniture, greenery everywhere, warm dappled shade",
    "City rooftop at golden hour (not dusk), warm sunlit sky, string lights visible but not yet the light source",
    "Sleek all-white café with marble counter, minimalist pendant, single flower stem in vase",
    "Parisian café with mirrored walls, rattan chairs, marble bistro table, warm afternoon light",
    "Japanese-inspired café with pale timber, ceramic objects, stone surfaces, calm zen aesthetic",
    "Luxury hotel lobby bar, dramatic high ceilings, low leather seating, bright natural light from tall windows",
    "Rooftop café bar, city view behind, warm golden hour, elegant glassware on the table",
    "Coastal café, light wood, linen napkins, sea light, relaxed editorial feel",
]


# Prompt 2 (no person, props/objects) was never covered by the fix above and kept
# defaulting to "overhead flat lay" + MacBook + Productivity Planner on every single
# post — confirmed on shopify-store-template's real generated prompt. Same root cause
# (open choice, no cross-post memory), same fix: assign it instead of asking for it.
_OBJECT_COMPOSITIONS = [
    "Overhead flat lay on a textured surface, items arranged loosely",
    "Straight-on flat lay shot at a slight angle, items arranged in a loose diagonal line",
    "Close-up macro detail shot — one or two items filling most of the frame, shallow depth of field",
    "Side-lit arrangement on a low shelf or ledge, objects catching directional light",
    "Objects arranged on a windowsill, soft backlight from outside",
    "Styled vignette in the corner of a desk, items loosely grouped, rest of desk softly blurred",
]

_HERO_PROPS = [
    "Apple MacBook Pro open, screen showing a crisp, legible design or analytics dashboard",
    "Apple iPhone 15 Pro in natural titanium, screen lit with crisp, legible content",
    "iPad Pro in a cream leather folio case, open with crisp, legible content",
]

_ACCENT_PROPS = [
    "Productivity Planner by Intelligent Change — black linen hardcover, gold foil lettering",
    "Large format art or fashion coffee table book, cover partially visible",
    "Open linen-covered notebook, blank pages, fine-tip pen lying across it",
    "Stack of 3-4 hardcover books in neutral tones, spines aligned",
    "Printed brand mood board showing colour swatches, editorial photos, type samples",
    "Bouquet of white peonies or garden roses in a fluted glass vase",
    "Single long-stem white orchid in a minimal ceramic vase",
    "Small amber glass luxury perfume bottle with gold cap on marble surface",
    "Designer sunglasses folded on the edge of the desk or chair arm",
    "Tall pillar candle in a gold or concrete holder, unlit",
    "Cluster of 3 varying height candles in linen-toned vessels",
]


def _cover_assignment(keyword: str) -> dict:
    """Deterministically assigns composition + environment (+ props for Prompt 2) per
    cover prompt from the keyword, instead of leaving the choice to the model. Left free
    to choose, Claude reliably defaults to the same handful of scenes regardless of post
    topic — confirmed across roughly half of all real published posts for Prompts 1/3,
    and on every single post for Prompt 2 (always 'overhead flat lay' + MacBook + the
    same Productivity Planner).

    Uses independent chunks of an MD5 digest per axis (not a simple summed-character
    hash) — two real keywords ("how to set up shopify store" / "pinterest seo") produced
    an identical assignment under a plain sum, because their sums happened to differ by
    an exact multiple of both list lengths. MD5 chunks don't share that structural risk."""
    digest = hashlib.md5(keyword.strip().lower().encode()).hexdigest()
    return {
        "prompt1_composition": _PERSON_COMPOSITIONS[int(digest[0:8], 16) % len(_PERSON_COMPOSITIONS)],
        "prompt1_environment": _ENVIRONMENTS[int(digest[8:16], 16) % len(_ENVIRONMENTS)],
        "prompt3_composition": _PERSON_COMPOSITIONS[int(digest[16:24], 16) % len(_PERSON_COMPOSITIONS)],
        "prompt3_environment": _ENVIRONMENTS[int(digest[24:32], 16) % len(_ENVIRONMENTS)],
        "prompt2_composition": _OBJECT_COMPOSITIONS[int(digest[0:8], 16) % len(_OBJECT_COMPOSITIONS)],
        "prompt2_environment": _ENVIRONMENTS[int(digest[16:24], 16) % len(_ENVIRONMENTS)],
        "prompt2_hero_prop": _HERO_PROPS[int(digest[24:32], 16) % len(_HERO_PROPS)],
        "prompt2_accent_prop": _ACCENT_PROPS[int(digest[8:16], 16) % len(_ACCENT_PROPS)],
    }


def generate_image_prompts(keyword: str, post_html: str) -> str:
    """Make a second Claude call to generate Nano Banana Pro image prompts for the post."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    plain_text = re.sub(r"<[^>]+>", " ", post_html)
    assignment = _cover_assignment(keyword)

    user_prompt = (
        f'Generate image prompts for a blog post about "{keyword}".\n\n'
        f"POST CONTENT:\n{plain_text[:3000]}\n\n"
        f"Read the post content carefully. Every prompt must be specific to this "
        f"post's topic, audience, and message. Follow the output format exactly.\n\n"
        f"COMPOSITION, ENVIRONMENT, AND KEY PROPS ARE ASSIGNED, NOT YOUR CHOICE — this is "
        f"what keeps cover images across different blog posts from all looking the same:\n"
        f"- PROMPT 1 MUST use this composition: {assignment['prompt1_composition']}\n"
        f"- PROMPT 1 MUST use this environment: {assignment['prompt1_environment']}\n"
        f"- PROMPT 2 MUST use this composition/layout: {assignment['prompt2_composition']}\n"
        f"- PROMPT 2 MUST use this environment/surface: {assignment['prompt2_environment']}\n"
        f"- PROMPT 2's hero prop (the topic-relevant screen content lives on this): {assignment['prompt2_hero_prop']}\n"
        f"- PROMPT 2's one accent prop: {assignment['prompt2_accent_prop']}\n"
        f"- PROMPT 2 must NOT include a Productivity Planner or MacBook unless it is the "
        f"assigned hero/accent prop above — those two have appeared in nearly every post "
        f"and must not become the default again.\n"
        f"- PROMPT 3 MUST use this composition: {assignment['prompt3_composition']}\n"
        f"- PROMPT 3 MUST use this environment: {assignment['prompt3_environment']}\n"
        f"Everything else — hair, outfit, drink, screen content, mood — is still yours to "
        f"choose freely, grounded in the actual post content. Follow the assigned activity "
        f"described within each composition exactly — do not substitute a laptop or add "
        f"typing/desk work where the composition specifies something else.\n\n"
        f"TWO NON-NEGOTIABLE RULES FOR PROMPT 1 AND PROMPT 3, regardless of which composition "
        f"was assigned above:\n"
        f"1. TOPICAL ANCHOR — the scene must include at least one small, natural element that "
        f"visibly connects to this specific post's topic: a phone/tablet screen showing "
        f"something relevant, a printed page, a relevant product or object in hand or on a "
        f"nearby surface. A composition like 'walking away' or 'wide shot' or 'staircase' can "
        f"still include this — e.g. a phone held loosely in hand with a relevant screen visible, "
        f"or a relevant object glimpsed on a table in frame. NEVER produce a pure mood/lifestyle "
        f"shot with zero connection to the topic — that has happened before and is not allowed.\n"
        f"2. BRIGHTNESS FLOOR — the scene must be clearly and evenly lit. A single warm lamp, "
        f"dusk, or 'evening glow' as the only light source is too dark — confirmed unusable on a "
        f"real generated cover. Combine any warm/moody lighting with genuine daylight or bright "
        f"ambient light so the whole frame reads clearly, not just a small pool of light."
    )

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=IMAGE_PROMPT_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


def generate_images_from_prompts(prompt_text: str, slug: str) -> "tuple[list[str], float]":
    """
    Parse 3 cover-image prompts from the image prompt text and generate them via OpenAI.
    These are candidates Jane picks a Wix cover image from herself — not embedded inline.
    All 3 are landscape 16:9. (Prompts 4-5 from IMAGE_PROMPT_SYSTEM's output, if present,
    are intentionally unused — pin images now come from a separate pipeline entirely.)
    Saves .jpg files to posts/images/{slug}/cover-N.jpg and returns relative paths for
    HTML embedding (GitHub-Pages-facing copy only) plus a running cost estimate.
    Fails gracefully — any failed image is skipped, the post still saves.
    """
    slug_dir = IMAGE_OUTPUT_DIR / slug
    slug_dir.mkdir(parents=True, exist_ok=True)

    PHOTO_CONFIGS = [(1, "16:9"), (2, "16:9"), (3, "16:9")]

    # Match on "PROMPT N -...:" as a prefix rather than the full literal label text —
    # Claude doesn't always reproduce the exact parenthetical wording from the output
    # format spec (e.g. "(person):" instead of "(person + action):"), which silently
    # dropped that prompt entirely under the old exact-string match. Confirmed on a
    # real post (how-to-start-an-online-store) before this fix.
    parsed = []
    for n, aspect in PHOTO_CONFIGS:
        label_match = re.search(rf"PROMPT {n} -[^\n:]*:", prompt_text)
        if not label_match:
            parsed.append((None, aspect))
            continue
        start = label_match.end()
        next_label = re.search(r"PROMPT \d", prompt_text[start:])
        chunk = prompt_text[start:start + next_label.start()].strip() if next_label else prompt_text[start:].strip()
        parsed.append((chunk if chunk else None, aspect))

    if not any(p for p, _ in parsed):
        log_error("image_generation", slug, "No photo prompts found in prompt text")
        print("  No photo prompts parsed - skipping cover image generation.")
        return [], 0.0

    image_paths = []
    total_cost = 0.0
    total = sum(1 for p, _ in parsed if p)

    for idx, (prompt, aspect) in enumerate(parsed, 1):
        if not prompt:
            print(f"  Cover image {idx}: no prompt found, skipping")
            continue

        print(f"  Generating cover image {idx} ({aspect})... [{idx}/{total}]")

        try:
            image_bytes, cost = generate_image_bytes(prompt, aspect_ratio=aspect, quality="high")
            img_filename = f"cover-{idx}.jpg"
            img_path = slug_dir / img_filename
            with open(img_path, "wb") as f:
                f.write(image_bytes)
            image_paths.append(f"images/{slug}/{img_filename}")
            total_cost += cost
            print(f"  Saved: {img_filename}")
        except Exception as e:
            print(f"  Cover image {idx} failed: {e}")
            log_error("image_generation", slug, f"Cover prompt {idx}: {str(e)}")
            continue

    return image_paths, total_cost


def generate_inline_images(post_html: str, slug: str) -> "tuple[str, list[str], float]":
    """
    Find every [DALLE: prompt] marker Claude embedded inline while writing the post
    (illustrating specific steps/sections — UI mockups, tool walkthroughs), generate a
    real image for each via OpenAI, save it to posts/images/{slug}/inline-N.jpg, and
    replace the marker in place with a real <img> tag.

    Called right after write_blog_post() returns, before anything else touches the text —
    by the time _assemble_html() runs, there are no [DALLE: ...] markers left to convert
    into visible prompt-text boxes.

    Returns (updated_post_html, image_paths, total_cost). Fails gracefully per-marker —
    a failed image just leaves that [DALLE: ...] marker in place rather than losing the
    whole post (falls through to the existing dalle_block() text-box rendering as a
    visible fallback, rather than silently vanishing).
    """
    slug_dir = IMAGE_OUTPUT_DIR / slug
    slug_dir.mkdir(parents=True, exist_ok=True)

    matches = list(re.finditer(r"\[DALLE:(.*?)\]", post_html, flags=re.DOTALL))
    if not matches:
        return post_html, [], 0.0

    image_paths = []
    total_cost = 0.0
    result_parts = []
    last_end = 0

    for idx, m in enumerate(matches, 1):
        prompt = m.group(1).strip()
        print(f"  Generating inline image {idx} ({len(matches)} total)...")

        result_parts.append(post_html[last_end:m.start()])
        last_end = m.end()

        try:
            image_bytes, cost = generate_image_bytes(prompt, aspect_ratio="16:9", quality="low")
            img_filename = f"inline-{idx}.jpg"
            img_path = slug_dir / img_filename
            with open(img_path, "wb") as f:
                f.write(image_bytes)
            rel_path = f"images/{slug}/{img_filename}"
            image_paths.append(rel_path)
            total_cost += cost
            result_parts.append(
                f'<img src="{rel_path}" alt="" style="width:100%;margin:1.5rem 0;border-radius:4px;display:block;">'
            )
            print(f"  Saved: {img_filename}")
        except Exception as e:
            print(f"  Inline image {idx} failed: {e} — leaving prompt text as fallback")
            log_error("image_generation", slug, f"Inline prompt {idx}: {str(e)}")
            result_parts.append(m.group(0))  # keep the original [DALLE: ...] marker

    result_parts.append(post_html[last_end:])
    return "".join(result_parts), image_paths, total_cost


def extract_faq_schema(post_text: str) -> str:
    """
    Parse the FREQUENTLY ASKED QUESTIONS section from the raw post text and
    return a JSON-LD FAQPage script tag for embedding in <head>.
    Returns empty string if no FAQ section is found or no Q&A pairs can be parsed.
    """
    import json as _json

    # Locate the FAQ section — everything between the heading and the next heading or end.
    # Headings are marked with "### " (see _assemble_html) — must match that, not just
    # bare ALL-CAPS lines, otherwise this lookahead never fires and the last FAQ answer
    # swallows the entire next section's heading + text.
    faq_match = re.search(
        r'FREQUENTLY ASKED QUESTIONS[^\n]*\n(.*?)(?=\n#{1,6}\s|\n[A-Z][A-Z\s,]{3,}\n|\Z)',
        post_text,
        re.DOTALL,
    )
    if not faq_match:
        return ""

    faq_text = faq_match.group(1)

    # Questions are formatted as *Question text?* on their own line
    # Capture each question and the text that follows it until the next question
    question_re = re.compile(r'\*([^*\n]+)\*\s*\n(.*?)(?=\n\*[^*\n]+\*|\Z)', re.DOTALL)

    qa_pairs = []
    for m in question_re.finditer(faq_text):
        question = m.group(1).strip()
        answer_raw = m.group(2).strip()
        # Strip markdown markers, take first 2 paragraphs, normalise whitespace
        answer = re.sub(r'\*+', '', answer_raw)
        answer = "\n\n".join(answer.split("\n\n")[:2]).strip()
        answer = re.sub(r"<[^>]+>", "", answer)
        answer = " ".join(answer.split())
        if question and answer:
            qa_pairs.append((question, answer))

    if not qa_pairs:
        return ""

    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in qa_pairs
        ],
    }
    return (
        '<script type="application/ld+json">\n'
        + _json.dumps(schema, indent=2, ensure_ascii=False)
        + "\n</script>"
    )


def _assemble_html(title: str, post_html: str, image_prompts: str, image_paths: "list[str]" = None, faq_schema: str = "") -> str:
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

    # Convert "### Heading" marker lines to h3 — using an explicit marker instead of
    # an ALL-CAPS heuristic keeps heading detection correct regardless of letter case,
    # so headings can be written in sentence case without breaking HTML structure.
    lines = content.split('\n')
    processed = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('### '):
            heading_text = stripped[4:].strip()
            processed.append(f'<h3>{heading_text}</h3>')
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

    # Convert [DALLE: ...] blocks into styled prompt cards
    def dalle_block(m):
        prompt_text = m.group(1).strip().replace('<','&lt;').replace('>','&gt;')
        return (
            '<div style="background:#f0f4ff;border:1.5px solid #c5d3f5;border-radius:8px;'
            'padding:1rem 1.25rem;margin:1.5rem 0;font-family:\'Courier New\',monospace;font-size:12px;line-height:1.6;color:#333;">'
            '<p style="font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;'
            'color:#6b7bb5;margin:0 0 0.5rem;font-family:Arial,sans-serif;">DALL-E / ChatGPT image prompt</p>'
            f'<p style="margin:0;">{prompt_text}</p></div>'
        )
    content = re.sub(r'\[DALLE:(.*?)\]', dalle_block, content, flags=re.DOTALL)

    # Convert markdown bold-italic ***text*** to <strong><em>
    content = re.sub(r'\*\*\*(.*?)\*\*\*', r'<strong><em>\1</em></strong>', content)
    # Convert markdown bold **text** to <strong>
    content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
    # Convert markdown italic *text* to <em>
    content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', content)

    safe_prompts = image_prompts.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Build image block
    image_block = ""
    if image_paths:
        imgs = ""
        for path in image_paths:
            imgs += f'<img src="{path}" alt="" style="width:100%;margin:0 0 1.75rem;border-radius:4px;display:block;">\n'
        image_block = f'<div style="margin:0 0 2rem;">{imgs}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
{faq_schema}
{css}
</head>
<body>
<div class="post">
<h1>{title}</h1>
{image_block}
{content}
<hr>
<p class="closing-note">Let me know in the comments below if you want me to cover any branding or marketing topics in more depth, and I'll make sure to create a blog post about it in the future.</p>
<div class="image-prompts">
<div class="image-prompts-title">Cover image prompts (OpenAI)</div>
{safe_prompts}
</div>
</div>
</body>
</html>"""


def save_output(keyword_row: dict, post_html: str, image_prompts: str, image_paths: "list[str]" = None) -> str:
    """
    Assemble and write the post to output/<slug>.html, append to completed.json,
    and print a terminal summary. Returns the output filename.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Title is always the first non-empty line of the model's output (the prompt
    # instructs the title to lead the post). Extracting it this way — rather than
    # depending on Claude having wrapped it in a literal <h1> tag — means title
    # casing always reflects exactly what was written, with no silent fallback
    # to the raw keyword string.
    first_line = next((l.strip() for l in post_html.split("\n") if l.strip()), "")
    title = re.sub(r"^<h1[^>]*>|</h1>$|^#+\s*", "", first_line, flags=re.IGNORECASE).strip()
    if not title:
        title = keyword_row["_keyword"]
    # The title line is consumed here — strip it so it isn't duplicated as a
    # paragraph in the assembled body, which already renders it via <h1>.
    post_html = post_html.split("\n", 1)[1] if "\n" in post_html else ""

    slug     = keyword_row["_slug"]
    filename = f"{slug}.html"
    out_path = OUTPUT_DIR / filename

    faq_schema = extract_faq_schema(post_html)
    if faq_schema:
        faq_q_count = faq_schema.count('"@type": "Question"')
        print(f"  FAQ schema: {faq_q_count} question(s) embedded in <head>")
    full_html = _assemble_html(title, post_html, image_prompts, image_paths, faq_schema=faq_schema)
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

    # Update dashboard_data.json
    dashboard_file = ROOT / "dashboard_data.json"
    try:
        dashboard_data = json.loads(dashboard_file.read_text(encoding="utf-8"))
        posts = dashboard_data.get("blog_seo_agent", {}).get("posts", [])
        existing_keywords = [p.get("keyword", "").lower() for p in posts]

        if keyword_row["_keyword"].lower() not in existing_keywords:
            new_post = {
                "title": title,
                "keyword": keyword_row["_keyword"],
                "written": True,
                "published": False,
                "date": date.today().isoformat(),
                "url": f"https://janeswiss.github.io/switzer-dashboard/posts/{filename}",
                "source": (keyword_row.get("Source") or "").strip(),
            }
            posts.append(new_post)
            dashboard_data["blog_seo_agent"]["posts"] = posts
            dashboard_file.write_text(
                json.dumps(dashboard_data, indent=2),
                encoding="utf-8"
            )
            print(f"  Dashboard: added '{keyword_row['_keyword']}' to dashboard_data.json")
        else:
            print(f"  Dashboard: '{keyword_row['_keyword']}' already exists - skipping to preserve published status")

    except Exception as e:
        log_error("dashboard_update", keyword_row["_keyword"], str(e))
        print(f"  Dashboard update failed: {e} - continuing anyway")

    print(f"  Saved  : {out_path}")
    print(f"  Words  : {word_count:,}")
    print(f"  Log    : {COMPLETED_LOG}")

    return filename


# ── module 5: indexing submission ─────────────────────────────────────────────

def ping_google_sitemap() -> None:
    """Ping both sitemaps so Google picks up new blog posts immediately."""
    sitemaps = [
        f"{SITE_URL}/blog-posts-sitemap.xml",
        f"{SITE_URL}/sitemap.xml",
    ]
    for sitemap_url in sitemaps:
        try:
            resp = requests.get(
                f"https://www.google.com/ping?sitemap={sitemap_url}",
                timeout=10,
            )
            label = sitemap_url.split("/")[-1]
            print(f"  Google sitemap ping ({label}): {'sent' if resp.status_code == 200 else resp.status_code}")
        except Exception as e:
            print(f"  Google sitemap ping failed: {e}")


def submit_url_to_bing(post_url: str, keyword: str) -> None:
    """Submit the post URL directly to Bing via Webmaster Tools API."""
    if not BING_API_KEY:
        print("  Bing submission: skipped (add BING_API_KEY to .env)")
        return
    try:
        resp = requests.post(
            f"https://ssl.bing.com/webmaster/api.svc/json/SubmitUrl?apikey={BING_API_KEY}",
            json={"siteUrl": SITE_URL, "url": post_url},
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=15,
        )
        if resp.status_code == 200:
            print(f"  Bing direct submission: sent")
        else:
            print(f"  Bing direct submission: {resp.status_code} — {resp.text[:80]}")
    except Exception as e:
        print(f"  Bing submission failed: {e}")
        log_error("indexing_bing", keyword, str(e))


def submit_indexnow(post_url: str, keyword: str) -> None:
    """Submit via IndexNow — notifies Bing, Yandex, and other engines at once."""
    if not INDEXNOW_KEY:
        print("  IndexNow: skipped (add INDEXNOW_KEY to .env)")
        return
    try:
        payload = {
            "host": SITE_URL.replace("https://", "").replace("http://", ""),
            "key": INDEXNOW_KEY,
            "keyLocation": f"{SITE_URL}/{INDEXNOW_KEY}.txt",
            "urlList": [post_url],
        }
        resp = requests.post(
            "https://api.indexnow.org/indexnow",
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=15,
        )
        if resp.status_code in (200, 202):
            print(f"  IndexNow (multi-engine): sent")
        else:
            print(f"  IndexNow: {resp.status_code} — {resp.text[:80]}")
    except Exception as e:
        print(f"  IndexNow failed: {e}")
        log_error("indexing_indexnow", keyword, str(e))


def submit_for_indexing(slug: str, keyword: str) -> None:
    """
    Step 1 (runs now): ping Google sitemap — safe to call immediately.
    Steps 2-3 (full submission): Bing + IndexNow — use publish_indexing.py
    after you publish the post to Wix so the URL is actually live.
    """
    expected_url = f"{BLOG_BASE_URL}/{slug}"
    print(f"\n  Submitting for indexing...")
    ping_google_sitemap()
    print(f"  Post URL when live: {expected_url}")
    print(f"  Run after publishing to Wix: python3 publish_indexing.py {slug}")


# ── module 6: run ──────────────────────────────────────────────────────────────

def run(force_keyword: str = None, angle_note: str = None):
    print("=" * 50)
    print("  Blog SEO Agent — Switzertemplates")
    print("=" * 50)

    # module 1
    print("\n[1/5] Loading next keyword...")
    try:
        if force_keyword:
            # Build a minimal keyword_row from the forced keyword
            keyword_row = {
                "_keyword": force_keyword,
                "_slug": slugify(force_keyword),
                "Priority Tier": "P1 - Build first",
                "Content Pillar": "Pinterest Marketing",
                "Notes": "",
                "Source": "",
            }
            # Try to find it in the masterlist to get full metadata
            all_rows = load_next_keyword.__wrapped__() if hasattr(load_next_keyword, '__wrapped__') else None
            try:
                with KEYWORDS_FILE.open(newline="", encoding="utf-8-sig") as f:
                    import csv as _csv
                    for row in _csv.DictReader(f):
                        row = {k.strip(): v.strip() for k, v in row.items()}
                        kw = row.get("Keyword", "")
                        if kw.lower() == force_keyword.lower():
                            keyword_row = {**row, "_keyword": kw, "_slug": slugify(kw)}
                            break
            except Exception:
                pass
            if angle_note:
                keyword_row["Notes"] = angle_note
            print(f"  Forced keyword: {force_keyword}")
        else:
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
    print("\n[2/5] Researching competitors...")
    try:
        competitors = research_competitors(keyword)
    except Exception as e:
        log_error("competitor_research", keyword, str(e))
        print(f"  Competitor research failed: {e} — continuing without data.")
        competitors = []

    # module 3 (research + write)
    print("\n[3/5] Researching topic and writing blog post...")
    try:
        post_html = write_blog_post(keyword_row, competitors)
    except Exception as e:
        log_error("blog_writer", keyword, str(e))
        print(f"  Blog post writing failed: {e}")
        return None

    total_image_cost = 0.0

    print("  Generating inline section images...")
    try:
        post_html, inline_image_paths, inline_cost = generate_inline_images(post_html, keyword_row["_slug"])
        total_image_cost += inline_cost
        if inline_image_paths:
            print(f"  {len(inline_image_paths)} inline image(s) generated successfully.")
    except Exception as e:
        log_error("image_generation", keyword, str(e))
        print(f"  Inline image generation failed: {e} - continuing with prompt text as fallback.")

    print("  Generating image prompts...")
    try:
        image_prompts = generate_image_prompts(keyword, post_html)
    except Exception as e:
        log_error("image_prompts", keyword, str(e))
        print(f"  Image prompt generation failed: {e} — saving post without prompts.")
        image_prompts = "(Image prompt generation failed.)"

    print("\n[4/5] Generating cover images via OpenAI...")
    image_paths = []
    try:
        image_paths, cover_cost = generate_images_from_prompts(image_prompts, keyword_row["_slug"])
        total_image_cost += cover_cost
        if image_paths:
            print(f"  {len(image_paths)} cover image(s) generated successfully.")
        else:
            print(f"  No cover images generated - post will save without them.")
    except Exception as e:
        log_error("image_generation", keyword, str(e))
        print(f"  Cover image generation failed: {e} - continuing without them.")

    if total_image_cost:
        print(f"  Estimated image cost this post: ${total_image_cost:.2f}")

    # module 4
    print("\n[5/5] Saving output...")
    try:
        filename = save_output(keyword_row, post_html, image_prompts, image_paths)
    except Exception as e:
        log_error("output", keyword, str(e))
        print(f"  Output save failed: {e}")
        return None

    plain_text = re.sub(r"<[^>]+>", " ", post_html)
    word_count = len(plain_text.split())
    print(f"\n{'=' * 50}")
    print(f"  Done.")
    print(f"  Keyword  : {keyword}")
    print(f"  File     : posts/{filename}")
    print(f"  Words    : {word_count:,}")
    print(f"{'=' * 50}\n")

    # Push to GitHub so dashboard updates automatically, and so the per-post image
    # folder is actually reachable at the link the GM hands Jane later.
    print("\n  Pushing to GitHub...")
    push_ok = False
    try:
        import subprocess
        subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-m", f"add post: {keyword}"], cwd=ROOT, check=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=ROOT, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, check=True)
        print("  GitHub updated successfully.")
        push_ok = True
    except subprocess.CalledProcessError as e:
        print(f"  GitHub push failed: {e} - post saved locally, push manually if needed.")
        log_error("git_push", keyword, str(e))

    submit_for_indexing(keyword_row["_slug"], keyword)

    return {
        "filename": filename,
        "slug": keyword_row["_slug"],
        "keyword": keyword,
        "image_cost": total_image_cost,
        "push_ok": push_ok,
    }


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

- Section headings: rewrite every heading in ALL CAPS literally, same as the title.
  Example: "What Branding Means For Small Business" becomes
  "WHAT BRANDING MEANS FOR SMALL BUSINESS" (never Title Case — every letter capital,
  not just the first letter of each word).
  Mark each heading by starting its line with "### ", on its own line, with a
  blank line before and after it.
  Body text stays in plain sentence case — never ALL CAPS, never Title Case.

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

    print(f"  Generating images...")
    image_paths = []
    try:
        image_paths = generate_images_from_prompts(image_prompts, slug)
        if image_paths:
            print(f"  {len(image_paths)} image(s) generated.")
        else:
            print(f"  No images generated - assembling without images.")
    except Exception as e:
        log_error("image_generation", slug, str(e))
        print(f"  Image generation failed: {e} - assembling without images.")

    # Assemble with new HTML template
    full_html = _assemble_html(title, formatted_body, image_prompts, image_paths)

    # Save as v2 — never overwrites original
    v2_path = OUTPUT_DIR / f"{slug}-v2.html"
    v2_path.write_text(full_html, encoding="utf-8")
    print(f"  Saved: {v2_path}")
    print(f"  Done.")


def reformat_all_posts() -> None:
    """
    Batch reformat all original posts in the output directory.
    Skips any file whose stem ends with -v2 (already reformatted).
    """
    html_files = sorted([
        f for f in OUTPUT_DIR.glob("*.html")
        if not f.stem.endswith("-v2")
    ])

    if not html_files:
        print("No posts to reformat.")
        return

    total = len(html_files)
    print(f"Found {total} post(s) to reformat.\n")

    for i, file in enumerate(html_files, 1):
        slug = file.stem
        print(f"Processing {i}/{total}: {slug}...")
        try:
            reformat_existing_post(slug)
        except Exception as e:
            log_error("reformat_all", slug, str(e))
            print(f"  Failed: {e} — continuing to next post.")
        print()


if __name__ == "__main__":
    import argparse as _ap
    parser = _ap.ArgumentParser()
    parser.add_argument("--keyword", metavar="KEYWORD", help="Write a post for a specific keyword instead of the next in queue")
    args = parser.parse_args()
    if args.keyword:
        run(force_keyword=args.keyword)
    else:
        run()
