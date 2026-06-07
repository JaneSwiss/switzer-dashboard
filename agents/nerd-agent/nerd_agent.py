#!/usr/bin/env python3
"""
Nerd Agent — Switzertemplates
Ingests external resources (YouTube videos, blog posts, newsletters, PDFs),
extracts key insights, and writes topic overviews that other agents can load.

Commands:
    python3 agents/nerd-agent/nerd_agent.py learn --url "https://youtube.com/watch?v=..."
    python3 agents/nerd-agent/nerd_agent.py learn --url "https://blog.example.com/post"
    python3 agents/nerd-agent/nerd_agent.py learn --file "/path/to/course.pdf"
    python3 agents/nerd-agent/nerd_agent.py learn --text "Content..." --source "Newsletter title"
    python3 agents/nerd-agent/nerd_agent.py learn --batch "urls.txt"
    python3 agents/nerd-agent/nerd_agent.py learn --url "..." --topics "pinterest-marketing,etsy-seo"
    python3 agents/nerd-agent/nerd_agent.py report --all
    python3 agents/nerd-agent/nerd_agent.py report --topic pinterest-marketing
    python3 agents/nerd-agent/nerd_agent.py report --status
    python3 agents/nerd-agent/nerd_agent.py list
    python3 agents/nerd-agent/nerd_agent.py list --topic pinterest-marketing
    python3 agents/nerd-agent/nerd_agent.py list --id a3f7bc12
    python3 agents/nerd-agent/nerd_agent.py share
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib3
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import anthropic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Suppress cosmetic SSL warning (HTTPS works fine — confirmed)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── paths ──────────────────────────────────────────────────────────────────────

ROOT              = Path(__file__).resolve().parents[2]
AGENT_DIR         = Path(__file__).resolve().parent
KNOWLEDGE_DIR     = AGENT_DIR / "knowledge"
ENTRIES_DIR       = KNOWLEDGE_DIR / "entries"
SOURCES_FILE      = KNOWLEDGE_DIR / "sources.json"
INSIGHTS_DIR      = ROOT / "context" / "nerd-insights"
LOGS_DIR          = AGENT_DIR / "logs"
ERROR_LOG         = LOGS_DIR / "errors.json"
BRAND_VOICE_FILE  = ROOT / "context" / "brand-voice.md"
PRODUCT_CATALOG_FILE = ROOT / "context" / "product-catalog.md"
DASHBOARD_FILE    = ROOT / "dashboard_data.json"

load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Max chars sent to Claude per source (~35 min of video or a long article)
MAX_TEXT_CHARS = 15_000

ALLOWED_TOPICS = {
    "pinterest-marketing",
    "etsy-seo",
    "email-marketing",
    "business-strategy",
    "content-creation",
    "product-development",
    "wix-websites",
    "branding",
}

TOPIC_LABELS = {
    "pinterest-marketing": "Pinterest Marketing",
    "etsy-seo": "Etsy SEO",
    "email-marketing": "Email Marketing",
    "business-strategy": "Business Strategy",
    "content-creation": "Content Creation",
    "product-development": "Product Development",
    "wix-websites": "Wix Websites",
    "branding": "Branding",
}

FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}


# ── helpers ────────────────────────────────────────────────────────────────────

def slugify(text, max_len=35):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:max_len].rstrip("-")


def log_error(stage, identifier, message):
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
        "identifier": identifier,
        "error": message,
    })
    ERROR_LOG.write_text(json.dumps(errors, indent=2), encoding="utf-8")


def strip_code_fences(text):
    """Strip markdown code fences Claude adds around JSON responses."""
    text = re.sub(r'^```(?:json)?\s*\n?', '', text.strip())
    text = re.sub(r'\n?```\s*$', '', text).strip()
    return text


def compute_entry_id(canonical):
    return hashlib.sha256(canonical.encode()).hexdigest()[:8]


def load_sources_index():
    if not SOURCES_FILE.exists():
        return {"version": 1, "total_sources": 0, "sources": []}
    try:
        return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "total_sources": 0, "sources": []}


def save_sources_index(index):
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    index["total_sources"] = len(index.get("sources", []))
    SOURCES_FILE.write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── module 1: content fetching ─────────────────────────────────────────────────

def detect_source_type(source):
    if re.search(r'(?:youtube\.com/watch|youtu\.be/)', source):
        return "youtube"
    if re.search(r'\.substack\.com/p/|open\.substack\.com/pub/', source):
        return "substack"
    p = Path(source)
    if p.exists() and p.suffix.lower() == ".pdf":
        return "pdf"
    if source.startswith("http"):
        return "article"
    return "text"


def fetch_youtube(url):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import (
            NoTranscriptFound, TranscriptsDisabled, VideoUnavailable
        )
    except ImportError:
        print("youtube-transcript-api not installed. Run: pip3 install youtube-transcript-api")
        sys.exit(1)

    m = re.search(r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})', url)
    if not m:
        raise ValueError(f"Could not parse video ID from: {url}")
    video_id = m.group(1)

    # Fetch title from YouTube page via og:title
    title = video_id
    try:
        resp = requests.get(url, headers=FETCH_HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].strip()
        elif soup.find("title"):
            raw = soup.find("title").text.strip()
            title = re.sub(r'\s*[-–|]\s*YouTube\s*$', '', raw).strip()
    except Exception:
        pass

    api = YouTubeTranscriptApi()
    try:
        chunks = api.fetch(video_id)
    except (NoTranscriptFound, TranscriptsDisabled) as e:
        raise RuntimeError(
            f"No transcript available for '{title}' ({video_id}).\n"
            f"To ingest this video: download the transcript manually and use:\n"
            f"  nerd_agent.py learn --text \"<transcript>\" --source \"{title}\""
        ) from e
    except VideoUnavailable as e:
        raise RuntimeError(f"Video unavailable: {video_id}") from e

    text = " ".join(c.text for c in chunks)
    word_count = len(text.split())

    if len(text) > MAX_TEXT_CHARS:
        print(f"  Transcript truncated to {MAX_TEXT_CHARS:,} chars (full video ~{word_count // 130} min)")
        text = text[:MAX_TEXT_CHARS]

    return {"type": "youtube", "url": url, "title": title, "text": text, "word_count": word_count}


def fetch_substack(url):
    # Supports both: pub.substack.com/p/slug  and  open.substack.com/pub/pub/p/slug
    m1 = re.match(r'https?://([^.]+\.substack\.com)/p/([^/?#]+)', url)
    m2 = re.match(r'https?://open\.substack\.com/pub/([^/]+)/p/([^/?#]+)', url)

    if m1:
        domain, slug = m1.group(1), m1.group(2)
    elif m2:
        domain = f"{m2.group(1)}.substack.com"
        slug = m2.group(2)
    else:
        raise ValueError(f"Could not parse Substack URL: {url}")

    import apify_fetch
    api_url = f"https://{domain}/api/v1/posts?slug={slug}"
    html = apify_fetch.fetch(api_url, timeout=30)
    if not html:
        raise RuntimeError(f"Could not reach Substack API for: {url}")

    try:
        posts = json.loads(html)
    except json.JSONDecodeError:
        raise RuntimeError(f"Substack API returned unexpected response for: {url}")

    if not isinstance(posts, list) or not posts:
        raise RuntimeError(f"No post data from Substack API for: {url}")

    post = posts[0]
    title = post.get("title", "Untitled Substack Post")
    body_html = post.get("body_html", "")

    if not body_html:
        raise RuntimeError(
            f"Post body empty — likely paywalled.\n"
            f"Copy the full text and run:\n"
            f"  nerd_agent.py learn --text \"<paste>\" --source \"{title}\""
        )

    text = BeautifulSoup(body_html, "html.parser").get_text(separator=" ", strip=True)

    if len(text) < 300:
        raise RuntimeError(
            f"Post content too short ({len(text)} chars) — likely paywalled.\n"
            f"Copy the full text and run:\n"
            f"  nerd_agent.py learn --text \"<paste>\" --source \"{title}\""
        )

    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]

    return {"type": "email", "url": url, "title": title, "text": text, "word_count": len(text.split())}


def fetch_web_page(url):
    import apify_fetch
    html = apify_fetch.fetch(url, timeout=30)
    if not html:
        raise RuntimeError(
            f"Could not fetch: {url}\n"
            f"If the site is behind a login or paywall, copy the content and use:\n"
            f"  nerd_agent.py learn --text \"<paste>\" --source \"Article title\""
        )

    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()
    elif soup.find("title"):
        title = soup.find("title").text.strip()
    else:
        title = url

    # Strip noise tags
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()

    # Prefer article/main body over full page dump
    body = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", id=re.compile(r"content|post|article", re.I))
        or soup.find("div", class_=re.compile(r"content|post|article|entry", re.I))
    )
    text = body.get_text(separator=" ", strip=True) if body else soup.get_text(separator=" ", strip=True)

    # JS-rendered page guard: big HTML but near-empty clean text
    if len(text) < 500 and len(html) > 10_000:
        raise RuntimeError(
            f"Page loaded but content is empty — JavaScript-rendered site.\n"
            f"To ingest this article:\n"
            f"  1. Open the page and select/copy all article text\n"
            f"  2. Run: nerd_agent.py learn --text \"<paste>\" --source \"{title}\""
        )

    if len(text) < 100:
        raise RuntimeError(f"Insufficient content extracted ({len(text)} chars) from: {url}")

    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]

    return {"type": "article", "url": url, "title": title, "text": text, "word_count": len(text.split())}


def fetch_pdf(file_path):
    try:
        import fitz
    except ImportError:
        print("PyMuPDF not installed. Run: pip3 install PyMuPDF")
        sys.exit(1)

    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    doc = fitz.open(str(p))
    pages_text = [page.get_text() for page in doc]
    doc.close()

    text = "\n\n".join(pages_text).strip()

    if len(text) < 100:
        raise RuntimeError(
            f"PDF returned no text — it may be image-based (scanned).\n"
            f"Copy the content manually and use:\n"
            f"  nerd_agent.py learn --text \"<paste>\" --source \"{p.stem}\""
        )

    if len(text) > MAX_TEXT_CHARS:
        print(f"  PDF truncated to {MAX_TEXT_CHARS:,} chars")
        text = text[:MAX_TEXT_CHARS]

    title = p.stem.replace("-", " ").replace("_", " ").title()
    return {"type": "pdf", "url": str(p.resolve()), "title": title, "text": text, "word_count": len(text.split())}


def fetch_content(source, source_type=None):
    stype = source_type or detect_source_type(source)
    if stype == "youtube":
        return fetch_youtube(source)
    if stype == "substack":
        return fetch_substack(source)
    if stype == "pdf":
        return fetch_pdf(source)
    if stype in ("article", "url"):
        return fetch_web_page(source)
    raise ValueError(f"Unknown source type '{stype}' for: {source}")


# ── module 2: claude extraction ────────────────────────────────────────────────

def load_context():
    brand_voice = ""
    product_catalog = ""
    if BRAND_VOICE_FILE.exists():
        brand_voice = BRAND_VOICE_FILE.read_text(encoding="utf-8")[:2000]
    if PRODUCT_CATALOG_FILE.exists():
        product_catalog = PRODUCT_CATALOG_FILE.read_text(encoding="utf-8")[:1500]
    return brand_voice, product_catalog


def extract_insights(content, client):
    brand_voice, product_catalog = load_context()
    topics_list = ", ".join(sorted(ALLOWED_TOPICS))

    prompt = f"""You are the Nerd Agent for Switzertemplates, a digital product business.

