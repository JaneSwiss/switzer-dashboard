#!/usr/bin/env python3
"""
Email Agent — Switzertemplates
Writes full email campaigns ready to paste into Flodesk.

Usage:
  python3 agents/email-agent/email_agent.py --research
  python3 agents/email-agent/email_agent.py --re-engagement
  python3 agents/email-agent/email_agent.py --blog-post <slug>
  python3 agents/email-agent/email_agent.py --product bundle|website|branding-kit|instagram-templates|design-vault
  python3 agents/email-agent/email_agent.py --weekly

Requirements (on top of base pip installs):
  pip install youtube-transcript-api scrapetube
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
POSTS_DIR = ROOT / "posts"
OUTPUT_DIR = ROOT / "outputs" / "emails"
CONTEXT_DIR = ROOT / "context"
BRAND_VOICE_FILE = CONTEXT_DIR / "brand-voice.md"
PRODUCT_CATALOG_FILE = CONTEXT_DIR / "product-catalog.md"
EMAIL_PRINCIPLES_FILE = CONTEXT_DIR / "email-copywriting-principles.md"

load_dotenv(ROOT / ".env")

BLOG_BASE_URL = os.getenv("BLOG_BASE_URL", "https://www.switzertemplates.com/post")

PRODUCT_URLS = {
    "bundle": "https://www.switzertemplates.com/business-template-bundles",
    "website": "https://www.switzertemplates.com/premade-wix-website-templates-for-sale",
    "branding-kit": "https://www.switzertemplates.com/branding-packages",
    "instagram-templates": "https://www.switzertemplates.com/instagram-templates",
    "design-vault": "https://www.switzertemplates.com/join-design-vault",
    "pinterest-services": "https://pinterest.switzertemplates.com",
}

# Extra context for products not covered in product-catalog.md
PRODUCT_SUPPLEMENTS = {
    "pinterest-services": """Pinterest Marketing Services — done-for-you Pinterest management by Jane.

Two packages:
- $699: Pinterest Strategy — full account audit, keyword research, board optimisation,
  90-day content plan, and pin templates tailored to the business
- $1,299: Pinterest Strategy + Setup — everything in the strategy package plus full
  account setup, board creation, 30 pins designed and scheduled, Tailwind configuration

Who it's for: business owners who want Pinterest traffic but don't have the time or
expertise to manage it themselves. They already have a product or service to sell —
they just need the traffic system built.

Key selling angles:
- Done-for-you — no learning curve, no monthly guesswork
- Pinterest is a long-game channel but the setup needs to be right from the start
- Jane runs her own top-performing Pinterest account — she knows what works
- $699 entry point is low relative to the traffic value Pinterest delivers over time

Audience note: past buyers of templates are warm leads — they already invest in
looking professional. Pinterest services is the next natural step for those who
want to grow their reach without spending more time on content.""",
}

CHANNEL_HANDLES = [
    ("Maxwell Copy", "@maxwellcopy"),
    ("Alex Cattoni", "@AlexCattoni"),
]


# ── helpers ───────────────────────────────────────────────────────────────────

def make_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not found in .env")
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key)


def load_context() -> dict:
    ctx = {}
    ctx["brand_voice"] = BRAND_VOICE_FILE.read_text(encoding="utf-8") if BRAND_VOICE_FILE.exists() else ""
    ctx["product_catalog"] = PRODUCT_CATALOG_FILE.read_text(encoding="utf-8") if PRODUCT_CATALOG_FILE.exists() else ""
    ctx["email_principles"] = EMAIL_PRINCIPLES_FILE.read_text(encoding="utf-8") if EMAIL_PRINCIPLES_FILE.exists() else ""
    return ctx


def extract_post(slug: str) -> dict:
    html_path = POSTS_DIR / f"{slug}.html"
    if not html_path.exists():
        print(f"Post not found: {html_path}")
        sys.exit(1)

    raw = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")

    for el in soup.find_all("div", class_="image-prompts"):
        el.decompose()
    for el in soup.find_all("p", class_="closing-note"):
        el.decompose()

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else slug.replace("-", " ").title()
    if h1:
        h1.decompose()

    body = re.sub(r"\n{3,}", "\n\n", soup.get_text(separator="\n").strip())
    return {"title": title, "body": body[:3000], "url": f"{BLOG_BASE_URL}/{slug}"}


def get_latest_post() -> str:
    html_files = [f for f in POSTS_DIR.glob("*.html") if f.is_file()]
    if not html_files:
        print("No blog posts found in posts/")
        sys.exit(1)
    return max(html_files, key=lambda f: f.stat().st_mtime).stem


def save_output(content: str, email_type: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = OUTPUT_DIR / f"{date_str}-{email_type}.md"
    counter = 1
    while out_path.exists():
        out_path = OUTPUT_DIR / f"{date_str}-{email_type}-{counter}.md"
        counter += 1
    out_path.write_text(content, encoding="utf-8")
    return out_path


def call_claude(client: anthropic.Anthropic, prompt: str, max_tokens: int = 1200) -> str:
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ── prompt building ───────────────────────────────────────────────────────────

def system_block(ctx: dict) -> str:
    principles_section = ""
    if ctx["email_principles"]:
        principles_section = f"\n\nEMAIL COPYWRITING PRINCIPLES (apply these):\n{ctx['email_principles'][:2000]}"

    return f"""You are the email copywriter for Switzertemplates, a digital product business selling
