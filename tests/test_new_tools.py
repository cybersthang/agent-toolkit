# -*- coding: utf-8 -*-
"""Unit tests for the 5 new tools shipped with this toolkit update:

  - templates/codex/tools/mcp_call.py
  - templates/codex/tools/creds_resolver.py
  - templates/codex/tools/migrate_probes_v2.py
  - templates/codex/tools/gap_status.py
  - templates/codex/tools/recipe_to_probe_script.py
  - templates/codex/tools/gap_fix_cycle.py

Plus C1 patch verification:
  - additional_evidence_patterns recognizer in pass_contract.py

Tests are isolated: each creates its own tmp project layout so we don't
pollute the toolkit repo or rely on a checked-in `.codex/`.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_TOOLS = TOOLKIT_ROOT / "templates" / "codex" / "tools"
TEMPLATES_HOOKS_AUDIT = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "_audit"
PY = sys.executable


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_probes_file(tmpdir: Path, probes: list) -> Path:
    """Create a minimal acceptance-probes.json at tmpdir/.agent-toolkit/."""
    at = tmpdir / ".agent-toolkit"
    at.mkdir(parents=True, exist_ok=True)
    path = at / "acceptance-probes.json"
    path.write_text(json.dumps({"version": 1, "probes": probes},
                               ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


# ============================================================
# migrate_probes_v2 — idempotent + adds defaults
# ============================================================

class TestMigrateProbesV2(unittest.TestCase):

    def setUp(self):
        self.mod = _load_module(
            "migrate_probes_v2_under_test",
            TEMPLATES_TOOLS / "migrate_probes_v2.py",
        )

    def test_migrates_v1_to_v2_adds_fields(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            probes_path = _make_probes_file(tmpdir, [
                {"id": "x", "description": "x desc"},
                {"id": "y", "description": "y desc"},
            ])
            result = self.mod.migrate(probes_path, dry_run=False)
            self.assertEqual(result["status"], "migrated")
            self.assertEqual(result["probes_upgraded"], 2)
            data = json.loads(probes_path.read_text(encoding="utf-8-sig"))
            self.assertEqual(data["schema_version"], 2)
            for p in data["probes"]:
                self.assertIn("auto_run", p)
                self.assertEqual(p["auto_run"], False)
                self.assertEqual(p["recipe_drift_tolerance"], "medium")

    def test_idempotent_on_v2(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            probes_path = _make_probes_file(tmpdir, [
                {"id": "x", "description": "x"},
            ])
            self.mod.migrate(probes_path, dry_run=False)
            result2 = self.mod.migrate(probes_path, dry_run=False)
            self.assertEqual(result2["status"], "already-v2")

    def test_dry_run_does_not_write(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            probes_path = _make_probes_file(tmpdir, [
                {"id": "x", "description": "x"},
            ])
            original = probes_path.read_bytes()
            result = self.mod.migrate(probes_path, dry_run=True)
            self.assertEqual(result["status"], "would-migrate")
            self.assertEqual(probes_path.read_bytes(), original)

    def test_missing_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            missing = tmpdir / ".agent-toolkit" / "acceptance-probes.json"
            result = self.mod.migrate(missing, dry_run=False)
            self.assertEqual(result["status"], "missing")


# ============================================================
# mcp_call — JSON parsing + arg handling (claude-cli + spawn paths
# require external state; test the parser only)
# ============================================================

class TestMcpCallCli(unittest.TestCase):
    """Exercise the CLI argument parsing and error paths without a real
    MCP server (those require external state)."""

    CLI = TEMPLATES_TOOLS / "mcp_call.py"

    def test_bad_json_args_returns_2(self):
        proc = subprocess.run(
            [PY, str(self.CLI), "fakeserver", "faketool",
             "--args", "not-valid-json"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15,
        )
        self.assertEqual(proc.returncode, 2,
                         "stderr=%r stdout=%r" % (proc.stderr, proc.stdout))

    def test_unknown_server_returns_2(self):
        # No .mcp.json in toolkit repo root → server lookup fails.
        proc = subprocess.run(
            [PY, str(self.CLI), "_does_not_exist", "x",
             "--args", "{}"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15,
        )
        # claude CLI may not be present either; spawn path also fails.
        self.assertEqual(proc.returncode, 2)


# ============================================================
# creds_resolver — env-file parsing + fallback chain
# ============================================================

class TestCredsResolver(unittest.TestCase):

    def setUp(self):
        self.mod = _load_module(
            "creds_resolver_under_test",
            TEMPLATES_TOOLS / "creds_resolver.py",
        )

    def test_parse_env_file_basic(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            envf = Path(td) / "test.env"
            envf.write_text(
                "FOO=bar\n"
                "# comment line\n"
                "  \n"
                "QUOTED=\"hello world\"\n"
                "SINGLE='abc'\n"
                "NO_EQUALS_LINE\n",
                encoding="utf-8",
            )
            parsed = self.mod._parse_env_file(envf)
            self.assertEqual(parsed.get("FOO"), "bar")
            self.assertEqual(parsed.get("QUOTED"), "hello world")
            self.assertEqual(parsed.get("SINGLE"), "abc")
            self.assertNotIn("NO_EQUALS_LINE", parsed)

    def test_parse_missing_file_returns_empty(self):
        self.assertEqual(
            self.mod._parse_env_file(Path("/__missing__.env")),
            {},
        )


# ============================================================
# gap_status — render markdown table, classify by state
# ============================================================

class TestGapStatus(unittest.TestCase):

    def setUp(self):
        self.mod = _load_module(
            "gap_status_under_test",
            TEMPLATES_TOOLS / "gap_status.py",
        )

    def test_classify_within_predicate(self):
        probe = {"id": "x", "severity": "warn", "description": "desc"}
        auto_state = {"x": {"status": "proven", "ts": 9999999999.0}}
        row = self.mod._classify(probe, auto_state, None, now=9999999999.0)
        self.assertEqual(row["status"], "within-predicate")

    def test_classify_failing(self):
        probe = {"id": "x", "severity": "blocker", "description": "desc"}
        auto_state = {"x": {"status": "refuted", "ts": 9999999999.0}}
        row = self.mod._classify(probe, auto_state, None, now=9999999999.0)
        self.assertEqual(row["status"], "failing")

    def test_classify_unknown_no_state(self):
        probe = {"id": "x", "severity": "warn", "description": "desc"}
        row = self.mod._classify(probe, {}, None, now=9999999999.0)
        self.assertEqual(row["status"], "unknown")

    def test_render_markdown_has_table_header(self):
        summary = {
            "spec": "s", "spec_path": "p.md", "feature_kind": "k",
            "verify_report": None,
            "total_probes": 1, "within_predicate": 0,
            "failing": 1, "unknown": 0, "stale": 0,
            "blockers_outstanding": ["x"],
            "next_action": "test",
            "rows": [{"id": "x", "severity": "blocker", "predicate": "p",
                      "verdict": "refuted", "source": "auto_run_probes",
                      "age_s": 60, "status": "failing", "auto_run": True}],
        }
        md = self.mod.render_markdown(summary)
        self.assertIn("| Probe | Severity |", md)
        self.assertIn("failing", md)
        self.assertIn("Blockers outstanding", md)


# ============================================================
# recipe_to_probe_script — pattern matching + skeleton fallback
# ============================================================

class TestRecipeToProbeScript(unittest.TestCase):

    def setUp(self):
        self.mod = _load_module(
            "recipe_to_probe_script_under_test",
            TEMPLATES_TOOLS / "recipe_to_probe_script.py",
        )

    def test_match_patterns_returns_in_text_order(self):
        text = "First trigger 3 RPC, then shadow=true, finally blockUI active"
        patterns = [
            {"id": "trigger", "match_regex": r"trigger\s+(?P<count>\d+)\s+RPC",
             "template": "TRIGGER {count}\n", "vars": {"count": "from_match"}},
            {"id": "shadow", "match_regex": r"shadow\s*=\s*true",
             "template": "SHADOW\n", "vars": {}},
            {"id": "block", "match_regex": r"blockUI active",
             "template": "BLOCK\n", "vars": {}},
        ]
        hits = self.mod._match_patterns(text, patterns)
        self.assertEqual(len(hits), 3)
        ids = [p["id"] for p, _ in hits]
        self.assertEqual(ids, ["trigger", "shadow", "block"])

    def test_fill_template_substitutes_named_group(self):
        import re as _re
        m = _re.search(r"trigger\s+(?P<count>\d+)", "trigger 5 RPC")
        out = self.mod._fill_template(
            "loop {count} times",
            {"count": "from_match"},
            m,
        )
        self.assertEqual(out, "loop 5 times")


# ============================================================
# additional_evidence_satisfied (C1 patch on pass_contract.py)
# ============================================================

class TestAdditionalEvidence(unittest.TestCase):

    def setUp(self):
        # pass_contract imports `.strip` relative — set up `_audit` as a
        # real package so relative imports work.
        hooks_dir = TEMPLATES_HOOKS_AUDIT.parent  # templates/claude/hooks
        if str(hooks_dir) not in sys.path:
            sys.path.insert(0, str(hooks_dir))
        # Now `_audit` is a package importable from hooks_dir.
        import importlib
        if "_audit" in sys.modules:
            del sys.modules["_audit"]
        if "_audit.pass_contract" in sys.modules:
            del sys.modules["_audit.pass_contract"]
        self.mod = importlib.import_module("_audit.pass_contract")

    def test_returns_false_when_no_patterns(self):
        probe = {"evidence": {"required_tools": ["manual-browser"]}}
        ok = self.mod.additional_evidence_satisfied(probe, {"t1": {"content": "x"}}, [])
        self.assertFalse(ok)

    def test_matches_when_pattern_hits_tool_result(self):
        probe = {"evidence": {"required_tools": ["manual-browser"]}}
        patterns = [{
            "name": "test",
            "match_tool_results": r"===PROBE_X_BEGIN===.*===PROBE_X_END===",
            "counts_as": "manual-browser",
        }]
        results = {"t1": {"content": "===PROBE_X_BEGIN=== all good ===PROBE_X_END==="}}
        self.assertTrue(
            self.mod.additional_evidence_satisfied(probe, results, patterns)
        )

    def test_skipped_when_counts_as_not_in_required_tools(self):
        probe = {"evidence": {"required_tools": ["real-data-proof"]}}
        patterns = [{
            "name": "test",
            "match_tool_results": "anything",
            "counts_as": "manual-browser",
        }]
        results = {"t1": {"content": "anything"}}
        self.assertFalse(
            self.mod.additional_evidence_satisfied(probe, results, patterns)
        )


if __name__ == "__main__":
    unittest.main()
