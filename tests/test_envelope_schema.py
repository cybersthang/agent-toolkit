# -*- coding: utf-8 -*-
"""Tests for R8 — _common envelope protocol version handshake.

Covers validate_envelope_schema: complete envelope, missing fields,
and forward-compat for unknown events.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
COMMON = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "_common.py"


def _load_common():
    """Load _common module fresh (isolated from any installed hooks)."""
    spec = importlib.util.spec_from_file_location("_common_under_test", str(COMMON))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_common_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestEnvelopeSchema(unittest.TestCase):

    def setUp(self):
        self.mod = _load_common()

    def test_complete_stop_envelope_is_valid(self):
        envelope = {"transcript_path": "x", "stop_hook_active": False, "cwd": "."}
        self.assertEqual(
            self.mod.validate_envelope_schema(envelope, "Stop"),
            (True, []),
        )

    def test_empty_stop_envelope_reports_all_missing(self):
        ok, missing = self.mod.validate_envelope_schema({}, "Stop")
        self.assertFalse(ok)
        self.assertEqual(
            missing, ["transcript_path", "stop_hook_active", "cwd"]
        )
        self.assertEqual(len(missing), 3)

    def test_unknown_event_is_forward_compatible(self):
        self.assertEqual(
            self.mod.validate_envelope_schema({}, "UnknownEvent"),
            (True, []),
        )


if __name__ == "__main__":
    unittest.main()
