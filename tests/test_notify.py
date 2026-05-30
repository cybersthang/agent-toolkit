"""Tests for v0.24.0 tools/notify.py (agent-resilience-supervisor).

Covers acceptance_eval us3-notify-pluggable. Each channel is exercised with
the real send mocked (no email/HTTP/toast actually fires); asserts payload
shape + that smtp/webhook read credentials from ENV only.

Run: pytest tests/test_notify.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLKIT_ROOT / "tools"))

import notify  # noqa: E402


ALERT = {"spec": "feat", "reason": "stalled", "idle_seconds": 200,
         "brief": "🔄 RESUME — còn S2, S3"}


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    return tmp_path


class TestChannels:
    def test_each_channel_payload_and_creds_from_env(self, ws, monkeypatch):
        # --- log (always-on) ---
        assert notify.notify_log(ALERT, ws) is True
        alert_file = ws / ".agent-toolkit/.stall_alert.json"
        assert alert_file.exists()
        data = json.loads(alert_file.read_text(encoding="utf-8"))
        assert data["spec"] == "feat" and "ts" in data

        # --- toast (mock subprocess) ---
        calls = {}
        class _FakeProc:
            pass
        def fake_run(cmd, *a, **k):
            calls["cmd"] = cmd
            return _FakeProc()
        monkeypatch.setattr(notify.subprocess, "run", fake_run)
        assert notify.notify_toast(ALERT) is True
        assert calls["cmd"], "toast must build a command"
        assert any("stalled" in str(part).lower() for part in calls["cmd"])

        # --- smtp (mock smtplib.SMTP, creds from env) ---
        for var in ("SMTP_HOST", "SMTP_FROM", "SMTP_TO", "SMTP_USER",
                    "SMTP_PASSWORD", "SMTP_PORT"):
            monkeypatch.delenv(var, raising=False)
        assert notify.notify_smtp(ALERT) is False, "no env → skip (no hardcoded)"

        sent = {}
        class FakeSMTP:
            def __init__(self, host, port, timeout=0):
                sent["host"] = host
                sent["port"] = port
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def starttls(self):
                sent["tls"] = True
            def login(self, u, p):
                sent["login"] = (u, p)
            def sendmail(self, frm, to, body):
                sent["mail"] = (frm, to, body)
        monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM", "bot@example.com")
        monkeypatch.setenv("SMTP_TO", "dev@example.com")
        monkeypatch.setenv("SMTP_USER", "u1")
        monkeypatch.setenv("SMTP_PASSWORD", "secret-from-env")
        assert notify.notify_smtp(ALERT) is True
        assert sent["login"] == ("u1", "secret-from-env"), "creds from env"
        assert sent["mail"][0] == "bot@example.com"

        # --- webhook (mock urlopen, URL from env) ---
        monkeypatch.delenv("WEBHOOK_URL", raising=False)
        assert notify.notify_webhook(ALERT) is False, "no URL → skip"
        posted = {}
        class _FakeResp:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        def fake_urlopen(req, timeout=0):
            posted["data"] = req.data
            return _FakeResp()
        monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setenv("WEBHOOK_URL", "https://hooks.example.com/x")
        assert notify.notify_webhook(ALERT) is True
        body = json.loads(posted["data"].decode("utf-8"))
        assert "text" in body and "RESUME" in body["text"]

    def test_dispatch_always_includes_log(self, ws, monkeypatch):
        monkeypatch.setattr(notify, "notify_toast", lambda a: True)
        res = notify.dispatch(ALERT, {"notify": {"channels": ["toast"]}}, ws)
        assert res.get("log") is True, "log must always run even if not listed"
        assert res.get("toast") is True

    def test_no_secret_literal_in_source(self):
        src = (TOOLKIT_ROOT / "tools" / "notify.py").read_text(encoding="utf-8")
        # Credentials must come from os.environ, not be embedded.
        assert "os.environ.get(\"SMTP_PASSWORD\")" in src
        assert "password=" not in src.replace("password = os.environ", "")
