"""
Interactive lead report server — serves the report on localhost:8765 and
handles status updates so you can mark leads as messaged directly from the browser.

Start with:  python3 skills/lead-gen-agent/main.py --serve
Stop with:   Ctrl+C in the terminal
"""

import json
import subprocess
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

PORT = 8765


class LeadHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # silence access logs

    def do_GET(self):
        from lead_tracker import load_leads
        import report
        leads = load_leads()
        html = report.generate(leads, open_browser=False, server_mode=True)
        body = html.encode("utf-8")
        self._respond(200, "text/html; charset=utf-8", body)

    def do_POST(self):
        if self.path == "/update":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw)
            except Exception:
                self._respond(400, "application/json", b'{"error":"bad json"}')
                return

            lead_id = data.get("lead_id", "")
            status  = data.get("status", "messaged")

            from lead_tracker import update_lead
            updates = {"status": status}
            if status == "messaged":
                updates["outreach_date"] = date.today().isoformat()
            if lead_id:
                update_lead(lead_id, updates)
                print(f"  [tracker] {lead_id} → {status}", file=sys.stderr)

            self._respond(200, "application/json", b'{"ok":true}')
        else:
            self._respond(404, "text/plain", b"not found")

    def do_OPTIONS(self):
        self._respond(200, "text/plain", b"")

    def _respond(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)


def serve():
    url = f"http://127.0.0.1:{PORT}/"
    try:
        server = HTTPServer(("127.0.0.1", PORT), LeadHandler)
    except OSError:
        print(f"\n[serve] Port {PORT} already in use — opening existing session.")
        subprocess.Popen(["open", url])
        return

    print(f"\n[Lead Tracker] Running at {url}")
    print("[Lead Tracker] Mark leads as sent directly in the browser.")
    print("[Lead Tracker] Press Ctrl+C to stop.\n")
    subprocess.Popen(["open", url])

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Lead Tracker] Stopped.")
        server.server_close()
