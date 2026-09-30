from __future__ import annotations

import csv
import os
import json
import requests
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore


BASE_URL = "https://api-v1.tailwind.ai/v1"

_SYDNEY = ZoneInfo("Australia/Sydney")
_SLOT_HOURS = [9, 13, 17, 20]  # 9am, 1pm, 5pm, 8pm Sydney time


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.getenv('TAILWIND_API_KEY', '')}",
        "Content-Type": "application/json",
    }


def _get_account_id() -> str:
    """
    Return the Tailwind account ID to use.
    Uses TAILWIND_ACCOUNT_ID from .env if set; otherwise returns the first account.
    Response shape: {"data": {"accounts": [{"id": "...", "username": "...", ...}]}}
    """
    explicit = os.getenv("TAILWIND_ACCOUNT_ID", "").strip()
    if explicit:
        return explicit

    resp = requests.get(f"{BASE_URL}/accounts", headers=_headers(), timeout=10)
    resp.raise_for_status()
    body = resp.json()
    accounts = body.get("data", {}).get("accounts", [])
    if not accounts:
        raise RuntimeError("No Pinterest accounts found in Tailwind.")
    return str(accounts[0]["id"])


def _fetch_boards(account_id: str) -> list[dict]:
    """Return all boards for an account. Response shape: {"data": {"boards": [...]}}"""
    resp = requests.get(
        f"{BASE_URL}/accounts/{account_id}/boards",
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("data", {}).get("boards", [])


def _resolve_board_id(account_id: str) -> str:
    """
    Return the board ID to post to.
    Checks TAILWIND_BOARD_ID first; if not set, resolves TAILWIND_BOARD_NAME via the boards API.
    Returns empty string to create an unscheduled draft with no board assigned.
    """
    board_id = os.getenv("TAILWIND_BOARD_ID", "").strip()
    if board_id:
        return board_id

    board_name = os.getenv("TAILWIND_BOARD_NAME", "").strip().lower()
    if not board_name:
        return ""

    boards = _fetch_boards(account_id)
    for b in boards:
        if b.get("name", "").strip().lower() == board_name:
            return str(b["id"])

    raise RuntimeError(
        f"Board '{os.getenv('TAILWIND_BOARD_NAME')}' not found in Tailwind. "
        f"Run --list-boards to see all available boards."
    )


def _slot_sequence(after_utc: datetime) -> Iterator[datetime]:
    """Yield future UTC datetimes, one per slot, cycling through _SLOT_HOURS in Sydney time."""
    current_date = after_utc.astimezone(_SYDNEY).date()
    while True:
        for hour in _SLOT_HOURS:
            slot_syd = datetime(
                current_date.year, current_date.month, current_date.day,
                hour, 0, 0, tzinfo=_SYDNEY,
            )
            slot_utc = slot_syd.astimezone(timezone.utc)
            if slot_utc > after_utc:
                yield slot_utc
        current_date += timedelta(days=1)


def _schedule_start(account_id: str) -> datetime:
    """Return UTC datetime to begin scheduling from — after the latest already-scheduled post."""
    now_utc = datetime.now(timezone.utc)
    try:
        resp = requests.get(
            f"{BASE_URL}/accounts/{account_id}/posts",
            headers=_headers(),
            params={"status": "scheduled", "limit": 200},
            timeout=10,
        )
        if resp.status_code == 200:
            posts = resp.json().get("data", {}).get("posts", [])
            latest = now_utc
            for p in posts:
                for key in ("sendAt", "send_at", "scheduledAt", "scheduled_at"):
                    raw = p.get(key)
                    if raw:
                        try:
                            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                            if dt > latest:
                                latest = dt
                        except ValueError:
                            pass
                        break
            return latest
    except Exception:
        pass
    return now_utc


def list_boards() -> list[dict]:
    """
    Utility — returns all own (non-collaborator) boards, sorted by name.
    Called by main.py --list-boards so Jane can find the right board ID/name.
    """
    account_id = _get_account_id()
    boards = _fetch_boards(account_id)
    own = [b for b in boards if not b.get("isCollaborator", False)]
    return sorted(own, key=lambda b: b.get("name", "").lower())


def submit_to_tailwind(approved_pins: list[dict], schedule: bool = True) -> list[dict]:
    """
    Submit approved pins to Tailwind via POST /accounts/{id}/posts.

    When schedule=True (default), each pin is assigned a future sendAt timestamp:
    slots at 9am / 1pm / 5pm / 8pm Sydney time, starting after the latest already-
    scheduled post, one pin per slot. Pins go live automatically — no manual scheduling.

    When schedule=False, omits sendAt and pins land as unscheduled drafts.

    Requires TAILWIND_API_KEY. Uses TAILWIND_BOARD_ID or resolves from TAILWIND_BOARD_NAME.
    Returns list of {"index", "success", "message", "mode", "send_at"} dicts.
    """
    results = []

    try:
        account_id = _get_account_id()
    except Exception as e:
        return [
            {"index": p.get("index"), "success": False,
             "message": f"Could not get Tailwind account: {e}", "mode": "queue"}
            for p in approved_pins
        ]

    try:
        board_id = _resolve_board_id(account_id)
    except Exception as e:
        return [
            {"index": p.get("index"), "success": False,
             "message": str(e), "mode": "queue"}
            for p in approved_pins
        ]

    # Build slot iterator starting after the last already-scheduled post
    slots = _slot_sequence(_schedule_start(account_id)) if schedule else None

    for pin in approved_pins:
        idx = pin.get("index", "?")
        image_url = pin.get("image_url", "")

        if not image_url:
            results.append({
                "index": idx, "success": False,
                "message": "No image URL — upload to Cloudinary first",
                "mode": "queue",
            })
            continue

        title = (pin.get("tailwind_title", "") or pin.get("seo_title", ""))[:100]
        description = (pin.get("tailwind_description", "") or pin.get("seo_description", ""))[:500]

        payload: dict = {
            "mediaUrl":    image_url,
            "title":       title,
            "description": description,
            "url":         pin.get("link", "https://www.switzertemplates.com"),
            "altText":     title,
        }
        if board_id:
            payload["boardId"] = board_id

        send_at_str = None
        if slots is not None:
            slot_utc = next(slots)
            send_at_str = slot_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            payload["sendAt"] = send_at_str

        try:
            resp = requests.post(
                f"{BASE_URL}/accounts/{account_id}/posts",
                headers=_headers(),
                json=payload,
                timeout=15,
            )
            if resp.status_code in (200, 201):
                post_id = resp.json().get("data", {}).get("post", {}).get("id", "?")
                mode = "scheduled" if send_at_str else "draft"
                msg = (
                    f"Scheduled for {send_at_str} (post ID: {post_id})"
                    if send_at_str
                    else f"Draft created (post ID: {post_id})"
                )
                results.append({
                    "index": idx, "success": True,
                    "message": msg, "mode": mode,
                    "send_at": send_at_str,
                })
            else:
                results.append({
                    "index": idx, "success": False,
                    "message": f"HTTP {resp.status_code}: {resp.text[:200]}",
                    "mode": "queue",
                })
        except requests.RequestException as e:
            results.append({
                "index": idx, "success": False,
                "message": str(e), "mode": "queue",
            })

    return results


def build_queue_entry(pin: dict) -> dict:
    """Format a single pin as a Tailwind-ready queue entry."""
    image_url = pin.get("image_url", "")
    return {
        "index": pin.get("index"),
        "topic": pin.get("topic"),
        "local_image_path": pin.get("image_path", ""),
        "image_url": image_url,
        "tailwind_title": pin.get("tailwind_title", "") or pin.get("seo_title", ""),
        "tailwind_description": pin.get("tailwind_description", "") or pin.get("seo_description", ""),
        "link": "https://www.switzertemplates.com",
        "board_id": os.getenv("TAILWIND_BOARD_ID", "SET_BOARD_ID_HERE"),
        "status": "uploaded" if image_url else "pending_upload",
    }


def generate_csv(approved_pins: list[dict], output_path: Path) -> Path:
    """
    Export approved pins as a Tailwind-compatible CSV for bulk scheduling.

    Column mapping to Tailwind's Pinterest scheduler:
      Image URL   → the pin image (Cloudinary URL)
      Title       → Pinterest pin title (shown above description)
      Note        → Pinterest description
      Link        → destination URL
      Board       → Pinterest board name (set via TAILWIND_BOARD_NAME in .env)
      Alt Text    → image alt text for accessibility

    To import: open Tailwind → Publisher → Drafts → Bulk Upload → Import CSV
    """
    board = os.getenv("TAILWIND_BOARD_NAME", "")

    fieldnames = ["Image URL", "Title", "Note", "Link", "Board", "Alt Text"]

    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for pin in approved_pins:
            title = pin.get("tailwind_title", "") or pin.get("seo_title", "")
            desc  = pin.get("tailwind_description", "") or pin.get("seo_description", "")
            writer.writerow({
                "Image URL": pin.get("image_url", ""),
                "Title":     title,
                "Note":      desc,
                "Link":      pin.get("link", "https://www.switzertemplates.com"),
                "Board":     board,
                "Alt Text":  title,   # reuse title as alt text — descriptive and keyword-rich
            })

    return output_path