Business:
- Products: branding kits ($38), Wix websites ($64), 3-in-1 bundles ($82), Instagram templates ($15)
- Audience: female small business owners, coaches, service providers
- Goal: help customers look professional online fast without hiring a designer

Brand voice (summary):
{brand_voice[:1200]}

Products:
{product_catalog[:1000]}

---

Analyse this {content['type']} and extract structured business insights.

Title: {content['title']}
Content:
{content['text']}

---

Return ONLY a valid JSON object — no preamble, no explanation, just the JSON:

{{
  "topics": ["pick 1-3 from ONLY: {topics_list}"],
  "key_points": ["3-8 specific, concrete points from the source"],
  "summary": "2-3 paragraph plain-text summary of what was learned",
  "business_ideas": [
    {{
      "idea": "specific idea for Switzertemplates based on what was learned",
      "product_relevance": "branding-kit | wix-website | instagram-templates | bundle | email-list | blog | pinterest | etsy",
      "effort": "low | medium | high",
      "topic": "one topic slug from the allowed list"
    }}
  ],
  "actionable_steps": ["3-6 concrete next steps Jane can take right now"]
}}

Rules:
- topics must only use values from the allowed list above
- key_points must be specific and quote-worthy, never vague
- business_ideas must be specific to Switzertemplates products and audience
- actionable_steps must be concrete actions, not generic advice"""

    try:
        resp = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = strip_code_fences(resp.content[0].text)
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        log_error("extraction", content.get("url", "unknown"), f"JSON parse failed: {e}")
        parsed = {
            "topics": [], "key_points": [], "summary": "Extraction failed.",
            "business_ideas": [], "actionable_steps": [],
        }

    # Validate topics — only keep known values
    valid_topics = [t for t in parsed.get("topics", []) if t in ALLOWED_TOPICS]
    if not valid_topics:
        valid_topics = ["business-strategy"]

    return {
        **content,
        "topics": valid_topics,
        "key_points": parsed.get("key_points", []),
        "summary": parsed.get("summary", ""),
        "business_ideas": parsed.get("business_ideas", []),
        "actionable_steps": parsed.get("actionable_steps", []),
    }


# ── module 3: storage ──────────────────────────────────────────────────────────

def store_entry(entry, force=False):
    ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    canonical = entry["url"]
    entry_id = compute_entry_id(canonical)

    index = load_sources_index()
    existing = next((s for s in index["sources"] if s["id"] == entry_id), None)

    if existing and not force:
        print(f"  Already ingested: {existing['title']} ({entry_id}) — use --force to re-process")
        return entry_id

    slug = slugify(entry.get("title", "untitled"))
    filename = f"{entry_id}-{slug}.json"

    entry_data = {
        "id": entry_id,
        "type": entry.get("type", "article"),
        "url": canonical,
        "title": entry.get("title", "Untitled"),
        "date_ingested": date.today().isoformat(),
        "topics": entry.get("topics", []),
        "word_count": entry.get("word_count", 0),
        "key_points": entry.get("key_points", []),
        "summary": entry.get("summary", ""),
        "business_ideas": entry.get("business_ideas", []),
        "actionable_steps": entry.get("actionable_steps", []),
    }

    (ENTRIES_DIR / filename).write_text(
        json.dumps(entry_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    source_record = {
        "id": entry_id,
        "type": entry_data["type"],
        "url": canonical,
        "title": entry_data["title"],
        "author": entry.get("author", ""),
        "date_ingested": entry_data["date_ingested"],
        "topics": entry_data["topics"],
        "word_count": entry_data["word_count"],
        "summary_file": f"entries/{filename}",
        "status": "ok",
    }

    if existing:
        index["sources"] = [
            source_record if s["id"] == entry_id else s
            for s in index["sources"]
        ]
    else:
        index["sources"].append(source_record)

    save_sources_index(index)

    # Append to ingested log
    ingested_log = LOGS_DIR / "ingested.json"
    log_entries = []
    if ingested_log.exists():
        try:
            log_entries = json.loads(ingested_log.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    log_entries.append({
        "date": date.today().isoformat(),
        "id": entry_id,
        "title": entry_data["title"],
        "type": entry_data["type"],
        "topics": entry_data["topics"],
    })
    ingested_log.write_text(json.dumps(log_entries, indent=2), encoding="utf-8")

    return entry_id


# ── module 4: topic reports ────────────────────────────────────────────────────

def load_entries_for_topic(topic):
    index = load_sources_index()
    entries = []
    for src in index["sources"]:
        if topic in src.get("topics", []):
            entry_path = KNOWLEDGE_DIR / src["summary_file"]
            if entry_path.exists():
                try:
                    entries.append(json.loads(entry_path.read_text(encoding="utf-8")))
                except json.JSONDecodeError:
                    pass
    return sorted(entries, key=lambda x: x.get("date_ingested", ""), reverse=True)


def write_topic_report(topic, client):
    entries = load_entries_for_topic(topic)
    if not entries:
        return None

    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    label = TOPIC_LABELS.get(topic, topic.replace("-", " ").title())
    today = date.today().isoformat()

    all_points = []
    all_ideas = []
    all_steps = []
    source_rows = []

    for e in entries:
        all_points.extend(e.get("key_points", []))
        all_ideas.extend(e.get("business_ideas", []))
        all_steps.extend(e.get("actionable_steps", []))
        source_rows.append({
            "title": e.get("title", "Untitled"),
            "type": e.get("type", "article"),
            "date": e.get("date_ingested", ""),
        })

    _, product_catalog = load_context()

    ideas_text = "\n".join(
        f"- [{i.get('product_relevance','?')}] ({i.get('effort','?')}) {i.get('idea','')}"
        for i in all_ideas[:20]
    )
    points_text = "\n".join(f"- {p}" for p in all_points[:30])
    steps_text = "\n".join(f"- {s}" for s in all_steps[:25])
    sources_text = "\n".join(
        f"{i+1}. {s['title']} ({s['type']}, {s['date']})"
        for i, s in enumerate(source_rows)
    )
    table_rows = "\n".join(
        f"| {i+1} | {s['title']} | {s['type']} | {s['date']} |"
        for i, s in enumerate(source_rows)
    )

    prompt = f"""Write a topic insight report for Switzertemplates on: {label}

