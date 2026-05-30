"""probe_autostub PostToolUse hook tests."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / ".claude" / "hooks" / "probe_autostub.py"
PY = sys.executable


def _make_workspace_with_coverage():
    """Tempdir workspace with coverage_config + empty probes registry."""
    ws = Path(tempfile.mkdtemp(prefix="autostub_test_"))
    (ws / ".agent-toolkit").mkdir(parents=True, exist_ok=True)
    (ws / ".agent-toolkit" / "coverage_config.json").write_text(
        json.dumps({"feature_globs": ["app/controllers/**.py"]}),
        encoding="utf-8",
    )
    (ws / ".agent-toolkit" / "acceptance-probes.json").write_text(
        json.dumps({"version": 1, "probes": [], "_defaults": {}}),
        encoding="utf-8",
    )
    (ws / "app" / "controllers").mkdir(parents=True, exist_ok=True)
    return ws


def _run_hook(ws: Path, envelope: dict) -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [PY, str(HOOK)],
        input=json.dumps(envelope),
        text=True, capture_output=True, encoding="utf-8", env=env,
    )
    return {
        "rc": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
    }


def _read_probes(ws: Path) -> list:
    data = json.loads((ws / ".agent-toolkit" / "acceptance-probes.json").read_text(encoding="utf-8"))
    return data.get("probes") or []


class TestAutostub(unittest.TestCase):

    def setUp(self):
        self.ws = _make_workspace_with_coverage()
        self.controller = self.ws / "app" / "controllers" / "main.py"

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_01_new_feature_no_existing_probe_warns(self):
        """New feature edit + no covering probe → hook emits warning,
        does NOT write any stub probe (new safety-net behavior)."""
        new_content = (
            "from http import http\n\n"
            'class Web:\n'
            '    @http.route("/api/v1/foo", auth="user")\n'
            '    def foo_handler(self, **kw):\n'
            '        return {}\n'
        )
        self.controller.write_text(new_content, encoding="utf-8")
        result = _run_hook(self.ws, {
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.controller), "content": new_content},
            "cwd": str(self.ws),
        })
        self.assertEqual(result["rc"], 0)
        # Probes registry must remain EMPTY — hook no longer stubs.
        self.assertEqual(_read_probes(self.ws), [])
        # Output must contain warning text.
        self.assertIn("WARNING", result["stdout"])
        self.assertIn("PROBE_READINESS", result["stdout"])

    def test_02_out_of_scope_file_silent(self):
        outside = self.ws / "tests" / "x.py"
        outside.parent.mkdir(parents=True, exist_ok=True)
        new_content = '@http.route("/api/v1/foo")\ndef bar(self): pass\n'
        outside.write_text(new_content, encoding="utf-8")
        result = _run_hook(self.ws, {
            "tool_name": "Write",
            "tool_input": {"file_path": str(outside), "content": new_content},
            "cwd": str(self.ws),
        })
        self.assertEqual(result["rc"], 0)
        self.assertEqual(result["stdout"], "")  # silent for out-of-scope
        self.assertEqual(_read_probes(self.ws), [])

    def test_03_path_already_covered_silent(self):
        """Agent already wrote a non-stub probe → hook stays silent."""
        # Pre-register a covering probe (simulating agent wrote from grill).
        registry_path = self.ws / ".agent-toolkit" / "acceptance-probes.json"
        registry_path.write_text(json.dumps({
            "version": 1,
            "probes": [{
                "id": "agent-wrote-this",
                "description": "real probe from grill",
                "applies_when": {"path_globs": ["app/controllers/main.py"]},
                "evidence": {"required_tools": ["mcp__realdata_test__run_smoke_test"]},
                "falsification": {"runner": {"measurement_command": "curl http://x"}},
                "severity": "blocker",
            }],
        }), encoding="utf-8")
        new_content = (
            'class Web:\n'
            '    @http.route("/api/v1/foo")\n'
            '    def foo_handler(self): pass\n'
        )
        self.controller.write_text(new_content, encoding="utf-8")
        result = _run_hook(self.ws, {
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.controller), "content": new_content},
            "cwd": str(self.ws),
        })
        self.assertEqual(result["rc"], 0)
        # Hook silent because path covered.
        self.assertEqual(result["stdout"], "")

    def test_04_no_features_silent(self):
        new_content = "import os\n\nx = 1\n"
        self.controller.write_text(new_content, encoding="utf-8")
        result = _run_hook(self.ws, {
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.controller), "content": new_content},
            "cwd": str(self.ws),
        })
        self.assertEqual(result["rc"], 0)
        self.assertEqual(result["stdout"], "")
        self.assertEqual(_read_probes(self.ws), [])

    def test_05_disable_via_env(self):
        new_content = (
            'class Web:\n'
            '    @http.route("/foo")\n'
            '    def foo(self): pass\n'
        )
        self.controller.write_text(new_content, encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["AGENT_TOOLKIT_DISABLE"] = "1"
        proc = subprocess.run(
            [PY, str(HOOK)],
            input=json.dumps({
                "tool_name": "Write",
                "tool_input": {"file_path": str(self.controller), "content": new_content},
                "cwd": str(self.ws),
            }),
            text=True, capture_output=True, encoding="utf-8", env=env,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual((proc.stdout or "").strip(), "")
        self.assertEqual(_read_probes(self.ws), [])

    def test_06_stub_probe_does_not_count_as_coverage(self):
        """A `_stub: true` entry should NOT prevent the warning — old
        stubs from legacy version don't satisfy the new contract."""
        registry_path = self.ws / ".agent-toolkit" / "acceptance-probes.json"
        registry_path.write_text(json.dumps({
            "version": 1,
            "probes": [{
                "id": "old-stub",
                "_stub": True,  # legacy stub
                "description": "TODO",
                "applies_when": {"path_globs": ["app/controllers/main.py"]},
                "severity": "blocker",
            }],
        }), encoding="utf-8")
        new_content = '@http.route("/foo")\ndef foo(self): pass\n'
        self.controller.write_text(new_content, encoding="utf-8")
        result = _run_hook(self.ws, {
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.controller), "content": new_content},
            "cwd": str(self.ws),
        })
        # Stub doesn't count → hook warns.
        self.assertIn("WARNING", result["stdout"])


if __name__ == "__main__":
    unittest.main()
