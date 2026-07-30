"""
Interpret Reply — General Manager

One Claude call: takes the original candidate keywords (with reasoning) from Step 1's
recommendation, plus Jane's actual GitHub comment(s), and works out what she approved,
rejected, or asked for instead — in her own words, not a rigid "reply yes" format.

Deliberately conservative: if the comment doesn't resolve to a clear decision, returns
empty approved/new_requests so the caller leaves the recommendation pending rather than
guessing and starting real production work on an unclear signal.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

SYSTEM_PROMPT = """You interpret one reply from Jane, the owner of Switzertemplates, on a \
GitHub issue where the General Manager (an automated content system) proposed keywords to \
write blog posts about this week.

Your job: read her comment(s) and work out exactly what she wants — which of the proposed \
keywords she approved, which she rejected, and whether she asked for anything not on the \
original list (a genuinely new topic/keyword idea).

She writes naturally, not in any fixed format — "yes to the first one, skip the branding \
one, maybe do something about email marketing instead" is a completely normal reply. Do \
not require exact keyword matches; match her intent to the closest candidate.

Be conservative. If her comment is genuinely ambiguous, off-topic, or doesn't clearly \
approve or request anything (e.g. "let me think about it", "not sure yet", a question back \
to the system), return empty approved/rejected/new_requests lists rather than guessing —
someone will check again after her next comment.

If she approves ALL candidates with something like "yes" / "go ahead" / "sounds good" and \
nothing else, treat every candidate as approved.

Return ONLY valid JSON, this exact shape, no markdown fences, no commentary:
{
  "approved": ["<keyword text, exactly as it appeared in the candidate list>", ...],
  "rejected": ["<keyword text>", ...],
  "new_requests": ["<a new topic/keyword she asked for that wasn't a candidate>", ...],
  "notes": "<one sentence summarizing what she said, for the completion email later>"
}"""


def _build_user_prompt(candidates: "list[dict]", comments: "list[str]") -> str:
    candidate_lines = "\n".join(
        f"- \"{c['keyword']}\" — reasoning given: {c.get('reasoning', '')}"
        for c in candidates
    )
    comments_block = "\n\n---\n\n".join(comments)
    return f"""ORIGINAL CANDIDATES PROPOSED:
{candidate_lines}

JANE'S COMMENT(S) ON THE ISSUE:
{comments_block}

What did she decide?"""


def interpret_reply(candidates: "list[dict]", comments: "list[str]") -> dict:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")
    if not comments:
        return {"approved": [], "rejected": [], "new_requests": [], "notes": ""}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(candidates, comments)}],
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        decision = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise RuntimeError(f"Could not parse interpretation response: {raw[:300]}")
        decision = json.loads(match.group())

    for key in ("approved", "rejected", "new_requests"):
        decision.setdefault(key, [])
    decision.setdefault("notes", "")
    return decision
