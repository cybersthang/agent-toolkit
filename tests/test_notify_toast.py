"""notify.py desktop toast must be transient + auto-expiring on Linux.

Regression: the Linux `notify-send` command had no `--expire-time` / transient
hint, so a stall toast stuck forever in the GNOME notification tray ("vẫn
còn" even when nothing was hung). The durable record is the `log` channel
(`.stall_alert.json`); the toast itself must be ephemeral.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent


def _load_notify():
    spec = importlib.util.spec_from_file_location(
        "notify_under_test", TOOLKIT_ROOT / "tools" / "notify.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # stdlib-only; import is side-effect-free
    return mod


@pytest.mark.skipif(sys.platform in ("win32", "darwin"),
                    reason="Linux notify-send branch only")
def test_linux_toast_is_transient_and_auto_expiring():
    notify = _load_notify()
    cmd = notify._toast_command("the title", "the body")
    assert cmd[0] == "notify-send"
    assert any(a.startswith("--expire-time") for a in cmd), cmd
    assert any("transient" in a for a in cmd), cmd
    # title + body still passed through.
    assert "the title" in cmd and "the body" in cmd