Synthesise {len(entries)} source(s) into a practical reference document.

Key points from all sources:
{points_text}

Business ideas from all sources:
{ideas_text}

Actionable steps from all sources:
{steps_text}

Sources:
{sources_text}

Product context:
{product_catalog[:800]}

Write in this exact markdown format — nothing before or after:

# Nerd Agent Insights — {label}
*Auto-generated. Last updated: {today}. Sources: {len(entries)}.*

---

## Key Principles

[3-6 bullet points — most important principles, specific and actionable]

---

## Business Ideas for Switzertemplates

### Branding Kit Opportunities
[Ideas relevant to the branding kit product]

### Blog / SEO Opportunities
[Content and SEO angles to pursue]

### Wix Website Opportunities
[Ideas for the Wix website product]

### Pinterest & Social Opportunities
[Pinterest and social media angles]

---

## Actionable Steps

[Numbered list of 5-8 concrete steps Jane should take]

---

## Source List

| # | Title | Type | Date |
|---|-------|------|------|
{table_rows}"""

    try:
        resp = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        report_text = resp.content[0].text.strip()
    except Exception as e:
        log_error("report", topic, str(e))
        print(f"  Error generating report for {topic}: {e}")
        return None

    output_path = INSIGHTS_DIR / f"{topic}.md"
    output_path.write_text(report_text, encoding="utf-8")
    print(f"  Wrote: context/nerd-insights/{topic}.md")
    return output_path


def write_insights_index():
    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    index = load_sources_index()
    today = date.today().isoformat()

    topic_counts = {}
    topic_dates = {}
    for src in index["sources"]:
        for t in src.get("topics", []):
            topic_counts[t] = topic_counts.get(t, 0) + 1
            d = src.get("date_ingested", "")
            if d > topic_dates.get(t, ""):
                topic_dates[t] = d

    lines = [
        "# Nerd Agent — Topic Index",
        f"*Last updated: {today}. Total sources: {index['total_sources']}.*",
        "",
        "| Topic | Sources | Last Updated | Insight File |",
        "|-------|---------|--------------|--------------|",
    ]

    for topic in sorted(topic_counts.keys()):
        label = TOPIC_LABELS.get(topic, topic)
        count = topic_counts[topic]
        last = topic_dates.get(topic, "—")
        file_exists = (INSIGHTS_DIR / f"{topic}.md").exists()
        file_ref = f"[{topic}.md]({topic}.md)" if file_exists else "not yet generated"
        lines.append(f"| {label} | {count} | {last} | {file_ref} |")

    if not topic_counts:
        lines.append("| — | No sources ingested yet | — | — |")

    (INSIGHTS_DIR / "_index.md").write_text("\n".join(lines), encoding="utf-8")


def write_all_topic_reports(client):
    index = load_sources_index()
    topics_with_content = set()
    for src in index["sources"]:
        topics_with_content.update(src.get("topics", []))

    written = []
    for topic in sorted(topics_with_content):
        print(f"  Generating: {TOPIC_LABELS.get(topic, topic)}...")
        path = write_topic_report(topic, client)
        if path:
            written.append(path)
        time.sleep(0.5)

    write_insights_index()
    return written


# ── module 5: dashboard update ─────────────────────────────────────────────────

def update_dashboard():
    if not DASHBOARD_FILE.exists():
        log_error("dashboard", "dashboard_data.json", "File not found")
        return

    try:
        data = json.loads(DASHBOARD_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        log_error("dashboard", "dashboard_data.json", f"Parse error: {e}")
        return

    index = load_sources_index()
    sources = index.get("sources", [])

    topic_summary = {}
    sources_by_type = {"youtube": 0, "article": 0, "email": 0, "pdf": 0}

    for src in sources:
        stype = src.get("type", "article")
        if stype in sources_by_type:
            sources_by_type[stype] += 1
        else:
            sources_by_type[stype] = sources_by_type.get(stype, 0) + 1

        for t in src.get("topics", []):
            if t not in topic_summary:
                topic_summary[t] = {
                    "sources": 0,
                    "actionable_steps": 0,
                    "last_updated": "",
                    "insight_file": f"context/nerd-insights/{t}.md",
                }
            topic_summary[t]["sources"] += 1
            d = src.get("date_ingested", "")
            if d > topic_summary[t]["last_updated"]:
                topic_summary[t]["last_updated"] = d

    # Count actionable steps per topic from entry files
    for t in topic_summary:
        entries = load_entries_for_topic(t)
        topic_summary[t]["actionable_steps"] = sum(
            len(e.get("actionable_steps", [])) for e in entries
        )

    recent = sorted(sources, key=lambda x: x.get("date_ingested", ""), reverse=True)[:10]

    data["nerd_agent"] = {
        "status": "active",
        "last_run": date.today().isoformat(),
        "total_sources_processed": len(sources),
        "topics_covered": sorted(topic_summary.keys()),
        "sources_by_type": sources_by_type,
        "topics": topic_summary,
        "recent_sources": [
            {
                "id": s["id"],
                "title": s["title"],
                "type": s["type"],
                "topics": s.get("topics", []),
                "date_ingested": s.get("date_ingested", ""),
            }
            for s in recent
        ],
    }
    data["last_updated"] = date.today().isoformat()

    try:
        DASHBOARD_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  Dashboard updated ({len(sources)} sources, {len(topic_summary)} topics)")
    except Exception as e:
        log_error("dashboard", "dashboard_data.json", str(e))
        print(f"  Dashboard update failed: {e}")


# ── CLI command handlers ───────────────────────────────────────────────────────

def _learn_single(source, source_type, title_override, force, topics_override, client):
    print(f"  Fetching: {source[:80]}...")

    try:
        content = fetch_content(source, source_type)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"\n  Error: {e}")
        log_error("fetch", source, str(e))
        return

    if title_override:
        content["title"] = title_override

    print(f"  Title:  {content['title']}")
    print(f"  Type:   {content['type']}  |  {content['word_count']:,} words")
    print(f"  Analysing with Claude...")

    entry = extract_insights(content, client)

    if topics_override:
        overrides = [t.strip() for t in topics_override.split(",") if t.strip() in ALLOWED_TOPICS]
        if overrides:
            entry["topics"] = overrides

    print(f"  Topics: {', '.join(entry['topics'])}")
    print(f"  Ideas:  {len(entry['business_ideas'])} business ideas generated")

    entry_id = store_entry(entry, force=force)

    print(f"  Updating topic insight files...")
    for topic in entry["topics"]:
        write_topic_report(topic, client)
    write_insights_index()
    update_dashboard()

    print(f"\n  Done — entry ID: {entry_id}")
    print(f"  Saved: agents/nerd-agent/knowledge/entries/{entry_id}-{slugify(entry['title'])}.json")


def _learn_text(text, source_title, force, topics_override, client):
    canonical = f"text:{source_title}:{hashlib.sha256(text[:200].encode()).hexdigest()[:12]}"

    content = {
        "type": "email",
        "url": canonical,
        "title": source_title,
        "text": text[:MAX_TEXT_CHARS],
        "word_count": len(text.split()),
    }

    print(f"  Title:  {source_title}")
    print(f"  Words:  {content['word_count']:,}")
    print(f"  Analysing with Claude...")

    entry = extract_insights(content, client)

    if topics_override:
        overrides = [t.strip() for t in topics_override.split(",") if t.strip() in ALLOWED_TOPICS]
        if overrides:
            entry["topics"] = overrides

    print(f"  Topics: {', '.join(entry['topics'])}")
    print(f"  Ideas:  {len(entry['business_ideas'])} business ideas generated")

    entry_id = store_entry(entry, force=force)

    for topic in entry["topics"]:
        write_topic_report(topic, client)
    write_insights_index()
    update_dashboard()

    print(f"\n  Done — entry ID: {entry_id}")


def run_learn(args, client):
    if args.batch:
        batch_path = Path(args.batch)
        if not batch_path.exists():
            print(f"Batch file not found: {args.batch}")
            sys.exit(1)
        lines = [
            l.strip() for l in batch_path.read_text().splitlines()
            if l.strip() and not l.startswith("#")
        ]
        print(f"Batch: {len(lines)} sources\n")
        for i, url in enumerate(lines, 1):
            print(f"[{i}/{len(lines)}] {url[:80]}")
            _learn_single(url, None, None, args.force, getattr(args, 'topics', None), client)
            print()
        return

    if args.text:
        source_title = args.source or "Pasted content"
        _learn_text(args.text, source_title, args.force, getattr(args, 'topics', None), client)
        return

    if args.file:
        _learn_single(
            args.file, "pdf", args.source, args.force,
            getattr(args, 'topics', None), client
        )
        return

    if args.url:
        _learn_single(
            args.url, None, args.source, args.force,
            getattr(args, 'topics', None), client
        )
        return

    print("Provide --url, --file, --text, or --batch")
    sys.exit(1)


def run_report(args, client):
    if args.status:
        index = load_sources_index()
        sources = index.get("sources", [])
        print(f"\n  Knowledge base: {len(sources)} source(s)")
        topic_counts = {}
        for src in sources:
            for t in src.get("topics", []):
                topic_counts[t] = topic_counts.get(t, 0) + 1
        if topic_counts:
            print(f"  Topics:")
            for t in sorted(topic_counts):
                label = TOPIC_LABELS.get(t, t)
                has_file = (INSIGHTS_DIR / f"{t}.md").exists()
                flag = "✓" if has_file else "○"
                print(f"    {flag} {label}: {topic_counts[t]} source(s)")
        else:
            print("  No sources ingested yet. Run: nerd_agent.py learn --url <url>")
        return

    if args.all:
        paths = write_all_topic_reports(client)
        update_dashboard()
        print(f"\n  {len(paths)} topic report(s) written to context/nerd-insights/")
        return

    if args.topic:
        if args.topic not in ALLOWED_TOPICS:
            print(f"  Unknown topic: {args.topic}")
            print(f"  Allowed: {', '.join(sorted(ALLOWED_TOPICS))}")
            sys.exit(1)
        path = write_topic_report(args.topic, client)
        write_insights_index()
        update_dashboard()
        if path:
            print(f"\n  Written: {path}")
        else:
            print(f"  No sources found for topic: {args.topic}")
        return

    print("Provide --all, --topic <name>, or --status")


def run_list(args):
    index = load_sources_index()
    sources = index.get("sources", [])

    if args.id:
        match = next((s for s in sources if s["id"] == args.id), None)
        if not match:
            print(f"  No source with ID: {args.id}")
            return
        entry_path = KNOWLEDGE_DIR / match["summary_file"]
        entry = json.loads(entry_path.read_text(encoding="utf-8")) if entry_path.exists() else match
        print(json.dumps(entry, indent=2))
        return

    filtered = sources
    if args.topic:
        filtered = [s for s in filtered if args.topic in s.get("topics", [])]
    if args.type:
        filtered = [s for s in filtered if s.get("type") == args.type]

    if not filtered:
        print("  No sources found.")
        return

    filtered = sorted(filtered, key=lambda x: x.get("date_ingested", ""), reverse=True)
    print(f"\n  {'ID':<10} {'Type':<10} {'Date':<12} {'Topics':<35} Title")
    print(f"  {'-'*8:<10} {'-'*8:<10} {'-'*10:<12} {'-'*33:<35} -----")
    for s in filtered:
        topics_str = ", ".join(s.get("topics", []))[:33]
        title = s.get("title", "")[:52]
        print(f"  {s['id']:<10} {s.get('type',''):<10} {s.get('date_ingested',''):<12} {topics_str:<35} {title}")

    print(f"\n  Total: {len(filtered)} source(s)")


def run_share(args, client):
    if args.topic:
        if args.topic not in ALLOWED_TOPICS:
            print(f"  Unknown topic: {args.topic}")
            sys.exit(1)
        path = write_topic_report(args.topic, client)
        write_insights_index()
        update_dashboard()
        if path:
            print(f"  Written: {path}")
        return

    print("  Refreshing all topic insight files...")
    paths = write_all_topic_reports(client)
    update_dashboard()
    print(f"\n  {len(paths)} insight file(s) written to context/nerd-insights/")
    print(f"  Other agents can load these like any context/*.md file.")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="nerd_agent.py",
        description="Nerd Agent — ingest external resources and extract business insights.",
    )
    sub = parser.add_subparsers(dest="command")

    # learn
    p_learn = sub.add_parser("learn", help="Ingest a new source")
    p_learn.add_argument("--url",    help="URL to ingest (YouTube, blog, Substack, etc.)")
    p_learn.add_argument("--file",   help="Path to a PDF file")
    p_learn.add_argument("--text",   help="Raw text content to ingest (newsletter, course notes, etc.)")
    p_learn.add_argument("--batch",  help="Path to a text file with one URL per line")
    p_learn.add_argument("--source", help="Title/label override (for --text or --file)")
    p_learn.add_argument("--topics", help="Override auto-detected topics (comma-separated): " + ", ".join(sorted(ALLOWED_TOPICS)))
    p_learn.add_argument("--force",  action="store_true", help="Re-process even if already ingested")

    # report
    p_report = sub.add_parser("report", help="Generate/refresh topic insight files")
    g = p_report.add_mutually_exclusive_group(required=True)
    g.add_argument("--all",    action="store_true", help="Regenerate all topic reports")
    g.add_argument("--topic",  help="Regenerate one topic report")
    g.add_argument("--status", action="store_true", help="Show knowledge base status (no writes)")

    # list
    p_list = sub.add_parser("list", help="Browse the knowledge base")
    p_list.add_argument("--topic", help="Filter by topic")
    p_list.add_argument("--type",  help="Filter by type: youtube, article, email, pdf")
    p_list.add_argument("--id",    help="Show full detail for one entry by ID")

    # share
    p_share = sub.add_parser("share", help="Write insight files to context/ and update dashboard")
    p_share.add_argument("--topic", help="Share only one specific topic")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    print("═" * 60)
    print("  Nerd Agent — Switzertemplates")
    print("═" * 60)

    # list and status don't need Claude
    if args.command == "list":
        run_list(args)
        print("═" * 60)
        return

    if args.command == "report" and getattr(args, "status", False):
        run_report(args, None)
        print("═" * 60)
        return

    if not ANTHROPIC_API_KEY:
        print("  Error: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if args.command == "learn":
        run_learn(args, client)
    elif args.command == "report":
        run_report(args, client)
    elif args.command == "share":
        run_share(args, client)

    print("═" * 60)


if __name__ == "__main__":
    main()
