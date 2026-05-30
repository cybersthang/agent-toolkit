"""Shared helpers for hook smoke tests.

Self-contained — no hardcoded user paths. Uses sys.executable for the
interpreter and Path(__file__) walks for the repo root + hook locations.
Workspaces are isolated via tempfile.mkdtemp so tests in parallel don't
collide.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[3]
HOOKS_DIR = ROOT / ".claude" / "hooks"
PY = sys.executable


def make_workspace(probes_registry: Dict[str, Any] | None = None) -> Path:
    """Create an isolated tempdir workspace with optional acceptance-probes.json
    and an empty invariants.json. Returns the workspace path. Caller must
    cleanup_workspace() it."""
    ws = Path(tempfile.mkdtemp(prefix="agtk_hook_"))
    (ws / ".agent-toolkit").mkdir(parents=True, exist_ok=True)
    if probes_registry is not None:
        (ws / ".agent-toolkit" / "acceptance-probes.json").write_text(
            json.dumps(probes_registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (ws / ".agent-toolkit" / "invariants.json").write_text(
        json.dumps({"version": 1, "invariants": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    return ws


def cleanup_workspace(ws: Path) -> None:
    shutil.rmtree(ws, ignore_errors=True)


def write_transcript(ws: Path, messages: List[Dict[str, Any]]) -> Path:
    """Write a JSONL transcript to ws/t.jsonl. Returns the path."""
    path = ws / "t.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for m in messages:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    return path


def run_evidence_audit(transcript_path: Path, ws: Path) -> Dict[str, Any]:
    """Invoke evidence_audit.py with a synthetic envelope, return parsed
    output dict. Empty stdout means 'allow' (sys.exit(0) without payload)."""
    hook = HOOKS_DIR / "evidence_audit.py"
    envelope = {"transcript_path": str(transcript_path), "cwd": str(ws)}
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [PY, str(hook)],
        input=json.dumps(envelope),
        text=True,
        capture_output=True,
        encoding="utf-8",
        env=env,
    )
    out = (proc.stdout or "").strip()
    if not out:
        return {"decision": "allow"}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"decision": "?", "raw": out, "stderr": proc.stderr}


def run_invariant_guard(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke invariant_guard.py with the envelope (must include tool_name,
    tool_input, cwd). Returns parsed hookSpecificOutput dict."""
    hook = HOOKS_DIR / "invariant_guard.py"
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [PY, str(hook)],
        input=json.dumps(envelope),
        text=True,
        capture_output=True,
        encoding="utf-8",
        env=env,
    )
    out = (proc.stdout or "").strip()
    if not out:
        return {}
    try:
        data = json.loads(out)
        return data.get("hookSpecificOutput") or data
    except json.JSONDecodeError:
        return {"raw": out, "stderr": proc.stderr}


# Long padding to push response above the 240-char cutoff.
LONG_PAD = "Bổ sung text để vượt ngưỡng 240 char cho hook turn này. " * 6
