"""The installer must never ship gitignored runtime junk into a project.

Regression: a dogfooded maintainer tree accumulated
`templates/cursor/skills/odoo/.agent-toolkit/.hook_fire_log.json`; the
file-copying installer (build_plan) propagated it to consumer projects.
build_plan's rglob walks now filter via `_is_copy_noise`.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent


def _load_setup():
    spec = importlib.util.spec_from_file_location(
        "setup_under_test", TOOLKIT_ROOT / "setup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # main() is guarded by if __name__ == '__main__'
    return mod


NOISE = [
    ".agent-toolkit/.hook_fire_log.json",
    "odoo/.agent-toolkit/.hook_loc_log.json",
    "__pycache__/x.cpython-310.pyc",
    "foo.pyc",
    ".hook_fire_log.json",
    "CLAUDE.md.bak.20260101-000000",
]
KEEP = [
    "odoo/odoo-code-review/SKILL.md",
    "odoo/odoo-account-move-overhaul/references/odoo-12-account-invoice.md",
    "_common/plan-feature/SKILL.md",
    "evidence_audit.py",
    "mcp_servers/gitlab_server.py",
]


def test_is_copy_noise_filters_runtime_junk():
    setup = _load_setup()
    for p in NOISE:
        assert setup._is_copy_noise(Path(p)) is True, f"should skip: {p}"
    for p in KEEP:
        assert setup._is_copy_noise(Path(p)) is False, f"should keep: {p}"
