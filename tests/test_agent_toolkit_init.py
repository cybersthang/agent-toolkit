"""Regression: agent_toolkit_init._starter_settings must not raise NameError.

The generated starter settings.json embeds the literal shell variable
`${CLAUDE_PROJECT_DIR}` inside Python f-strings. It MUST be escaped as
`${{CLAUDE_PROJECT_DIR}}` so the f-string emits the literal text; an unescaped
`${CLAUDE_PROJECT_DIR}` is parsed as an f-string replacement field and raises
NameError at call time. `_starter_settings(args.venv)` is called during
`agent_toolkit_init` (writes `.claude/settings.json`, line ~319), so the crash
blocks codex project init.

This also gives the (otherwise CI-uncovered) templates/codex/tools/ module a
smoke test in the canonical `tests/` suite.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
INIT_PY = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "agent_toolkit_init.py"


def _load_init_module():
    spec = importlib.util.spec_from_file_location(
        "agent_toolkit_init_under_test", INIT_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # functions are module-level; main() is guarded
    return mod


def test_starter_settings_does_not_raise_and_keeps_literal_var():
    mod = _load_init_module()
    out = mod._starter_settings("/venv/bin/python")   # must NOT raise NameError
    data = json.loads(out)                            # must be valid JSON
    # The literal shell variable must survive into the generated settings.
    assert "${CLAUDE_PROJECT_DIR}" in out
    # The f-string must not leave a doubled brace in the output.
    assert "${{CLAUDE_PROJECT_DIR}}" not in out
    # Structure intact: the four hook events are wired.
    for event in ("SessionStart", "UserPromptSubmit", "PreToolUse", "Stop"):
        assert data["hooks"][event]
