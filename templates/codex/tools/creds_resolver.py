#!/usr/bin/env python
"""creds-resolver — resolve test creds from project config + env files
into env vars ready to inject into a subprocess.

Used by `falsify.py` runners and any tool that spawns a subprocess
needing test credentials. Replaces the manual "DEV pastes creds into
chat" loop.

Inputs:
  - `.agent-toolkit/test_env.json` (schema v2) — declares `creds_ref`.
  - `creds_ref.creds_files` (default `[.codex/mcp.local.env]`) — search
    these key=value files for the env vars listed in `login_env` /
    `password_env`.
  - Optional: `creds_ref.spawn_test_user_via_mcp = true` — spawn a
    transient user via `mcp_call`; passwords stay in memory only.

Outputs (stdout, JSON):
  {
    "TOOLKIT_TEST_LOGIN": "admin",
    "TOOLKIT_TEST_PASSWORD": "..."
  }

Exit codes:
  0 — at least one creds pair resolved.
  2 — no creds_ref configured / file missing / both env+fallback empty.

NEVER prints passwords on stderr or in process listings. Caller is
responsible for piping output into a child process safely.

Example use from falsify.py before subprocess.run(...):

  creds = json.loads(subprocess.check_output(
      [sys.executable, ".codex/tools/creds_resolver.py"]
  ).decode("utf-8"))
  env.update(creds)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_ENV = REPO_ROOT / ".agent-toolkit" / "test_env.json"


def _load_test_env() -> Optional[Dict[str, Any]]:
    if not TEST_ENV.exists():
        return None
    try:
        return json.loads(TEST_ENV.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None


def _parse_env_file(path: Path) -> Dict[str, str]:
    """Parse simple KEY=VALUE lines (ignores # comments, blank lines)."""
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            elif v.startswith("'") and v.endswith("'"):
                v = v[1:-1]
            out[k.strip()] = v
    except OSError:
        pass
    return out


def _resolve_var(name: str, creds_files: List[Path]) -> Optional[str]:
    """Look up env var name in process env then each creds_file."""
    if not name:
        return None
    val = os.environ.get(name)
    if val:
        return val
    for f in creds_files:
        env = _parse_env_file(f)
        if name in env:
            return env[name]
    return None


def resolve() -> Tuple[Dict[str, str], List[str]]:
    """Return (creds_dict, warnings)."""
    warnings: List[str] = []
    test_env = _load_test_env()
    if not test_env:
        warnings.append("test_env.json missing")
        return {}, warnings

    creds_ref = (test_env or {}).get("creds_ref") or {}
    if not creds_ref:
        warnings.append("test_env.creds_ref missing")
        return {}, warnings

    creds_files_rel = creds_ref.get("creds_files") or [".codex/mcp.local.env"]
    creds_files = [REPO_ROOT / p for p in creds_files_rel]

    out: Dict[str, str] = {}

    login_env = creds_ref.get("login_env")
    password_env = creds_ref.get("password_env")

    login_val = _resolve_var(login_env, creds_files) if login_env else None
    pwd_val = _resolve_var(password_env, creds_files) if password_env else None

    if not login_val and creds_ref.get("fallback_login"):
        login_val = creds_ref["fallback_login"]
        warnings.append("login resolved via fallback_login")
    if not pwd_val and creds_ref.get("fallback_password"):
        pwd_val = creds_ref["fallback_password"]
        warnings.append("password resolved via fallback_password")

    if login_val and login_env:
        out[login_env] = login_val
    if pwd_val and password_env:
        out[password_env] = pwd_val

    if not out:
        warnings.append("no creds resolved — env vars empty and no fallback")
    return out, warnings


def main(argv: List[str]) -> int:
    creds, warnings = resolve()
    # Print warnings to stderr so caller can see resolution path.
    for w in warnings:
        print(f"[creds_resolver] {w}", file=sys.stderr)
    if not creds:
        # Empty object on stdout = caller knows nothing to inject.
        print("{}")
        return 2
    print(json.dumps(creds, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
