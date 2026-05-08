"""Unified test runner: forces the project venv Python, then runs unit tests,
live MCP smoke, and the AGENT structure check. Exits non-zero on any failure.

Usage (from workspace root, any shell):
    C:\\Users\\thang.vo\\Desktop\\NAKIVO\\venv\\Scripts\\python.exe .codex/tests/run_all_tests.py

If you invoke this with the wrong interpreter, it re-execs itself with the venv binary.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = ROOT.parent / "venv" / "Scripts" / "python.exe"


def ensure_venv_python() -> None:
    """Re-exec the script under the project venv Python if it isn't already."""
    if not VENV_PYTHON.exists():
        print(f"FAIL: project venv Python not found at {VENV_PYTHON}", file=sys.stderr)
        sys.exit(2)
    current = Path(sys.executable).resolve()
    if current != VENV_PYTHON.resolve():
        print(f"Re-executing under venv Python: {VENV_PYTHON}")
        result = subprocess.run([str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])
        sys.exit(result.returncode)


def run_unit_tests() -> int:
    print("\n=== [1/3] Unit tests (unittest) ===")
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(Path(__file__).parent), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def run_live_smoke() -> int:
    print("\n=== [2/3] Live JSON-RPC smoke (5 MCP servers) ===")
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "smoke_mcp_servers.py")],
        cwd=str(ROOT),
    )
    return proc.returncode


def run_structure_check() -> int:
    print("\n=== [3/3] AGENT structure check ===")
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "verify_agent_structure.py")],
        cwd=str(ROOT),
    )
    return proc.returncode


def run_determinism_harness() -> int:
    print("\n=== [4/4] Determinism harness (Q1 = Q2) ===")
    script = (Path(__file__).parent / "_determinism_inline.py")
    script.write_text(
        "import json, hashlib, subprocess, sys\n"
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[2]\n"
        "def call(topic):\n"
        "    payload = (\n"
        "        json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05'}}) + '\\n' +\n"
        "        json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'lookup_canonical_decision','arguments':{'topic':topic}}}) + '\\n'\n"
        "    ).encode('utf-8')\n"
        "    proc = subprocess.run([sys.executable, str(ROOT / '.codex' / 'start_codebase_mcp.py')], input=payload, capture_output=True, timeout=30)\n"
        "    for line in proc.stdout.decode('utf-8').splitlines():\n"
        "        if not line.startswith('{'): continue\n"
        "        msg = json.loads(line)\n"
        "        if msg.get('id') == 2:\n"
        "            return msg['result']['content'][0]['text']\n"
        "    return None\n"
        "topics = ['stack', 'python binary', 'api decorators', 'jira production', 'determinism']\n"
        "all_ok = True\n"
        "for topic in topics:\n"
        "    a = call(topic); b = call(topic)\n"
        "    ok = a == b and a is not None\n"
        "    all_ok = all_ok and ok\n"
        "    h = hashlib.sha256((a or '').encode()).hexdigest()[:16]\n"
        "    print(f\"  [{'PASS' if ok else 'FAIL'}] topic={topic!r:25}  hash={h}\")\n"
        "print('Determinism overall:', 'PASS' if all_ok else 'FAIL')\n"
        "sys.exit(0 if all_ok else 1)\n",
        encoding="utf-8",
    )
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd=str(ROOT))
        return proc.returncode
    finally:
        try:
            script.unlink()
        except OSError:
            pass


def main() -> int:
    ensure_venv_python()
    print(f"Workspace: {ROOT}")
    print(f"Python:    {sys.executable}")
    print(f"Version:   {sys.version.split()[0]}")
    failures = 0
    for stage_fn in (run_unit_tests, run_live_smoke, run_structure_check, run_determinism_harness):
        rc = stage_fn()
        if rc != 0:
            failures += 1
    print("\n=== Overall ===")
    print("PASS" if failures == 0 else f"FAIL ({failures} stage(s) failed)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