Canva templates, Wix websites, and branding kits to female small business owners.

BRAND VOICE — follow these rules exactly:
{ctx['brand_voice'][:1800]}

PRODUCT CATALOG:
{ctx['product_catalog'][:2000]}{principles_section}

OUTPUT FORMAT — use this exact structure, nothing before or after:

SUBJECT LINE A: [under 50 chars]
SUBJECT LINE B: [under 50 chars — different angle, not just a rewording]
PREVIEW TEXT: [under 90 chars — adds to subject line, never repeats it]

---

BODY:

[email body here]

Xo Jane

---

FLODESK NOTES:
Segment: [who should receive this]
CTA button label: [action-led and specific — not "click here" or "shop now"]
CTA link: [full URL — always switzertemplates.com, never Etsy]"""


# ── writing modes ─────────────────────────────────────────────────────────────

def write_pinterest_urgent(client: anthropic.Anthropic, ctx: dict) -> str:
    prompt = f"""{system_block(ctx)}

TASK: Write a product email for Pinterest Marketing Services — done-for-you Pinterest management by Jane.

URGENCY CONTEXT:
- Jane is opening spots for her next client cohort — exactly 5 spots available
- She handles all client work personally (not a team), so spots are genuinely limited
- Once the 5 spots fill, the next availability is the following month
- The first email announcing this service went out and got minimal response — this follow-up
  email needs a completely different angle to drive action

Product details:
{PRODUCT_SUPPLEMENTS['pinterest-services']}

Email requirements:
- Lead with the PROBLEM: they have a Pinterest account but it's either sitting idle or not
  converting — they set it up, posted a few times, and then it just... stopped
- Make the scarcity feel personal and real — Jane does this herself, 5 spots, period
- Reference her own Pinterest account as the proof: it drives thousands of clicks to her
  shop every month — she knows what works because she lives it
- Paint a picture of what Pinterest looks like when it's working: traffic showing up months
  later from pins posted years ago, clicks while they sleep, leads they didn't have to chase
- The urgency should come from: this is the time to set it up RIGHT before the algorithm
  ignores you for another 6 months — not manufactured hype
- One clear CTA to {PRODUCT_URLS['pinterest-services']}
- 200-300 words body
- Audience: 21,000 warm past buyers — they already invest in looking professional; this is
  the next step for those who want more reach without more content

Tone: Personal, direct, like Jane is talking to one person. Confident but not pushy.
The scarcity is real — write it that way."""

    return call_claude(client, prompt, max_tokens=1400)


def write_pinterest_newsletter(client: anthropic.Anthropic, ctx: dict) -> str:
    prompt = f"""{system_block(ctx)}

TASK: Write a value-led newsletter about Pinterest for the FULL Switzertemplates list (21,000
subscribers — mixed warm and cold, past buyers across all products).

Goal: This is NOT a sales email. It's a trust-building, educational email that warms the
audience toward Pinterest as a topic, gives away something genuinely useful, and only
softly opens the door to Jane's Pinterest services — without pitching them.

Structure to follow:
1. Open with what makes Pinterest different from every other platform: it compounds.
   A pin posted today can still be sending clicks in two years. Instagram and TikTok
   content has a lifespan of about 48 hours — Pinterest pins keep working long after
   you've moved on to the next thing.
2. Connect that to a concrete benefit for a small business owner: traffic that shows up
   without you creating new content every day. More time back. Less pressure to "always
   be posting."
