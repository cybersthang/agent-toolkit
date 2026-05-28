#!/usr/bin/env python
"""Pluggable notification dispatch for the agent-resilience watcher (v0.24.0).

Channels (all stdlib — no external deps):
  - log    : always-on; writes `.agent-toolkit/.stall_alert.json` + appends a
             rolling log line. Audit baseline.
  - toast  : OS desktop notification — Windows PowerShell toast / Linux
             `notify-send` (chosen by `os.name`). macOS uses `osascript`.
  - smtp   : email via smtplib. Credentials read from ENV ONLY (never
             hardcoded; per credentials policy they live in
             `.codex/mcp.local.env`): SMTP_HOST, SMTP_PORT, SMTP_USER,
             SMTP_PASSWORD, SMTP_FROM, SMTP_TO.
  - webhook: HTTP POST JSON to WEBHOOK_URL (Slack/Discord-compatible payload).

`dispatch(alert, config, workspace)` fans out to the channels enabled in
`config['notify']['channels']`. Each channel fails soft (logs nothing fatal)
so one broken channel never blocks the others.
"""
from __future__ import annotations

import json
import os
import smtplib
import subprocess
import sys
import time
import urllib.request
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

STALL_ALERT_REL = ".agent-toolkit/.stall_alert.json"


def _alert_title(alert: Dict[str, Any]) -> str:
    spec = alert.get("spec") or "?"
    reason = alert.get("reason") or "stalled"
    return f"Claude session stalled [{spec}]: {reason}"


def _alert_body(alert: Dict[str, Any]) -> str:
    lines = [
        _alert_title(alert),
        f"last activity: {alert.get('idle_seconds', '?')}s ago",
    ]
    if alert.get("brief"):
        lines.append("")
        lines.append(str(alert["brief"]))
    lines.append("")
    lines.append("→ Vào chat gõ 'tiếp' để agent tiếp tục (đọc scope manifest).")
    return "\n".join(lines)


def notify_log(alert: Dict[str, Any], workspace: Path) -> bool:
    """Always-on channel: persist a structured alert file. Returns success."""
    try:
        path = workspace / STALL_ALERT_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(alert)
        payload["ts"] = int(time.time())
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return True
    except OSError:
        return False


def _toast_command(title: str, body: str) -> List[str]:
    """Build the platform-appropriate desktop-notification command."""
    if os.name == "nt":
        # Windows: use msg.exe (always present) as a simple, dependency-free
        # popup. PowerShell BurntToast would be nicer but is not guaranteed.
        ps = (
            "powershell -NoProfile -Command "
            "\"[void][System.Reflection.Assembly]::LoadWithPartialName("
            "'System.Windows.Forms');"
            "[System.Windows.Forms.MessageBox]::Show("
            f"'{body}','{title}')\""
        )
        return ["cmd", "/c", ps]
    if sys.platform == "darwin":
        script = f'display notification "{body}" with title "{title}"'
        return ["osascript", "-e", script]
    # Linux / others.
    return ["notify-send", title, body]


def notify_toast(alert: Dict[str, Any]) -> bool:
    title = _alert_title(alert)
    body = _alert_body(alert)
    try:
        subprocess.run(_toast_command(title, body),
                       capture_output=True, timeout=10, check=False)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def notify_smtp(alert: Dict[str, Any]) -> bool:
    """Email via SMTP. ALL connection params + credentials come from env
    (credentials policy — `.codex/mcp.local.env`). Missing config → skip."""
    host = os.environ.get("SMTP_HOST")
    sender = os.environ.get("SMTP_FROM")
    rcpt = os.environ.get("SMTP_TO")
    if not (host and sender and rcpt):
        return False
    port = int(os.environ.get("SMTP_PORT") or "587")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    msg = MIMEText(_alert_body(alert), _charset="utf-8")
    msg["Subject"] = _alert_title(alert)
    msg["From"] = sender
    msg["To"] = rcpt
    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            try:
                server.starttls()
            except smtplib.SMTPException:
                pass  # server may not support STARTTLS
            if user and password:
                server.login(user, password)
            server.sendmail(sender, [rcpt], msg.as_string())
        return True
    except (OSError, smtplib.SMTPException):
        return False


def notify_webhook(alert: Dict[str, Any]) -> bool:
    """POST JSON to WEBHOOK_URL (Slack/Discord `text` field). URL from env."""
    url = os.environ.get("WEBHOOK_URL")
    if not url:
        return False
    payload = json.dumps({"text": _alert_body(alert)}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=15)  # noqa: S310 (config'd URL)
        return True
    except OSError:
        return False


_CHANNELS = {
    "log": None,  # handled specially (needs workspace)
    "toast": notify_toast,
    "smtp": notify_smtp,
    "webhook": notify_webhook,
}


def dispatch(alert: Dict[str, Any], config: Dict[str, Any],
             workspace: Path) -> Dict[str, bool]:
    """Fan out an alert to every enabled channel. `log` is always attempted.
    Returns {channel: success}. Never raises (each channel fails soft)."""
    notify_cfg = (config or {}).get("notify") or {}
    channels = notify_cfg.get("channels") or ["log", "toast"]
    if "log" not in channels:
        channels = ["log"] + list(channels)
    results: Dict[str, bool] = {}
    for ch in channels:
        if ch == "log":
            results["log"] = notify_log(alert, workspace)
            continue
        fn = _CHANNELS.get(ch)
        if fn is None:
            continue
        try:
            results[ch] = fn(alert)
        except Exception:  # noqa: BLE001 — channel must never break dispatch
            results[ch] = False
    return results
