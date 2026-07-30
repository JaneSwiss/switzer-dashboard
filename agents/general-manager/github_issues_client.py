"""
GitHub Issues client — General Manager

Thin wrapper over GitHub's REST API for the recommend/approve exchange: Step 1 opens an
issue with the week's recommendation, Step 2 polls it for Jane's comment. No threading-
header fragility to worry about (unlike the email-reply design this replaced) — a comment
is unambiguously attached to its issue.

Setup: GITHUB_TOKEN (already in .env, used for git pushes) needs "issues: write" scope —
check under GitHub Settings > Developer settings > Personal access tokens if this client
returns a 403.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO = "JaneSwiss/switzer-dashboard"
API_BASE = "https://api.github.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def create_issue(title: str, body: str) -> dict:
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not set in .env")

    resp = requests.post(
        f"{API_BASE}/repos/{REPO}/issues",
        headers=_headers(),
        json={"title": title, "body": body},
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"GitHub create_issue failed {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    return {"number": data["number"], "url": data["html_url"]}


def fetch_new_comments(issue_number: int, since: str) -> "list[str]":
    """
    Returns the text of every comment on the issue created after `since` (ISO date/
    datetime string). Empty list if none yet — that's the expected common case, not
    an error.
    """
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not set in .env")

    params = {"since": since} if since else {}
    resp = requests.get(
        f"{API_BASE}/repos/{REPO}/issues/{issue_number}/comments",
        headers=_headers(),
        params=params,
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"GitHub fetch_new_comments failed {resp.status_code}: {resp.text[:300]}")

    return [c["body"] for c in resp.json()]


def close_issue(issue_number: int, comment: str | None = None) -> None:
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not set in .env")

    if comment:
        requests.post(
            f"{API_BASE}/repos/{REPO}/issues/{issue_number}/comments",
            headers=_headers(),
            json={"body": comment},
            timeout=20,
        )

    resp = requests.patch(
        f"{API_BASE}/repos/{REPO}/issues/{issue_number}",
        headers=_headers(),
        json={"state": "closed"},
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"GitHub close_issue failed {resp.status_code}: {resp.text[:300]}")