3. The hook: Jane is giving away 10 free Pinterest pin templates — ready to use in Canva,
   built in the formats getting the most clicks right now. No catch, no opt-in funnel talk.
4. ONE soft, single-sentence mention near the end: if someone wants this handled for them
   entirely, Jane also offers done-for-you Pinterest services — phrase it as a passing
   mention with a simple text link, NOT a second button, NOT pricing, NOT urgency.
5. Primary CTA (the only button): download the free templates.

Tone: generous, low-pressure, educational — like sharing something useful with a friend,
not selling. The freebie is the hero of this email. The services mention is a quiet,
open door — easy to miss if you're not looking for it, easy to click if you are.

Requirements:
- 200-280 words body
- Exactly ONE button-style CTA: the freebie download — use [FREEBIE LINK] as the placeholder
- The Pinterest services mention must be ONE sentence, woven naturally into the closing,
  with a plain text link only (use {PRODUCT_URLS['pinterest-services']})
- No urgency, no scarcity, no "spots", no pricing, no packages — that belongs in a
  different email, not this one
- Audience: full list — assume mixed familiarity with Pinterest"""

    return call_claude(client, prompt, max_tokens=1400)


def write_re_engagement_2(client: anthropic.Anthropic, ctx: dict) -> str:
    prompt = f"""{system_block(ctx)}

TASK: Write a SECOND re-engagement email for subscribers who did NOT open the first re-engagement email.

Context:
- These subscribers have been inactive 90+ days
- They already received a first re-engagement email ("Before I remove you, read this" /
  "Still there? Here's what you'd be leaving.") — and they did NOT open it
- They are past buyers — they've bought from Switzertemplates before
- Threat framing did not work on them — do not repeat it

CRITICAL STRATEGIC SHIFT:
- Do NOT mention list cleaning, removing, unsubscribing — that approach failed
- Do NOT use urgency or threat framing of any kind
- Use a completely different angle: pure, immediate value with no ask attached
- The subject line should be about a specific business problem or insight — not about Jane's inbox
- No mention of the previous email, no guilt, no "you haven't opened in a while"
- The tone should feel like Jane reached back into her contacts and sent something useful
  because she thought of them — not because she's trying to save a metric

Email approach:
- Open with ONE specific, surprising insight about Pinterest or online visibility that
  makes the reader think "I didn't know that" or "that's exactly what's happening to me"
