"""
Outreach Generator — writes personalised DM and email drafts for each lead
using Claude. Every message includes:

  - A specific opener referencing their product or business
  - A niche-specific explanation of why Pinterest works for them
  - Jane's social proof (28,000+ sales, Pinterest-driven website traffic)
  - Link to pinterest.switzertemplates.com
  - Soft CTA — curiosity, not a hard sell
  - No price mentioned

Drafts saved to outputs/leads/outreach-drafts/<lead_id>-<type>.txt
"""

import os
import sys
import random
import anthropic
from pathlib import Path
from datetime import date

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from lead_tracker import get_leads_for_outreach, update_lead

DRAFTS_DIR = Path(__file__).resolve().parents[2] / "outputs" / "leads" / "outreach-drafts"

# ── Niche-specific Pinterest reasoning ───────────────────────────────────────

NICHE_ANGLES = {
    "handmade jewelry": (
        "Pinterest is the platform where women save and rediscover jewelry before they buy. "
        "It's not a social feed — it's a visual search engine, and jewelry is one of its top-performing categories. "
        "Pins drive purchase-intent traffic for months or years after posting."
    ),
    "handmade candles": (
        "Home lifestyle content thrives on Pinterest — buyers search 'candle gift ideas', 'soy candle aesthetic', "
        "'home fragrance gift'. These are purchase-intent searches. A single well-optimised pin can drive sales for a year."
    ),
    "ceramic pottery": (
        "Handmade homewares perform exceptionally well on Pinterest. Buyers search by aesthetic — "
        "'japandi ceramics', 'earthy pottery', 'handmade mug gift'. Pinterest connects makers directly to buyers "
        "who are actively shopping, not just scrolling."
    ),
    "home decor": (
        "Home decor is Pinterest's single biggest category. Buyers use it to plan purchases, not just gather inspiration — "
        "they pin what they intend to buy. Being found on Pinterest means being found at the moment of decision."
    ),
    "interior design": (
        "Pinterest is a portfolio platform for interior designers. Clients use it to find and vet designers "
        "before ever reaching out. Being visible there means being discovered at the start of someone's search "
        "for exactly what you offer."
    ),
    "wedding photography": (
        "Brides spend months pinning wedding inspiration before they book anything — and that includes their photographer. "
        "Pinterest is where they find and shortlist photographers. Being found there means being considered from day one."
    ),
    "wedding planning": (
        "Couples use Pinterest to plan every detail of their wedding — venues, themes, flowers, timelines. "
        "Wedding planners who show up on Pinterest get discovered at the very start of the planning journey, "
        "before couples even know who to contact."
    ),
    "wedding florals": (
        "Floral inspiration is one of Pinterest's most-searched categories. Brides and event planners use it "
        "to find their florist — they pin styles they love, then contact whoever created them. "
        "Pinterest puts your work directly in front of buyers actively planning an event."
    ),
    "floristry": (
        "Flower arrangements, bouquets, and seasonal floral designs perform exceptionally on Pinterest. "
        "Event planners and occasion shoppers search for inspiration and find local florists through it. "
        "A strong Pinterest presence means being discovered at the exact moment someone is planning to buy."
    ),
    "event planning": (
        "Visual event content — tablescapes, styled shoots, venue setups — is highly saved on Pinterest. "
        "Clients planning weddings, corporate events, and parties use it to brief their planner. "
        "Being on Pinterest means your work is doing the marketing for you."
    ),
    "gift shop": (
        "Gift-giving searches on Pinterest spike every season — 'unique gifts for her', 'small business gifts', "
        "'thoughtful birthday gift ideas'. These are buyers, not browsers. A well-optimised gift shop presence "
        "on Pinterest drives consistent revenue around every gifting occasion."
    ),
    "boutique travel": (
        "Travel inspiration is one of Pinterest's top categories. People plan entire trips through it — "
        "destinations, experiences, itineraries. Boutique travel agencies and planners who show up in those searches "
        "get discovered at the exact moment someone decides where to go."
    ),
    "travel agency": (
        "Travel inspiration is one of Pinterest's top categories. People plan entire trips through it — "
        "destinations, experiences, itineraries. Travel agencies that show up in those searches "
        "get discovered at the exact moment someone is ready to book."
    ),
    "travel agent": (
        "Travel inspiration is one of Pinterest's top categories. People plan entire trips through it — "
        "destinations, experiences, itineraries. Travel agents who show up in those searches "
        "get discovered at the exact moment someone is ready to book."
    ),
    "pilates": (
        "Reformer pilates is having a massive moment and Pinterest is where people discover studios — "
        "they search 'reformer pilates near me', 'pilates body transformation', 'beginner reformer pilates'. "
        "Studios that show up in those searches fill their classes without paying for ads."
    ),
    "personal training": (
        "Fitness and wellness content drives consistent traffic on Pinterest. People search 'home workout plan', "
        "'personal trainer near me', 'weight loss tips' — and they save content to come back to. "
        "A personal trainer with a Pinterest presence gets discovered by clients actively looking for help, "
        "not just passive scrollers."
    ),
    "life coaching": (
        "Self-development and mindset content is one of Pinterest's most-saved categories. "
        "People search for coaches when they're ready to change something — Pinterest puts you in front of them "
        "at exactly that moment. It's one of the few platforms where long-form content and transformation stories "
        "outperform short-form."
    ),
    "business coaching": (
        "Business owners turn to Pinterest for strategies, frameworks, and experts they can trust. "
        "Business coaches who show up in search results for 'how to grow my business' or 'entrepreneur tips' "
        "get discovered by buyers who are already motivated and looking for help."
    ),
    "esthetics": (
        "Beauty services — skincare routines, facials, brow work, lash treatments — perform exceptionally well "
        "on Pinterest. Clients search for specific treatments before booking, and visual before/after content "
        "is among the most-saved on the platform. Pinterest drives local discovery in a way Instagram rarely does."
    ),
    "nutrition coaching": (
        "Health and wellness is one of Pinterest's top-performing niches. People search meal plans, clean eating, "
        "weight loss strategies — and they save content from experts they trust. A nutritionist or health coach "
        "with Pinterest presence gets consistent inbound enquiries from people already sold on the concept."
    ),
    "therapy": (
        "Mental health content is increasingly searched on Pinterest, and private practice therapists who show up "
        "there get discovered at the moment someone is ready to take action. Pinterest drives long-term referral "
        "traffic from people who find your content, save it, and come back when they're ready to book."
    ),
    "virtual assistant": (
        "Small business owners searching for support turn to Pinterest for referrals, tips, and service providers "
        "they trust. VAs who share their process and results on Pinterest get discovered by exactly the right "
        "audience — overwhelmed business owners actively looking to delegate."
    ),
    "social media management": (
        "Business owners searching 'how to grow on Instagram' and 'social media strategy' land on Pinterest "
        "constantly — and they hire the people whose content they've been saving. "
        "Social media managers who are visible on Pinterest attract clients who already see them as an authority."
    ),
    "handmade skincare": (
        "Beauty and skincare content drives significant Pinterest traffic. Buyers search routines, ingredients, "
        "and 'clean skincare gift ideas'. Handmade skincare brands particularly benefit because Pinterest "
        "shoppers actively seek out small, independent brands over mass-market options."
    ),
    "handmade products": (
        "Buyers on Pinterest are specifically looking for handmade, independent, and small-business products — "
        "it's one of the few platforms where 'handmade' is a competitive advantage, not a limitation. "
        "Pins drive purchase-intent traffic for months after posting."
    ),
    "small business": (
        "Pinterest shoppers actively seek out small businesses and independent makers — it's baked into the culture "
        "of the platform. Unlike Instagram where posts disappear in 24 hours, pins drive traffic for months or years."
    ),
    "health coaching": (
        "Women search Pinterest for answers before they hire anyone — 'gut health tips', 'hormone balance', "
        "'how to lose weight naturally', 'what to eat to have more energy'. Health coaches who show up in those "
        "searches get discovered by people who are already committed to making a change."
    ),
    "relationship coaching": (
        "Pinterest is where women go when they're quietly working on themselves — searching 'how to attract the right partner', "
        "'dating confidence', 'relationship red flags', 'heal after a breakup'. A relationship coach with a presence "
        "there gets found by exactly the right people at exactly the right moment."
    ),
    "financial coaching": (
        "Money mindset and personal finance is one of Pinterest's strongest niches among women. They search "
        "'how to save money', 'money management tips', 'financial freedom journey', 'pay off debt fast'. "
        "Financial coaches who show up there reach buyers who are already motivated to change their relationship with money."
    ),
    "mindset coaching": (
        "Mindset, self-development, and confidence content is one of Pinterest's most-saved categories. "
        "Women search 'morning routine ideas', 'growth mindset quotes', 'how to build confidence', 'daily habits'. "
        "A mindset coach who shows up there gets found by people actively investing in themselves."
    ),
    "personal styling": (
        "Fashion and personal style is one of Pinterest's top categories — women plan their wardrobes through it. "
        "They search 'capsule wardrobe', 'how to dress your body type', 'business casual outfits for women', "
        "'elevated everyday style'. Personal stylists who show up in those searches get clients who are already "
        "motivated to invest in their appearance."
    ),
    "home organizing": (
        "Home organisation is one of Pinterest's most searched and saved categories. People search 'pantry organisation ideas', "
        "'bedroom declutter', 'minimalist home', 'small space storage' — and they save this content for months "
        "before hiring someone. A professional organiser on Pinterest gets discovered at exactly the inspiration-to-action moment."
    ),
}

