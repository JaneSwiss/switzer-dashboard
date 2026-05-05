"""
Switzertemplates — Etsy Agent Scheduler

What this does:
1. Every 14 days, sends a Mac desktop notification asking for a fresh Everbee export
2. Watches the data/everbee/ folder for a new CSV file
3. When a new file appears, runs the full report generator automatically
4. Report saves to reports/latest-etsy-report.md (dashboard reads from there)

Setup (one time only):
- Run: python3 scheduler/main.py
- That's it. No credentials, no accounts, nothing else needed.
"""

import sys
import time
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
import json

ROOT = Path(__file__).parent.parent
EVERBEE_DIR = ROOT / "data" / "everbee"
EVERBEE_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = ROOT / "scheduler" / ".state.json"
REPORT_INTERVAL_DAYS = 14
CHECK_INTERVAL_SECONDS = 60


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_report_date": None, "last_notified_date": None, "known_files": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def file_hash(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def notify(title, message):
    """Mac desktop notification — no setup needed, built into every Mac."""
    script = f'display notification "{message}" with title "{title}" sound name "Ping"'
    subprocess.run(["osascript", "-e", script], check=False)
    print(f"  [notification] {title}: {message}", file=sys.stderr)


def run_report(csv_path):
    print(f"\n[{datetime.now():%H:%M}] New file detected: {csv_path.name}", file=sys.stderr)
    sys.path.insert(0, str(ROOT / "skills" / "report-generator"))
    from main import generate_report
    try:
        report, out_path = generate_report(everbee_csv_path=csv_path)
        print(f"  Saved: {out_path}", file=sys.stderr)
        notify("Switzertemplates — Report Ready ✓", "Your Etsy Growth Report is updated. Open the dashboard.")
        return True
    except Exception as e:
        print(f"  [error] {e}", file=sys.stderr)
        notify("Switzertemplates — Report Failed", str(e)[:80])
        return False


def main():
    print(f"Scheduler running. Watching: {EVERBEE_DIR}", file=sys.stderr)
    state = load_state()

    while True:
        now = datetime.now()

        # Time to ask for fresh data?
        should_notify = not state["last_notified_date"] or (
            now - datetime.fromisoformat(state["last_notified_date"])
            >= timedelta(days=REPORT_INTERVAL_DAYS)
        )

        if should_notify:
            notify(
                "Switzertemplates — Etsy Growth Report",
                "Time for your bi-weekly report. Drop a fresh Everbee CSV into data/everbee/"
            )
            state["last_notified_date"] = now.isoformat()
            save_state(state)

        # Watch for new CSV files
        current_files = {str(p): file_hash(p) for p in EVERBEE_DIR.glob("*.csv")}
        new_files = [Path(p) for p in current_files if p not in state["known_files"]]

        if new_files:
            latest = sorted(new_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]
            if run_report(latest):
                state["known_files"] = list(current_files.keys())
                state["last_report_date"] = now.isoformat()
                save_state(state)

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
