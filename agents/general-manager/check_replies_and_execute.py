#!/usr/bin/env python3
"""
Check Replies and Execute — General Manager, Step 2

Runs a few times a day (launchd) — not real-time, there's no reason this needs to be
instant. Checks whether Jane has commented on the pending GitHub issue; if so, interprets
her comment, and — only on a clear decision — writes the approved post(s), pushes Wix
drafts, generates pins, drafts the newsletter, and emails a completion summary.

Most runs are a no-op (nothing pending, or nothing new) — that's expected, not a failure.

Run:
    python3 agents/general-manager/check_replies_and_execute.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent
ROOT = AGENT_DIR.parents[1]
LOGS_DIR = AGENT_DIR / "logs"
PENDING_FILE = LOGS_DIR / "pending_recommendation.json"
LOCK_FILE = LOGS_DIR / "execution.lock"
DASHBOARD_FILE = ROOT / "dashboard_data.json"
GITHUB_REPO = "JaneSwiss/switzer-dashboard"

sys.path.insert(0, str(AGENT_DIR))
sys.path.insert(0, str(ROOT / "agents" / "blog-seo-agent"))
sys.path.insert(0, str(ROOT / "agents" / "content-repurposer"))

load_dotenv(ROOT / ".env")


def _notify(message: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "General Manager" sound name "Ping"'],
            check=False,
        )
    except Exception:
        pass  # notification is a nice-to-have, never worth crashing the run over


def _load_pending() -> "dict | None":
    if not PENDING_FILE.exists():
        return None
    try:
        return json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _produce_one_post(keyword: str) -> dict:
    """Runs the full pipeline for one approved keyword: write -> Wix draft -> newsletter
    draft -> pins. Every stage fails gracefully — one failure doesn't stop the others,
    and doesn't stop the next keyword in the batch."""
    import blog_seo_agent
    import content_repurposer
    import pin_pipeline

    result = {"keyword": keyword, "errors": []}

    try:
        post_result = blog_seo_agent.run(force_keyword=keyword)
    except Exception as e:
        result["errors"].append(f"blog write failed: {e}")
        return result

    if not post_result:
        result["errors"].append("blog write returned no result (see logs/errors.json)")
        return result

    result.update({
        "title": post_result.get("keyword", keyword),
        "slug": post_result["slug"],
        "push_ok": post_result.get("push_ok", False),
        "image_cost": post_result.get("image_cost", 0.0),
    })

    try:
        import publish_to_wix
        publish_to_wix.publish(result["slug"])
        result["wix_ok"] = True
    except Exception as e:
        result["wix_ok"] = False
        result["errors"].append(f"Wix draft failed: {e}")

    try:
        result["newsletter_ok"] = bool(content_repurposer.repurpose(result["slug"]))
    except Exception as e:
        result["newsletter_ok"] = False
        result["errors"].append(f"newsletter draft failed: {e}")

    try:
        keyword_row_volume = 0  # best-effort; pin_pipeline scores product match regardless
        pin_result = pin_pipeline.generate_pins_for_keyword(keyword, volume=keyword_row_volume, slug=result["slug"])
        result["pin_message"] = pin_result.get("message", "unknown")
        if not pin_result.get("success"):
            result["errors"].append(f"pins: {pin_result.get('message', 'failed')}")
    except Exception as e:
        result["pin_message"] = "failed"
        result["errors"].append(f"pin generation failed: {e}")

    return result


def _update_dashboard(run_summary: "list[dict]") -> None:
    try:
        data = json.loads(DASHBOARD_FILE.read_text(encoding="utf-8")) if DASHBOARD_FILE.exists() else {}
        gm = data.setdefault("general_manager", {})
        gm["status"] = "active"
        gm["last_run"] = date.today().isoformat()
        gm["awaiting_reply"] = False
        gm["candidates"] = []
        gm["failures"] = [
            {"keyword": p["keyword"], "errors": p["errors"]} for p in run_summary if p.get("errors")
        ]
        data["last_updated"] = date.today().isoformat()
        DASHBOARD_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        subprocess.run(["git", "add", "dashboard_data.json"], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-m", "General Manager: run complete"], cwd=ROOT, check=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=ROOT, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, check=True)
    except Exception as e:
        print(f"  Dashboard update failed: {e}")


def main():
    print("=" * 50)
    print("  General Manager — Step 2: check replies and execute")
    print("=" * 50)

    if LOCK_FILE.exists():
        print("  A run is already in progress (lock file present) — skipping this check.")
        return

    pending = _load_pending()
    if pending is None or pending.get("resolved", True):
        print("  Nothing pending. Nothing to do.")
        return

    import github_issues_client
    import interpret_reply
    import report_writer

    try:
        comments = github_issues_client.fetch_new_comments(pending["issue_number"], since=pending["sent_date"])
    except Exception as e:
        print(f"  Could not reach GitHub: {e}")
        _notify("Can't reach GitHub — check GITHUB_TOKEN. The approval loop is stuck until this is fixed.")
        return

    if not comments:
        print("  No reply yet. Trying again next scheduled check.")
        return

    print(f"  Found {len(comments)} comment(s) — interpreting...")
    decision = interpret_reply.interpret_reply(pending["candidates"], comments)

    actionable = decision.get("approved", []) + decision.get("new_requests", [])
    if not actionable:
        print("  Comment didn't resolve to a clear decision — leaving pending, will check again.")
        return

    LOCK_FILE.touch()
    try:
        pending["resolved"] = True
        PENDING_FILE.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"  Producing: {actionable}")
        run_summary = [_produce_one_post(kw) for kw in actionable]

        _update_dashboard(run_summary)

        try:
            github_issues_client.close_issue(
                pending["issue_number"],
                comment="Done — see the completion email for details.",
            )
        except Exception as e:
            print(f"  Could not close issue: {e}")

        subject, body = report_writer.write_completion_email(decision, run_summary)

        try:
            import gmail_client
            gmail_client.send_email(to=gmail_client.GMAIL_ADDRESS, subject=subject, body=body)
        except Exception as e:
            print(f"  Completion email failed to send: {e}")

        _notify("This week's posts are ready — check your email.")
        print("\nDone.")
    finally:
        LOCK_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