FALLBACK_ANGLE = (
    "Pinterest is a visual search engine — buyers use it to find and save products and services before they purchase. "
    "Unlike Instagram, where content disappears in 24 hours, a well-optimised pin drives traffic for months or years. "
    "It's one of the few platforms where showing up consistently has a compounding return."
)


def _get_niche_angle(product_type: str) -> str:
    if not product_type:
        return FALLBACK_ANGLE
    pt = product_type.lower().strip()
    # Exact match
    if pt in NICHE_ANGLES:
        return NICHE_ANGLES[pt]
    # Partial match
    for key, angle in NICHE_ANGLES.items():
        if key in pt or pt in key:
            return angle
    return FALLBACK_ANGLE


def _detect_outreach_type(lead: dict) -> str:
    """DM if we have an Instagram handle, email if we have a sendable email, form otherwise."""
    from lead_tracker import _is_sendable_email
    if lead.get("instagram_handle") and not lead.get("contact_email"):
        return "DM"
    if lead.get("contact_email") and _is_sendable_email(lead["contact_email"]):
        return "email"
    if lead.get("contact_page_url"):
        return "contact-form"
    return "DM"


_OPENER_PROMPT = """Write one sentence that completes this outreach opener for Jane, who is reaching out to a small business owner about Pinterest marketing.

The sentence must:
- Start with "{opening_phrase}"
- Then add a short, natural compliment about their products or business — keep it simple and genuine, like how a real person would say it
- Avoid flowery language, long descriptions, or over-specific product details
- Be warm but brief — no more than 15 words after the opening phrase

Business: {business}
Niche / product type: {niche}

Examples of the right tone:
- "I really like your profile - your jewellery pieces are really beautiful."
- "I really like your website - the products you sell are so elegant."
- "I really like your profile - your candles look amazing."

Write only the single sentence. No quotes around it. Nothing else."""

