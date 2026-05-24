# -*- coding: utf-8 -*-
"""Unit tests for debug_sentry.py v0.6.1 STRONG/WEAK pattern split.

Covers the false-positive scenario that caused the duplicate
clarification-gate response: reading a Python source file containing
`raise ValueError(...)` should NOT trigger the sentry, but a real
runtime traceback with the same exception name SHOULD.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "debug_sentry.py"


def _load_hook():
    """Load debug_sentry as module — but first stub out _common.
    wrap_utf8_stdio so the module-level call doesn't reach into
    pytest's captured stdin/stdout (which raises ValueError: I/O
    on closed file)."""
    hooks_dir = HOOK_PATH.parent
    if str(hooks_dir) not in sys.path:
        sys.path.insert(0, str(hooks_dir))

    # Pre-load + monkey-patch _common before debug_sentry imports it.
    import types
    common_spec = importlib.util.spec_from_file_location(
        "_common", str(hooks_dir / "_common.py"))
    common_mod = importlib.util.module_from_spec(common_spec)
    sys.modules["_common"] = common_mod
    common_spec.loader.exec_module(common_mod)
    common_mod.wrap_utf8_stdio = lambda: None   # no-op for test

    # Reload debug_sentry under the stubbed _common.
    sys.modules.pop("debug_sentry_under_test", None)
    spec = importlib.util.spec_from_file_location(
        "debug_sentry_under_test", str(HOOK_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["debug_sentry_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestStrongPatterns(unittest.TestCase):

    def setUp(self):
        self.mod = _load_hook()

    def test_traceback_header_matches(self):
        text = "Traceback (most recent call last):\n  File \"x.py\""
        seen = self.mod._matches(text, self.mod.DEFAULT_PATTERNS)
        self.assertTrue(seen)

    def test_psycopg2_qualified_matches(self):
        text = "boom — psycopg2.errors.UniqueViolation: duplicate key"
        seen = self.mod._matches(text, self.mod.DEFAULT_PATTERNS)
        self.assertTrue(seen)

    def test_odoo_exception_pattern_lives_in_overlay_not_hardcoded(self):
        """v0.13+: framework-specific exception namespaces moved out of
        DEFAULT_PATTERNS into `debug.<framework>.json` overlay config.
        DEFAULT_PATTERNS must stay stack-agnostic (no `odoo.exceptions.`,
        no `django.core.exceptions.`, etc.); the Odoo pattern lives in
        `templates/agent_toolkit/debug.odoo.json` and is loaded by the
        hook from `.agent-toolkit/debug.json` at runtime."""
        import json
        # Hardcoded defaults stay stack-agnostic.
        for pattern in self.mod.DEFAULT_PATTERNS + self.mod.STRONG_PATTERNS:
            self.assertNotIn(
                "odoo.exceptions", pattern,
                f"Found framework-specific Odoo pattern in hook defaults: {pattern!r}",
            )
        # Overlay file ships the Odoo pattern.
        overlay = (
            TOOLKIT_ROOT / "templates" / "agent_toolkit" / "debug.odoo.json"
        )
        self.assertTrue(overlay.exists(), f"missing overlay: {overlay}")
        cfg = json.loads(overlay.read_text(encoding="utf-8"))
        joined = " ".join(cfg.get("patterns", []))
        self.assertIn("odoo", joined.lower(),
                      "debug.odoo.json should ship an Odoo exception pattern")
        # And the hook DOES match the pattern at runtime when loaded.
        text = "raise odoo.exceptions.AccessError('no perm')"
        seen = self.mod._matches(text, cfg["patterns"])
        self.assertTrue(seen, f"Odoo overlay pattern should match: {text!r}")

    def test_python_frame_line_matches(self):
        text = '  File "/app/foo.py", line 42, in handler'
        seen = self.mod._matches(text, self.mod.DEFAULT_PATTERNS)
        self.assertTrue(seen)


class TestWeakPatternsRequireContext(unittest.TestCase):

    def setUp(self):
        self.mod = _load_hook()

    def test_bare_value_error_in_source_code_does_not_match(self):
        # The scenario that caused the original duplicate response:
        # AGENT Read jira_server.py which contains a bare `raise
        # ValueError(...)` declaration. No traceback context nearby.
        text = (
            "    43|    if not env_var:\n"
            "    44|        raise ValueError('MYAPP_API_URL must be set')\n"
            "    45|    return env_var.rstrip('/')\n"
        )
        seen = self.mod._matches(text, self.mod.DEFAULT_PATTERNS)
        self.assertEqual(
            seen, [],
            "ValueError in source-code Read should NOT match without "
            "traceback context. Got: %r" % seen,
        )

    def test_value_error_with_traceback_context_matches(self):
        text = (
            'Traceback (most recent call last):\n'
            '  File "/app/handler.py", line 12, in run\n'
            "    raise ValueError('bad input')\n"
            "ValueError: bad input"
        )
        seen = self.mod._matches(text, self.mod.DEFAULT_PATTERNS)
        self.assertIn(r"\bValueError\b", seen)

    def test_key_error_with_file_line_context_matches(self):
        text = (
            '  File "/srv/api.py", line 99, in lookup\n'
            "KeyError: 'session_id'"
        )
        seen = self.mod._matches(text, self.mod.DEFAULT_PATTERNS)
        self.assertIn(r"\bKeyError\b", seen)

    def test_assertion_error_with_caret_context_matches(self):
        text = (
            "    self.assertEqual(a, b)\n"
            "        ^^^^^^^^^^^^^^^^^^^\n"
            "AssertionError: 1 != 2"
        )
        seen = self.mod._matches(text, self.mod.DEFAULT_PATTERNS)
        # Caret line + AssertionError within window → should match.
        self.assertIn(r"\bAssertionError\b", seen)

    def test_bare_runtime_error_in_doc_does_not_match(self):
        text = (
            "## RuntimeError handling\n"
            "Our service catches RuntimeError and returns a 503.\n"
        )
        seen = self.mod._matches(text, self.mod.DEFAULT_PATTERNS)
        self.assertNotIn(r"\bRuntimeError\b", seen)


class TestLegacyCustomPatternsStillStrong(unittest.TestCase):
    """If a project overrides debug.json with custom patterns, treat
    them as STRONG (DEV opted in explicitly)."""

    def setUp(self):
        self.mod = _load_hook()

    def test_custom_pattern_no_context_required(self):
        text = "Something happened: BUSINESS_RULE_VIOLATION at line"
        custom = [r"\bBUSINESS_RULE_VIOLATION\b"]
        seen = self.mod._matches(text, custom)
        self.assertEqual(seen, [r"\bBUSINESS_RULE_VIOLATION\b"])


if __name__ == "__main__":
    unittest.main()