- Give them 1-2 concrete tips they can act on TODAY without buying anything
  (example: how often to pin, the biggest Pinterest mistake most accounts make,
   or the one thing that separates accounts that get traffic from those that don't)
- This free value should be specific enough to be genuinely useful — not a teaser
- End with a single very soft CTA: a blog post, the Pinterest guide, or just "hit reply
  if you want me to take a look at your account" — no product pitch
- Under 200 words body total — tight and focused
- The subject line must feel like a useful tip email, not a re-engagement campaign

The goal: earn a click by deserving it. If they open and click, they're re-engaged.
If they don't, they'll be quietly removed — but this email gets one last real shot
by giving something first."""

    return call_claude(client, prompt, max_tokens=1200)


def write_re_engagement(client: anthropic.Anthropic, ctx: dict) -> str:
    prompt = f"""{system_block(ctx)}

TASK: Write a re-engagement email for the Switzertemplates email list.

List context:
- 21,000 past buyers who already know and trust the brand
- Open rate has dropped to 15% — they have gone quiet
- Goal: get them clicking again with something genuinely useful, or let them self-select out

Tone rules for this email:
- Honest and self-aware — acknowledge that inboxes are noisy
- No guilt-tripping, no "I miss you", no hollow flattery
- Give something real (a practical tip, insight, or link to a useful post) before asking for anything
- One clear CTA to switzertemplates.com — either a blog post or a product page
- 150-250 words body maximum

The email should feel like it was written by a real person, not a re-engagement template.
Open with something unexpected or self-aware that earns attention instantly."""

    return call_claude(client, prompt)


def write_blog_post_email(client: anthropic.Anthropic, ctx: dict, slug: str) -> str:
    post = extract_post(slug)
    prompt = f"""{system_block(ctx)}

TASK: Write an email promoting this blog post to the Switzertemplates subscriber list.

POST TITLE: {post['title']}
POST URL: {post['url']}
POST CONTENT (excerpt):
{post['body']}

Requirements:
- Open with a real business problem or insight drawn from the post content
- Build curiosity about the post without giving everything away — leave a reason to click
- Primary CTA links to the blog post URL
- If a natural product mention fits in one sentence mid-body, include it — but do not force it
- 150-250 words body
- Audience: 21,000 warm past buyers — skip intros, get to the value fast"""

    return call_claude(client, prompt)


def write_product_email(client: anthropic.Anthropic, ctx: dict, product: str) -> str:
    if product not in PRODUCT_URLS:
        valid = ", ".join(PRODUCT_URLS.keys())
        print(f"Unknown product '{product}'. Valid options: {valid}")
        sys.exit(1)

    product_url = PRODUCT_URLS[product]
    supplement = PRODUCT_SUPPLEMENTS.get(product, "")

    upsell_note = """
Upsell logic — follow exactly:
- Do NOT pitch the bundle to someone who already has a Wix website or branding kit
- Wix website buyers → upsell branding kit
- Branding kit buyers → upsell Wix website
- Instagram template buyers → upsell website or bundle
- If subscriber history is unknown → default to bundle (flagship offer)"""

    product_context = f"\nADDITIONAL PRODUCT DETAILS:\n{supplement}" if supplement else ""

    prompt = f"""{system_block(ctx)}

TASK: Write a product-focused email promoting: {product}

Product page URL (CTA destination): {product_url}{product_context}
{upsell_note}

Writing requirements:
- Open with the business problem this product solves — not the product itself
- Connect the product to a concrete outcome: looks professional, attracts clients, saves time, drives traffic
- Reference one or two proof points naturally ("27,700+ sales", "Top 1% Etsy seller")
- One clear CTA to the product page
- 150-300 words body
- Audience: 21,000 warm past buyers — they know the brand, skip introductions"""

    return call_claude(client, prompt)


# ── research phase ─────────────────────────────────────────────────────────────

def get_channel_video_ids(handle: str, limit: int = 15) -> list[tuple[str, str]]:
    """Scrape a YouTube channel page and return (video_id, title) pairs."""
    import re
    import requests

    url = f"https://www.youtube.com/{handle}/videos"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()

    video_ids = list(dict.fromkeys(re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', r.text)))[:limit]

    # Extract titles — each title sits near its videoId in the page JSON
    title_map = {}
    for match in re.finditer(r'"videoId":"([a-zA-Z0-9_-]{11})".*?"text":"([^"]{10,100})"', r.text):
        vid, title = match.group(1), match.group(2)
        if vid not in title_map:
            title_map[vid] = title

    return [(vid, title_map.get(vid, vid)) for vid in video_ids]


def run_research(client: anthropic.Anthropic):
    """Phase A: Scrape YouTube transcripts and synthesize email copywriting principles."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("youtube-transcript-api not installed. Run: pip install youtube-transcript-api")
        sys.exit(1)

    all_sections = []

    for creator_name, handle in CHANNEL_HANDLES:
        print(f"\nFetching {creator_name} ({handle})...")

        try:
            videos = get_channel_video_ids(handle, limit=15)
            print(f"  Found {len(videos)} videos")
        except Exception as e:
            print(f"  Could not fetch channel: {e}")
            continue

        api = YouTubeTranscriptApi()
        creator_transcripts = []
        SKIP_TITLES = {"youtube home", "trending", "subscriptions", "library", "history"}
        for video_id, title in videos[:10]:
            if title.lower() in SKIP_TITLES or len(title) < 8:
                continue
            try:
                chunks = api.fetch(video_id)
                text = " ".join(c.text for c in chunks)
                creator_transcripts.append(f"### {title}\n{text[:2500]}")
                print(f"  + {title[:65]}")
            except Exception as e:
                print(f"  - {title[:65]} ({type(e).__name__})")

        if creator_transcripts:
            all_sections.append(f"## {creator_name}\n\n" + "\n\n".join(creator_transcripts[:5]))

    if not all_sections:
        print("\nNo transcripts retrieved. Check internet connection or channel URLs.")
        sys.exit(1)

    print(f"\nSynthesising principles from {len(all_sections)} creator(s)...")

    combined = "\n\n---\n\n".join(all_sections)
    synthesis_prompt = f"""You are analysing email marketing transcripts from two expert copywriters
to extract practical principles for Switzertemplates, a digital product business selling
Canva templates and Wix websites to female small business owners.

Audience context:
- 21,000 subscribers, all past buyers (warm list, already trusts the brand)
- Current open rate: 15% — needs re-engagement
- Email goals: increase opens, drive traffic to switzertemplates.com, convert to product sales
- Email types written: re-engagement, blog post promotion, product launches, weekly newsletters

TRANSCRIPTS:
{combined[:12000]}

Extract and synthesise the most actionable email copywriting principles relevant to this business.
Structure your output as a practical guide with these sections:

## 1. Subject line formulas
Include fill-in-the-blank templates and real examples.

## 2. Opening hooks for warm lists
What makes someone open and keep reading when they already know the brand.

## 3. Body copy structure
How to flow from hook to value to CTA without losing the reader.

## 4. CTA techniques that convert
How to write CTAs that feel natural and drive clicks.

## 5. Re-engagement tactics
Specific approaches for winning back a quiet list without guilt-tripping.

## 6. What to avoid
Common mistakes that kill open rates or trust.

Be specific and practical. Include example phrases and sentence patterns.
Do not write theory — write actionable guidance with examples."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2500,
        messages=[{"role": "user", "content": synthesis_prompt}],
    )

    output = "# Email Copywriting Principles — Switzertemplates\n"
    output += f"*Synthesised from Maxwell Copy + Alex Cattoni. Updated {datetime.now().strftime('%Y-%m-%d')}.*\n\n"
    output += response.content[0].text.strip()

    EMAIL_PRINCIPLES_FILE.write_text(output, encoding="utf-8")
    print(f"\nSaved: {EMAIL_PRINCIPLES_FILE.relative_to(ROOT)}")
    print("Run any writing mode to use these principles automatically.")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Email Agent — Switzertemplates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python3 agents/email-agent/email_agent.py --research
  python3 agents/email-agent/email_agent.py --re-engagement
  python3 agents/email-agent/email_agent.py --blog-post pinterest-marketing
  python3 agents/email-agent/email_agent.py --product bundle
  python3 agents/email-agent/email_agent.py --weekly""",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--research", action="store_true",
                       help="Build email principles from YouTube transcripts (run once)")
    group.add_argument("--re-engagement", action="store_true",
                       help="Write a re-engagement email for quiet subscribers")
    group.add_argument("--re-engagement-2", action="store_true",
                       help="Write a second re-engagement email (value-first, for those who ignored the first)")
    group.add_argument("--pinterest-urgent", action="store_true",
                       help="Write a Pinterest services email with genuine scarcity (5 spots)")
    group.add_argument("--pinterest-newsletter", action="store_true",
                       help="Write a value-led Pinterest newsletter for the full list (freebie hook, soft pitch)")
    group.add_argument("--blog-post", metavar="SLUG",
                       help="Write an email promoting a blog post by slug")
    group.add_argument("--product", metavar="NAME",
                       help=f"Write a product email ({', '.join(PRODUCT_URLS)})")
    group.add_argument("--weekly", action="store_true",
                       help="Write weekly email from the most recently written blog post")

    args = parser.parse_args()
    client = make_client()

    if args.research:
        run_research(client)
        return

    ctx = load_context()

    if not ctx["email_principles"]:
        print("Tip: run --research first to build email principles from expert sources.")
        print("     Writing will still work, just without those learned patterns.\n")

    if args.re_engagement:
        email_type = "re-engagement"
        content = write_re_engagement(client, ctx)

    elif getattr(args, "re_engagement_2", False):
        email_type = "re-engagement-2"
        content = write_re_engagement_2(client, ctx)

    elif getattr(args, "pinterest_urgent", False):
        email_type = "product-pinterest-services-urgent"
        content = write_pinterest_urgent(client, ctx)

    elif getattr(args, "pinterest_newsletter", False):
        email_type = "newsletter-pinterest-freebie"
        content = write_pinterest_newsletter(client, ctx)

    elif args.blog_post:
        email_type = f"blog-{args.blog_post}"
        content = write_blog_post_email(client, ctx, args.blog_post)

    elif args.product:
        email_type = f"product-{args.product}"
        content = write_product_email(client, ctx, args.product)

    elif args.weekly:
        slug = get_latest_post()
        print(f"Latest post: {slug}")
        email_type = f"weekly-{slug}"
        content = write_blog_post_email(client, ctx, slug)

    out_path = save_output(content, email_type)

    print(f"\n{'=' * 60}")
    print(content)
    print(f"{'=' * 60}")
    print(f"\nSaved: {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