SUBJECT_POOL = [
    # Questions
    "Are your ideal clients finding you on Pinterest?",
    "Quick question about your Pinterest presence",
    "Is Pinterest missing from your marketing?",
    "Have you tried Pinterest for your business?",
    "Could Pinterest work for your business?",
    "Are you using Pinterest to get clients?",
    "Has anyone mentioned Pinterest to you yet?",
    "Is your business showing up on Pinterest?",
    "Are you missing clients on Pinterest?",
    "Do your ideal clients use Pinterest?",
    # Observations
    "I think your business is perfect for Pinterest",
    "Your business would do really well on Pinterest",
    "Noticed you're not on Pinterest yet",
    "I spotted a Pinterest opportunity for your business",
    "Pinterest could be a real fit for what you do",
    "Your type of business thrives on Pinterest",
    "Honestly your business is made for Pinterest",
    "Your work would translate so well to Pinterest",
    "I think you'd love what Pinterest could do for you",
    "I kept thinking about your business and Pinterest",
    # Soft pitch
    "I'd love to set up your Pinterest for success",
    "Let's get your business growing on Pinterest",
    "Your next clients might already be on Pinterest",
    "There's a Pinterest audience ready for your business",
    "Pinterest could bring you clients without the ad spend",
    "I can help you get found on Pinterest",
    "Your business deserves to be on Pinterest",
    "Pinterest is where your next client is searching",
    "Let me show you what Pinterest could do for you",
    "Your ideal clients are already on Pinterest",
    "I'd love to help you grow on Pinterest",
    "Pinterest could change the game for your business",
    "Let's put your business in front of Pinterest users",
    # Curiosity / provocative
    "Your competitors are quietly growing on Pinterest",
    "Most businesses in your niche sleep on Pinterest",
    "There's a traffic source you're probably not using",
    "Pinterest doesn't work for everyone — but it might for you",
    "Something your marketing is probably missing",
    "Pinterest is quietly sending clients to your competitors",
    "This is probably where your next client is right now",
    "The platform most businesses in your industry forget",
    "Most people in your industry haven't figured Pinterest out",
    "The one platform your competitors aren't taking seriously",
    "Your next 10 clients might already be on Pinterest",
    "Pinterest is underrated for businesses like yours",
    # Simple / direct
    "Noticed a Pinterest gap worth fixing",
    "A Pinterest strategy built for your business",
    "Pinterest could be your best marketing channel",
    "Worth 5 minutes of your time — Pinterest for your business",
    "Your business + Pinterest = a lot of potential clients",
]

