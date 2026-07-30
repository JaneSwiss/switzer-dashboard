"""
Shared Gmail send — used by the General Manager for completion notifications.

Send logic extracted from skills/lead-gen-agent/email_sender.py, which already proves
this pattern in daily production use for cold outreach — email_sender.py itself is
untouched, this just avoids writing a second copy of the same send logic.

Setup required in .env (already present for lead-gen-agent's use):
  GMAIL_ADDRESS=jane@youremail.com
  GMAIL_APP_PASSWORD=abcdefghijklmnop   (16-char App Password, no spaces)
"""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_email(to: str, subject: str, body: str) -> bool:
    """Sends one plain-text email via Gmail SMTP. Returns True on success, raises on
    failure (callers keep their own try/except + log_error() per this codebase's
    convention — this function doesn't swallow errors silently)."""
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD):
        raise RuntimeError("GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set in .env")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, to, msg.as_string())

    return True
