#!/usr/bin/env python3
"""
Canva Publisher — generates Pinterest pin copy and validates it against
Canva design structure, then outputs operations JSON for Claude to apply
via Canva MCP tools.

Architecture note:
  The Canva editing transaction API is only accessible through Claude Code's
  MCP runtime (which manages its own OAuth tokens). This script handles the
  parts Python can own cleanly:
    Steps 1-3  parse design structure, exclude watermarks, classify elements
    Steps 4-5  generate copy via Claude API, validate character limits
    Step 6-out write operations JSON for Claude to apply via MCP

  When run in --full-run mode, Claude orchestrates the Canva MCP calls and
  calls this script for the copy-generation portion via Bash.

Usage (called by Claude orchestrator):
  # Generate copy for a single page (keyword auto-resolved from topics JSON)
  python3 skills/pinterest-agent/canva_publisher.py \\
      --page-structure /tmp/page1_txn.json \\
      --page 1 \\
      --output /tmp/page1_edits.json

  # With explicit keyword and superlatives tracking
  python3 skills/pinterest-agent/canva_publisher.py \\
      --page-structure /tmp/page1_txn.json \\
      --page 1 \\
      --keyword "coach websites" \\
      --superlatives-used "best,simple" \\
      --output /tmp/page1_edits.json

  # Full test run (orchestrated by Claude)
  python3 skills/pinterest-agent/canva_publisher.py --full-run

Output (--output file):
  {
    "transaction_id":    "...",
    "pages":             [...],
    "page_index":        1,
    "operations":        [{"type": "replace_text", "element_id": "...", "text": "..."}, ...],
    "summary":           [{"role": "headline", "element_id": "...", "new_text": "...", "word_count": 4}],
    "superlatives_used": ["best"]
  }
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR   = PROJECT_ROOT / "outputs" / "pins" / "canva-publisher"

load_dotenv(PROJECT_ROOT / ".env")


# ─── Step 1: Parse page structure from MCP transaction data ──────────────

def parse_page_structure(txn_data: dict, page_number: int) -> dict:
    """
    Extract editable text elements from start-editing-transaction response.

    Watermark elements (containing 'switzertemplates.com') are excluded.
    SHAPE-type containers with no regions are also excluded.

    Returns:
        transaction_id : str
        pages          : list[dict]
        editable_slots : list[dict]  — {element_id, current_text, width, height}
    """
    transaction_id = txn_data["transaction"]["transaction_id"]
    pages          = txn_data.get("pages", [])
    all_richtexts  = txn_data.get("richtexts", [])

    page_texts = [
        rt for rt in all_richtexts
        if rt.get("page_index") == page_number
        and rt.get("containerElement", {}).get("type") == "TEXT"
        and rt.get("regions")
    ]

    editable_slots: list[dict] = []
    for rt in page_texts:
        text = "".join(r.get("text", "") for r in rt["regions"]).strip()
        el   = rt["containerElement"]
        dim  = el.get("dimension", {})
        w    = round(dim.get("width",  0), 2)
        h    = round(dim.get("height", 0), 2)

        if "switzertemplates.com" in text.lower():
            continue  # watermark — skip silently

        if len(text) <= 3:
            continue  # decorative element — skip silently

        editable_slots.append({
            "element_id":   rt["element_id"],
            "current_text": text,
            "width":        w,
            "height":       h,
        })

    return {
        "transaction_id": transaction_id,
        "pages":          pages,
        "editable_slots": editable_slots,
    }


# ─── Step 2: Character limits ─────────────────────────────────────────────

def char_limit(current_text: str) -> int:
    return max(20, len(current_text))


# ─── Step 3: Classify element roles via pin-architecture.json ────────────

_WORD_LIMITS: dict[str, int] = {"headline": 7, "body": 5, "cta": 4}
_ARCH_FILE = PROJECT_ROOT / "context" / "pin-architecture.json"


def _load_architecture() -> dict:
    return json.loads(_ARCH_FILE.read_text())


def classify_elements(slots: list[dict], page_number: int) -> list[dict]:
    """
    Assigns roles from context/pin-architecture.json — no height logic.
    Elements not listed in the architecture for this page are silently skipped.
    """
    arch      = _load_architecture()
    page_arch = arch.get("pages", {}).get(str(page_number), {})
    id_to_role = {eid: role for role, eid in page_arch.get("elements", {}).items()}

    result = []
    for s in slots:
        role = id_to_role.get(s["element_id"])
        if role is None:
            continue
        s = dict(s)
        s["role"]      = role
        s["max_chars"] = char_limit(s["current_text"])
        s["max_words"] = _WORD_LIMITS.get(role, 7)
        result.append(s)

    return result


# ─── Step 4: Generate copy via Claude API ────────────────────────────────

_COPY_RULES_FILE = PROJECT_ROOT / "context" / "Pin-TEXTS-HOOKS-CTAs.txt"


def _load_copy_rules() -> str:
    if _COPY_RULES_FILE.exists():
        return _COPY_RULES_FILE.read_text().strip()
    return ""


def _build_system_prompt() -> str:
    rules = _load_copy_rules()
    prompt = (
        "You are a Pinterest pin copy writer for Switzer Templates, a digital product business "
        "selling Canva templates, Wix website templates, branding kits and Instagram templates "
        "to small business owners and Etsy sellers.\n\n"
        "Rules:\n\n"
        "- Write in plain language, active voice, sentence case\n"
        "- Never use all caps\n"
        "- No hashtags\n"
        "- The keyword drives everything — it must appear naturally in the headline\n"
        "- Headline and body must work as one connected thought — body completes or extends the "
        "headline, never starts a new idea\n"
        "- No comma-pause constructions like 'Your website, ready to launch' — use straight "
        "natural statements only\n"
        "- Rotate superlatives across pins — best, perfect, ideal, top, great, proven, simple, "
        "easy — never use the same one twice in the same batch\n"
        "- Use proven Pinterest formulas: number + keyword + outcome, best/top/ideal + keyword + "
        "benefit, how to + outcome, problem + fix\n"
        "- CTA should feel like browsing not pressure — examples: 'View the template', "
        "'Save this list', 'Shop the kit', 'Read the guide', 'Get the template'\n"
        "- Never identify a specific product — the keyword drives the copy, not the product"
    )
    if rules:
        prompt += f"\n\nPinterest copy rules reference:\n\n{rules}"
    return prompt


_SUPERLATIVES = ["best", "perfect", "ideal", "top", "great", "proven", "simple", "easy"]


def extract_superlatives(elements: list[dict]) -> list[str]:
    found = []
    for el in elements:
        words = set(re.sub(r"[^\w\s]", "", el.get("new_text", "").lower()).split())
        for sup in _SUPERLATIVES:
            if sup in words and sup not in found:
                found.append(sup)
    return found


def _ensure_sentence_case(elements: list[dict]) -> list[dict]:
    for el in elements:
        text = el.get("new_text", "")
        if text and text[0].islower():
            el["new_text"] = text[0].upper() + text[1:]
    return elements


def extract_by_role(elements: list[dict], classified: list[dict], role: str) -> list[str]:
    role_map = {s["element_id"]: s["role"] for s in classified}
    return [el["new_text"] for el in elements if role_map.get(el["element_id"]) == role]


_STOP_WORDS = {
    "a", "an", "the", "for", "of", "to", "in", "on", "at", "by",
    "with", "and", "or", "but", "that", "this", "is", "are", "was",
    "were", "be", "been", "your", "my", "their", "our", "its",
    "you", "it", "how", "what", "why", "which", "who", "these",
    "more", "most", "some", "any", "all", "no", "not", "than",
}


def extract_headline_phrases(elements: list[dict], classified: list[dict]) -> list[str]:
    """Extract 2-word content phrases from headline copy for batch deduplication."""
    headlines = extract_by_role(elements, classified, "headline")
    phrases = []
    for headline in headlines:
        words = re.sub(r"[^\w\s]", "", headline.lower()).split()
        content_words = [w for w in words if w not in _STOP_WORDS]
        for i in range(len(content_words) - 1):
            phrase = f"{content_words[i]} {content_words[i + 1]}"
            if phrase not in phrases:
                phrases.append(phrase)
    return phrases


def _user_prompt(
    classified: list[dict],
    keyword: str,
    superlatives_used: list[str],
    body_lines_used: list[str],
    ctas_used: list[str],
    headline_phrases_used: list[str],
    retry_note: str = "",
) -> str:
    slots = "\n".join(
        f"- element_id: {s['element_id']}\n"
        f"  Role: {s['role']}\n"
        f"  Max words: {s['max_words']}\n"
        f"  Current placeholder text (for context only): {s['current_text']}"
        for s in classified
    )
    sup_str      = ", ".join(superlatives_used) if superlatives_used else "none yet"
    body_str     = ", ".join(f'"{b}"' for b in body_lines_used) if body_lines_used else "none yet"
    cta_str      = ", ".join(f'"{c}"' for c in ctas_used) if ctas_used else "none yet"
    phrases_str  = ", ".join(f'"{p}"' for p in headline_phrases_used) if headline_phrases_used else "none yet"
    return (
        f"Write Pinterest pin copy for the following text slots. "
        f"The keyword for this pin is: {keyword}\n\n"
        "STRICT RULES:\n\n"
        "- headline role: maximum 7 words. Use the keyword naturally. "
        "Use a proven Pinterest formula from the rules file.\n"
        "- body role: maximum 5 words. Must add NEW information that extends the headline — "
        "not describe the template or repeat what the headline already said. Never repeat a "
        "word from the headline. "
        "Good examples: 'Best coach websites that convert clients' → body: 'without hiring a designer'. "
        "'Top Wix templates for small businesses' → body: 'a website in a weekend'. "
        "Bad examples (describe the template, not the client benefit): 'ready to customize', "
        "'built and ready fast', 'everything included', 'ready to launch this week' — these "
        "describe the template, not the client benefit. Always extend the headline with a "
        "client-focused thought, a price/effort contrast, or a specific outcome.\n"
        "- cta role: maximum 4 words. Soft browsing CTA only. Action verb first.\n"
        f"- Never use the same superlative as other pins in this batch. "
        f"Superlatives used so far in this batch: {sup_str}\n"
        f"- Never repeat a body line used earlier in this batch. "
        f"Previously used body lines: {body_str}\n"
        f"- Never repeat a CTA used earlier in this batch. "
        f"Previously used CTAs: {cta_str}\n"
        f"- Never repeat a key phrase used in a previous headline in this batch. "
        f"Previously used headline phrases: {phrases_str}\n\n"
        f"{retry_note}"
        f"Text slots:\n{slots}\n\n"
        "Return JSON only with no preamble or markdown:\n"
        "{\n"
        '  "elements": [\n'
        '    {"element_id": "...", "new_text": "..."},\n'
        "    ...\n"
        "  ]\n"
        "}"
    )


def generate_copy(
    classified: list[dict],
    keyword: str,
    superlatives_used: list[str],
    body_lines_used: list[str],
    ctas_used: list[str],
    headline_phrases_used: list[str],
    api_key: str,
    retry_note: str = "",
) -> list[dict]:
    client  = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_build_system_prompt(),
        messages=[{"role": "user", "content": _user_prompt(
            classified, keyword, superlatives_used, body_lines_used,
            ctas_used, headline_phrases_used, retry_note
        )}],
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$",          "", raw)
    # Extract the first complete balanced JSON object to handle trailing content
    start = raw.find('{')
    if start != -1:
        depth = 0
        for i, ch in enumerate(raw[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    raw = raw[start:i + 1]
                    break
    return json.loads(raw).get("elements", [])


# ─── Step 5: Validate character limits ────────────────────────────────────

def validate_and_retry(
    classified: list[dict],
    generated: list[dict],
    keyword: str,
    superlatives_used: list[str],
    body_lines_used: list[str],
    ctas_used: list[str],
    headline_phrases_used: list[str],
    api_key: str,
) -> list[dict]:
    limit_map = {s["element_id"]: s["max_words"] for s in classified}

    def violations(elements: list[dict]) -> list[str]:
        out = []
        for el in elements:
            eid   = el["element_id"]
            text  = el.get("new_text", "")
            limit = limit_map.get(eid, 999)
            wc    = len(text.split())
            if wc > limit:
                out.append(
                    f"element_id={eid} is {wc} words (max {limit}): \"{text}\""
                )
        return out

    # Fix 3: sentence case before any validation
    current = _ensure_sentence_case(generated)

    for attempt in range(3):
        bad = violations(current)
        if not bad:
            return current
        if attempt >= 2:
            break
        note = (
            "IMPORTANT — the previous response exceeded word limits. "
            "These elements MUST be shorter:\n"
            + "\n".join(f"  • {v}" for v in bad)
            + "\n\n"
        )
        current = _ensure_sentence_case(
            generate_copy(
                classified, keyword, superlatives_used, body_lines_used,
                ctas_used, headline_phrases_used, api_key, note
            )
        )

    # Hard-truncate any remaining violations (drop words beyond limit)
    for el in current:
        limit = limit_map.get(el["element_id"], 999)
        words = el.get("new_text", "").split()
        if len(words) > limit:
            el["new_text"] = " ".join(words[:limit])
    return current


# ─── Main: generate copy for one page ────────────────────────────────────

def generate_page_copy(
    txn_data: dict,
    page_number: int,
    keyword: str,
    api_key: str,
    superlatives_used: list[str] | None = None,
    body_lines_used: list[str] | None = None,
    ctas_used: list[str] | None = None,
    headline_phrases_used: list[str] | None = None,
) -> dict:
    """
    Full steps 1–5 for one page.

    Returns a dict ready for Claude to pass to perform-editing-operations:
      {
        "transaction_id":       str,
        "pages":                list[dict],
        "page_index":           int,
        "operations":           list[{"type": "replace_text", "element_id": str, "text": str}],
        "summary":              list[{"role": str, "element_id": str, "new_text": str, "word_count": int}],
        "superlatives_used":    list[str]   — superlatives found in this page's copy
        "body_lines_used":      list[str]   — body lines found in this page's copy
        "ctas_used":            list[str]   — CTAs found in this page's copy
        "headline_phrases_used": list[str]  — 2-word content phrases from this page's headlines
      }
    """
    if superlatives_used is None:
        superlatives_used = []
    if body_lines_used is None:
        body_lines_used = []
    if ctas_used is None:
        ctas_used = []
    if headline_phrases_used is None:
        headline_phrases_used = []

    # Steps 1–3
    ctx        = parse_page_structure(txn_data, page_number)
    slots      = ctx["editable_slots"]
    classified = classify_elements(slots, page_number)

    print(f"  Page {page_number}: {len(classified)} editable slot(s)")
    for s in classified:
        print(f"    {s['role']:8s}  h={s['height']:6.1f}px  "
              f"max={s['max_words']}w  '{s['current_text'][:45]}'")

    if not classified:
        return {
            "transaction_id":        ctx["transaction_id"],
            "pages":                 ctx["pages"],
            "page_index":            page_number,
            "operations":            [],
            "summary":               [],
            "superlatives_used":     [],
            "body_lines_used":       [],
            "ctas_used":             [],
            "headline_phrases_used": [],
        }

    # Steps 4–5
    generated = generate_copy(
        classified, keyword, superlatives_used, body_lines_used,
        ctas_used, headline_phrases_used, api_key
    )
    validated = validate_and_retry(
        classified, generated, keyword, superlatives_used, body_lines_used,
        ctas_used, headline_phrases_used, api_key
    )

    # Build output
    operations = [
        {"type": "replace_text", "element_id": el["element_id"], "text": el["new_text"]}
        for el in validated
    ]
    limit_map             = {s["element_id"]: s for s in classified}
    summary               = [
        {
            "role":       limit_map[el["element_id"]]["role"],
            "element_id": el["element_id"],
            "new_text":   el["new_text"],
            "word_count": len(el["new_text"].split()),
        }
        for el in validated
        if el["element_id"] in limit_map
    ]
    new_superlatives      = extract_superlatives(validated)
    new_body_lines        = extract_by_role(validated, classified, "body")
    new_ctas              = extract_by_role(validated, classified, "cta")
    new_headline_phrases  = extract_headline_phrases(validated, classified)

    print(f"  Generated copy:")
    for s in summary:
        print(f"    {s['role']:8s}  {s['word_count']:2d}w  \"{s['new_text']}\"")
    if new_superlatives:
        print(f"  Superlatives used: {new_superlatives}")

    return {
        "transaction_id":        ctx["transaction_id"],
        "pages":                 ctx["pages"],
        "page_index":            page_number,
        "operations":            operations,
        "summary":               summary,
        "superlatives_used":     new_superlatives,
        "body_lines_used":       new_body_lines,
        "ctas_used":             new_ctas,
        "headline_phrases_used": new_headline_phrases,
    }


# ─── Keyword lookup from topics JSON ─────────────────────────────────────

_DEFAULT_TOPICS_FILE = PROJECT_ROOT / "data" / "pinterest-agent" / "topics-2026-04-30.json"


def keyword_for_page(page_number: int, topics_file: Path | None = None) -> str:
    tf = topics_file or _DEFAULT_TOPICS_FILE
    data   = json.loads(tf.read_text())
    topics = data.get("topics", [])
    idx    = (page_number - 1) // 5
    if idx < len(topics):
        return topics[idx].get("keyword", "")
    return ""


# ─── CLI ──────────────────────────────────────────────────────────────────

def _cli() -> None:
    parser = argparse.ArgumentParser(description="Generate Pinterest copy for a Canva design page.")
    parser.add_argument("--page-structure",  type=Path,
                        help="JSON file from start-editing-transaction MCP response")
    parser.add_argument("--page",            type=int, default=1)
    parser.add_argument("--keyword",         type=str, default="",
                        help="Pinterest keyword for this pin (auto-resolved from topics JSON if omitted)")
    parser.add_argument("--topics-json",     type=Path, default=None,
                        help="Topics JSON to resolve keyword from (default: topics-2026-04-30.json)")
    parser.add_argument("--superlatives-used", type=str, default="",
                        help="Comma-separated superlatives already used earlier in this batch")
    parser.add_argument("--body-lines-used",   type=str, default="",
                        help="Pipe-separated body lines already used earlier in this batch")
    parser.add_argument("--ctas-used",             type=str, default="",
                        help="Pipe-separated CTAs already used earlier in this batch")
    parser.add_argument("--headline-phrases-used", type=str, default="",
                        help="Pipe-separated 2-word headline phrases already used earlier in this batch")
    parser.add_argument("--output",            type=Path, default=None,
                        help="Write result JSON here (default: stdout)")
    parser.add_argument("--full-run",          action="store_true",
                        help="Print orchestration instructions (Claude drives the Canva MCP calls)")
    args = parser.parse_args()

    if args.full_run:
        _print_full_run_instructions()
        return

    if not args.page_structure or not args.page_structure.exists():
        print("Error: --page-structure <json_file> is required.", file=sys.stderr)
        sys.exit(1)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    keyword = args.keyword or keyword_for_page(args.page, args.topics_json)
    if not keyword:
        print("Error: --keyword is required (or provide --topics-json to auto-resolve).",
              file=sys.stderr)
        sys.exit(1)

    superlatives_used = (
        [s.strip() for s in args.superlatives_used.split(",") if s.strip()]
        if args.superlatives_used else []
    )
    body_lines_used = (
        [b.strip() for b in args.body_lines_used.split("|") if b.strip()]
        if args.body_lines_used else []
    )
    ctas_used = (
        [c.strip() for c in args.ctas_used.split("|") if c.strip()]
        if args.ctas_used else []
    )
    headline_phrases_used = (
        [p.strip() for p in args.headline_phrases_used.split("|") if p.strip()]
        if args.headline_phrases_used else []
    )

    txn_data = json.loads(args.page_structure.read_text())
    result   = generate_page_copy(
        txn_data, args.page, keyword, api_key,
        superlatives_used, body_lines_used, ctas_used, headline_phrases_used
    )

    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out)
        print(f"\n  Written to: {args.output}")
    else:
        print(out)


def _print_full_run_instructions() -> None:
    """
    Print the design IDs and page map for the test run.
    Claude calls this to remember the orchestration plan.
    """
    topics_file = _DEFAULT_TOPICS_FILE
    page_map: dict[int, str] = {}
    if topics_file.exists():
        data   = json.loads(topics_file.read_text())
        topics = data.get("topics", [])
        for page in range(1, 26):
            kw = keyword_for_page(page)
            page_map[page] = kw
    plan = {
        "design_id":   "DAHJa5-fxUQ",
        "design_name": "Pinterest-Pins-01",
        "pages":       page_map,
        "script":      str(Path(__file__).resolve()),
        "temp_dir":    "/tmp/canva_publisher",
        "output_dir":  str(OUTPUT_DIR),
    }
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    _cli()