# Contact form + DM template — no "Hi there", no "How are you?"
_TEMPLATE = """{greeting}

{opener} I noticed you don't have a Pinterest presence — which is worth looking into for your type of business.

My name is Jane. I work with business owners to build Pinterest strategies that drive consistent, long-term traffic to their websites. I also run Switzer Templates (28,000+ sales), and Pinterest is my main traffic driver.

I offer two packages tailored to your niche: https://pinterest.switzertemplates.com/ Each includes a full audit and a strategy built around what's actually working in your industry.

There's also a free Pinterest starter guide here if you want to explore first: switzertemplates.myflodesk.com/pinterest-guidebook

Happy to answer any questions.

Regards,
Jane"""

# Email body variants — rotated randomly to avoid spam filters.
# Subject line and opener are already unique per lead.
_EMAIL_TEMPLATES = [
    """{greeting}

{opener} I think your business could do really well on Pinterest — and I noticed you don't have a profile linked anywhere.

My name is Jane. I help business owners drive thousands of visitors from Pinterest to their websites (I also run Switzer Templates, a shop with over 28,000 sales, and Pinterest is my biggest traffic source).

I offer two packages to help set your account up for success: https://pinterest.switzertemplates.com/ I do a full audit and build a strategy specifically for your niche, using paid analytics tools that show you exactly what's working and how much traffic you can realistically expect.

If you're not ready to invest yet, I also put together a free guide to help you get started: switzertemplates.myflodesk.com/pinterest-guidebook

Happy to answer any questions!

Regards,
Jane""",

    """{greeting}

{opener} One thing I noticed — you don't seem to have a Pinterest presence, which is worth looking into for your type of business.

I'm Jane. I work with business owners to build Pinterest strategies that drive consistent, long-term traffic to their websites and shops. I also run Switzer Templates (28,000+ sales), and Pinterest is my main traffic driver.

If you're interested, I offer two packages tailored to your niche: https://pinterest.switzertemplates.com/ Each one includes a full audit and a detailed strategy built around what's actually working in your industry — using analytics tools not available to the public.

There's also a free Pinterest starter guide here if you want to explore first: switzertemplates.myflodesk.com/pinterest-guidebook

Let me know if you have any questions.

Regards,
Jane""",

    """{greeting}

{opener} I wanted to reach out because I think Pinterest could be a strong traffic channel for your business — and I can see you're not on it yet.

My name is Jane. I specialise in Pinterest strategy for small business owners. I also run my own shop, Switzer Templates, with over 28,000 sales — Pinterest is how I get most of my traffic.

I offer two packages to get your account set up properly: https://pinterest.switzertemplates.com/ The process includes a full niche audit and a strategy built on real data, so you know exactly what to pin and what kind of results to expect.

If you'd like to learn the basics first, grab my free guide here: switzertemplates.myflodesk.com/pinterest-guidebook

Always happy to chat if you have questions.

Regards,
Jane""",

    """{greeting}

{opener} I came across your business and noticed you're not on Pinterest — which actually surprised me, because your niche tends to do really well there.

I'm Jane, a Pinterest strategist. I also run Switzer Templates, a shop with 28,000+ sales where Pinterest drives the majority of my traffic.

I work with business owners like you to build a Pinterest presence that brings in consistent visitors over time — not just a spike. I offer two packages: https://pinterest.switzertemplates.com/ Both include a full audit of your niche and a strategy based on what's actually getting results right now.

If you're just curious and not ready to invest, here's a free guide to get started: switzertemplates.myflodesk.com/pinterest-guidebook

Feel free to reach out with any questions.

Regards,
Jane""",
]


