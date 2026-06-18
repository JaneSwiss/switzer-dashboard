#!/usr/bin/env python3
"""
One-time helper: looks up your member ID as site owner, needed for WIX_MEMBER_ID
in .env so publish_to_wix.py can create draft posts under your name.

Run after WIX_API_KEY and WIX_SITE_ID are set in .env:
    python3 agents/blog-seo-agent/find_wix_member_id.py
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

WIX_API_KEY = os.getenv("WIX_API_KEY", "")
WIX_SITE_ID = os.getenv("WIX_SITE_ID", "")


def main() -> None:
    if not (WIX_API_KEY and WIX_SITE_ID):
        print("Set WIX_API_KEY and WIX_SITE_ID in .env first.")
        return

    resp = requests.post(
        "https://www.wixapis.com/members/v1/members/query",
        headers={
            "Authorization": WIX_API_KEY,
            "wix-site-id": WIX_SITE_ID,
            "Content-Type": "application/json",
        },
        json={"query": {"paging": {"limit": 20}}, "fieldsets": ["FULL"]},
        timeout=30,
    )
    if not resp.ok:
        print(f"Error {resp.status_code}: {resp.text}")
        return

    members = resp.json().get("members", [])
    if not members:
        print("No members found. The site owner may not appear as a 'member' — "
              "check Wix dashboard > Settings > Site Members to find your profile manually.")
        return

    print(f"Found {len(members)} member(s):\n")
    for m in members:
        contact = m.get("contact", {})
        name = f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip()
        email = contact.get("emails", [{}])
        email = email[0].get("email", "") if email else ""
        print(f"  id: {m.get('id')}  |  name: {name or '(no name)'}  |  email: {email}")

    print("\nCopy the id that matches you (the site owner) into WIX_MEMBER_ID in .env.")


if __name__ == "__main__":
    main()
