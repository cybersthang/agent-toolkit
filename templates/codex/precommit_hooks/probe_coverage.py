#!/usr/bin/env python
"""Pre-commit probe-coverage gate.

For each staged file under a "feature scope" (controllers, models,
workers, cron, services), check `.agent-toolkit/acceptance-probes.json`
to see if any probe's `applies_when.path_globs` matches the file. If
no probe covers a feature-scope file, the commit is BLOCKED with a
suggestion to run `/probe-add`.

Feature scope is configurable via
`.agent-toolkit/coverage_config.json`. Default scope = Odoo addon
controllers, models, jobs, wizards. Empty config = scope everywhere.

Exit:
  0 — clean (all feature-scope files covered by ≥1 probe, OR file is
      out of scope, OR no acceptance-probes.json registered yet).
  1 — at least one feature-scope file has no probe coverage.

Bypass: `git commit --no-verify` (audit logged by git).
"""
from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES_PATH = REPO_ROOT / ".agent-toolkit" / "acceptance-probes.json"
CONFIG_PATH = REPO_ROOT / ".agent-toolkit" / "coverage_config.json"

# Default feature-scope globs. Project-specific overrides via coverage_config.json.
DEFAULT_FEATURE_GLOBS = [
    # Odoo
    "*/addons/**/controllers/**.py",
    "*/addons/**/models/**.py",
    "*/addons/**/wizard/**.py",
    "*/addons/**/wizards/**.py",
    "*/addons/**/jobs/**.py",
    "**/controllers/**.py",
    "**/models/**.py",
    # Generic stacks
    "**/api/**.py",
    "**/services/**.py",
    "**/views.py",
    "**/handlers/**.py",
]
DEFAULT_EXEMPT_GLOBS = [
    "**/__init__.py",
    "**/tests/**.py",
    "**/test_*.py",
    "**/*_test.py",
    "**/migrations/**.py",
    "**/conftest.py",
    "OCA/**",  # third-party Odoo addons — out of scope
    ".codex/**",
    ".claude/**",
    ".agent-toolkit/**",
]


def _load_probes() -> List[dict]:
    if not PROBES_PATH.exists():
        return []
    try:
        data = json.loads(PROBES_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    return [p for p in (data.get("probes") or []) if isinstance(p, dict)]


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def _matches_any(path: str, globs: List[str]) -> bool:
    norm = path.replace("\\", "/")
    for g in globs:
        if fnmatch.fnmatch(norm, g.replace("\\", "/")):
            return True
    return False


def _probe_covers(file_path: str, probes: List[dict]) -> bool:
    for probe in probes:
        aw = probe.get("applies_when") or {}
        globs = aw.get("path_globs") or []
        if _matches_any(file_path, globs):
            return True
    return False


def main(argv: List[str]) -> int:
    files = argv[1:]
    if not files:
        return 0

    config = _load_config()
    feature_globs = config.get("feature_globs") or DEFAULT_FEATURE_GLOBS
    exempt_globs = config.get("exempt_globs") or DEFAULT_EXEMPT_GLOBS

    probes = _load_probes()
    # If no probes registered yet, don't block — toolkit being adopted.
    if not probes:
        return 0

    uncovered: List[str] = []
    for fp in files:
        # In-scope = matches feature glob AND not in exempt list
        if not _matches_any(fp, feature_globs):
            continue
        if _matches_any(fp, exempt_globs):
            continue
        if not _probe_covers(fp, probes):
            uncovered.append(fp)

    if not uncovered:
        return 0

    print("[probe-coverage] feature-scope files WITHOUT registered probe:", file=sys.stderr)
    for fp in uncovered:
        print(f"  - {fp}", file=sys.stderr)
    print(
        "\nRegister a probe before committing:\n"
        "  In Claude Code, run `/probe-add <id-slug>` for each file above.\n"
        "  The probe must declare:\n"
        "    - applies_when.path_globs covering the file\n"
        "    - evidence.required_tools (which MCP call proves the feature works)\n"
        "    - falsification recipe (how dev would empirically disprove the claim)\n\n"
        "Bypass single commit: `git commit --no-verify`\n"
        "Permanently exempt a path: add glob to `.agent-toolkit/coverage_config.json`\n"
        "  under `exempt_globs`.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