def _build_opener_prompt(lead: dict) -> str:
    business = lead.get("shop_or_business_name") or "your business"
    niche    = lead.get("product_type") or "small business"
    source   = lead.get("source", "etsy")
    if source == "etsy":
        opening_phrase = "I really like your shop -"
    elif source == "google" or source == "bing":
        opening_phrase = "I really like your website -"
    else:
        opening_phrase = "I really like your profile -"
    return _OPENER_PROMPT.format(business=business, niche=niche, opening_phrase=opening_phrase)


def _build_subject_prompt(lead: dict) -> str:
    niche = lead.get("product_type") or "small business"
    return _SUBJECT_PROMPT.format(niche=niche)


_BAD_SUBJECT_STARTS = (
    "here's", "here are", "subject line:", "subject:", "option", "sure,",
    "certainly", "of course", "i'd be", "here is",
)

def _clean_subject(raw: str, client, lead: dict) -> str:
    """
    Clean the subject line. If it looks like preamble or garbage, retry once.
    """
    text = raw.strip().strip('"').strip("'").strip()

    # If it ends with a colon or looks like a preamble, it's bad — retry
    if text.endswith(":") or text.lower().startswith(_BAD_SUBJECT_STARTS) or len(text) > 100:
        retry = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=30,
            messages=[{"role": "user", "content": _build_subject_prompt(lead)}],
        )
        text = retry.content[0].text.strip().strip('"').strip("'").strip()

    # Final strip of any remaining preamble
    for prefix in ("subject line:", "subject:", "here's your subject:", "here is your subject:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()

    return text


def _extract_first_name(lead: dict) -> str:
    """
    Extract a usable first name from a lead. Priority order:
    1. owner_name field (set by website scraper)
    2. Email prefix — kayla@kaylasnell.com → Kayla
    3. CamelCase shop name — AndreaHillPottery → Andrea
    Returns empty string if nothing looks like a real name.
    """
    import re

    _GENERIC_PREFIXES = {
        "info", "admin", "hello", "contact", "enquiries", "enquiry",
        "office", "mail", "mymail", "team", "support", "reception", "studio",
        "clinic", "salon", "spa", "shop", "store", "sales", "booking",
        "bookings", "appointments", "general", "noreply", "no-reply",
        "help", "service", "services", "care", "management",
        "intake", "therapy", "coaching", "clientconnect", "customercare",
        "concierge", "wellness", "training", "fitness", "massage",
        "beauty", "aesthetics", "accounts", "billing",
        "hiring", "jobs", "recruitment", "careers", "frontdesk",
        "front", "desk", "board",
    }

    _NOT_NAMES = {
        "the", "a", "an", "my", "your", "our", "new", "old", "best", "pro",
        "top", "true", "pure", "just", "all", "one", "two", "three", "four",
        "eye", "body", "soul", "mind", "life", "live", "love", "real", "rise",
        "flow", "glow", "peak", "core", "apex", "elite", "prime", "plus",
        "fit", "flex", "zen", "well", "care", "heal", "vibe", "bold", "bliss",
        "studio", "clinic", "center", "centre", "house", "home", "room",
        "group", "team", "club", "hub", "lab", "co", "inc", "llc",
        "inner", "outer", "urban", "city", "west", "east", "north", "south",
        "downtown", "uptown", "bright", "clear", "clean", "fresh", "smart",
        "move", "werk", "total", "whole", "pivot", "spark", "starling",
        "yonder", "derm", "skin", "face", "body", "hair", "nail", "lash",
        # surnames / place names that look like first names in email prefixes
        "brookshire", "tmivong",
    }

    # Common first names — used to extract names from domain roots when email prefix is generic
    # e.g. info@amyvermillion.com → Amy, info@annabaylis.com.au → Anna
    _COMMON_NAMES = {
        "amy", "anna", "anne", "annie", "amanda", "andrea", "angela", "alyssa",
        "alicia", "alison", "alexis", "alexa", "alice", "abby", "abigail",
        "ashley", "amber", "april", "audrey", "aurora",
        "bella", "bethany", "bianca", "brianna", "brittany", "brooke",
        "caitlin", "carly", "carmen", "caroline", "cassandra", "catherine",
        "charlotte", "chelsea", "chloe", "christy", "claire", "claudia",
        "dana", "danielle", "diana", "elise", "elizabeth", "ella", "emily",
        "emma", "erica", "eimear", "eva", "evelyn",
        "faith", "fiona", "francesca", "gabrielle", "gemma", "georgia",
        "grace", "hannah", "haley", "heather", "holly", "isabelle", "isla",
        "jade", "jamie", "jane", "jasmine", "jenna", "jennifer", "jessica",
        "julia", "julie", "june", "kasey", "kate", "katelyn", "katherine",
        "kathryn", "katie", "kayla", "kelly", "kim", "kimberly", "kristen",
        "laura", "lauren", "leah", "lily", "linda", "lisa", "lucy",
        "madison", "mary", "maya", "megan", "melissa", "michelle", "molly", "monica",
        "morgan", "natalie", "natasha", "nicole", "nina", "olivia",
        "paige", "patricia", "rachel", "rebecca", "renee", "riley",
        "samantha", "sandra", "sara", "sarah", "savannah", "shannon",
        "sophia", "sophie", "stephanie", "susan", "sydney", "tara",
        "taylor", "tessa", "tiffany", "vanessa", "victoria", "violet",
        "whitney", "zoe",
        # male names (coaches, trainers etc. do appear)
        "adam", "alex", "andrew", "brian", "chris", "daniel", "david",
        "ethan", "james", "jason", "john", "jon", "jordan", "josh",
        "justin", "kevin", "kyle", "mark", "matt", "michael", "mike",
        "nathan", "nick", "paul", "peter", "ryan", "sam", "sean",
        "thomas", "tim", "tom", "tyler", "william",
    }

    # 1. owner_name from website scraper
    owner = (lead.get("owner_name") or "").strip()
    if owner:
        return owner.split()[0]

    # 2. Email prefix — most reliable signal for personal business emails
    email = (lead.get("contact_email") or "").strip().lower()
    # Strip URL-encoded junk and stray punctuation (e.g. "%20ginger@", ":shannon@")
    email = email.lstrip("%20").lstrip(":").lstrip("%20%20").lstrip()
    if "@" in email:
        prefix = email.split("@")[0]
        # Handle firstname.lastname or firstname_lastname patterns
        for sep in (".", "_", "-"):
            if sep in prefix:
                prefix = prefix.split(sep)[0]
                break
        has_vowel = any(c in "aeiou" for c in prefix)
        in_common = prefix in _COMMON_NAMES
        if (prefix.isalpha()
                and has_vowel
                and 2 <= len(prefix) <= 9   # >9 chars = almost certainly a compound business name
                and prefix not in _GENERIC_PREFIXES
                and prefix not in _NOT_NAMES
                and (len(prefix) >= 5 or in_common)):  # short prefixes must be known names
            return prefix.capitalize()

    # 3. "byName" in email prefix — e.g. aestheticsbyeimear@gmail.com → Eimear
    if "@" in email:
        raw_prefix = email.split("@")[0]
        if "by" in raw_prefix:
            after_by = raw_prefix.split("by")[-1]
            if (after_by.isalpha()
                    and 2 <= len(after_by) <= 10
                    and after_by not in _GENERIC_PREFIXES
                    and after_by not in _NOT_NAMES):
                return after_by.capitalize()

    # 4. Domain-root extraction for generic email prefixes
    # e.g. info@amyvermillion.com → domain root "amyvermillion" starts with "amy"
    if "@" in email:
        domain_root = email.split("@")[1].split(".")[0].lower()
        for name in sorted(_COMMON_NAMES, key=len, reverse=True):  # longest first avoids partial matches
            if domain_root.startswith(name):
                return name.capitalize()

    # 5. CamelCase shop name — only when first word is a known real first name
    shop = (lead.get("shop_or_business_name") or "").strip()
    if shop and " " not in shop:
        words = re.sub(r"([A-Z][a-z]+)", r" \1", shop).split()
        first = words[0] if words else ""
        if (len(words) > 1
                and first.isalpha()
                and first.lower() in _COMMON_NAMES):
            return first

    return ""


def generate_draft(lead: dict) -> tuple[str, str, str]:
    """
    Generate a single outreach draft for a lead.
    Returns (outreach_type, subject_line, draft_text).
    subject_line is empty string for DM outreach.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    outreach_type = _detect_outreach_type(lead)

    # Generate opener sentence
    opener_msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=80,
        messages=[{"role": "user", "content": _build_opener_prompt(lead)}],
    )
    opener = opener_msg.content[0].text.strip().strip('"').strip("'").strip()

    if outreach_type == "email":
        subject_line = random.choice(SUBJECT_POOL)

        greeting_name = _extract_first_name(lead)
        greeting = f"Hi {greeting_name}," if greeting_name else "Hi,"
        template = random.choice(_EMAIL_TEMPLATES)
        draft = template.format(opener=opener, greeting=greeting)
    else:
        subject_line = ""
        greeting_name = _extract_first_name(lead)
        greeting = f"Hi {greeting_name}," if greeting_name else "Hi,"
        draft = _TEMPLATE.format(opener=opener, greeting=greeting)

    return outreach_type, subject_line, draft


def save_draft(lead: dict, outreach_type: str, subject_line: str, draft: str) -> Path:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    lead_id = lead.get("lead_id", "unknown")
    business = (lead.get("shop_or_business_name") or "lead").replace(" ", "-").lower()
    filename = f"{lead_id}-{business}-{outreach_type.lower()}.txt"
    path = DRAFTS_DIR / filename

    subject_line_row = f"Subject:  {subject_line}\n" if subject_line else ""
    header = (
        f"Lead ID:  {lead_id}\n"
        f"Business: {lead.get('shop_or_business_name', '')}\n"
        f"Niche:    {lead.get('product_type', '')}\n"
        f"Type:     {outreach_type}\n"
        f"{subject_line_row}"
        f"Contact:  {lead.get('contact_email') or lead.get('instagram_handle') or lead.get('contact_page_url', '')}\n"
        f"Source:   {lead.get('source', '')}\n"
        f"Date:     {date.today().isoformat()}\n"
        f"{'─' * 60}\n\n"
    )
    path.write_text(header + draft, encoding="utf-8")
    return path


def run(limit=20, only_type=None):
    leads = get_leads_for_outreach(limit=limit * 10 if only_type else limit)
    if only_type:
        leads = [l for l in leads if _detect_outreach_type(l) == only_type][:limit]
    print(f"\n[Outreach Generator] {len(leads)} leads to process", file=sys.stderr)

    generated = 0
    for lead in leads:
        business = lead.get("shop_or_business_name") or lead.get("lead_id")
        print(f"  Generating draft for: {business}", file=sys.stderr)
        try:
            outreach_type, subject_line, draft = generate_draft(lead)
            path = save_draft(lead, outreach_type, subject_line, draft)
            update_lead(lead["lead_id"], {
                "outreach_type": outreach_type,
                "status": "qualified",
            })
            print(f"    → Saved: {path.name}", file=sys.stderr)
            generated += 1
        except Exception as e:
            print(f"    [error] {e}", file=sys.stderr)

    print(f"\n[Outreach Generator] {generated} drafts saved to outputs/leads/outreach-drafts/", file=sys.stderr)
    return generated


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20, help="Max leads to process")
    parser.add_argument("--type", dest="only_type", default=None,
                        help="Only generate for leads of this type: email, contact-form, DM")
    args = parser.parse_args()
    run(limit=args.limit, only_type=args.only_type)
