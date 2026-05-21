#!/usr/bin/env python
"""End-to-end harness for gap_fix_cycle.py + python_assertion_mismatch
diagnose strategy.

Sets up a tmp workspace mimicking a consumer project layout, seeds a
probe + auto_probes_state with simulated AssertionError stderr, then
invokes gap_fix_cycle.py with --dry-run to capture the proposal.

Output: prints JSON summary + decision-log delta. Used by
test_gap_fix_cycle_e2e.py + manual trace evidence capture.

Usage:
  python tests/fixtures/run_gap_fix_e2e.py [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent.parent


def _setup_workspace(td: Path, apply_mode: bool) -> Path:
    project = td / "proj"
    project.mkdir()

    (project / ".codex" / "tools").mkdir(parents=True)
    (project / ".codex" / "gap_fix_diagnose").mkdir(parents=True)
    (project / ".agent-toolkit").mkdir(parents=True)
    (project / "tests").mkdir(parents=True)

    shutil.copy2(
        str(TOOLKIT_ROOT / "templates" / "codex" / "tools" / "gap_fix_cycle.py"),
        str(project / ".codex" / "tools" / "gap_fix_cycle.py"),
    )
    shutil.copy2(
        str(TOOLKIT_ROOT / "templates" / "codex" / "tools" / "falsify.py"),
        str(project / ".codex" / "tools" / "falsify.py"),
    )
    for strat in (
        "python_assertion_mismatch.py",
        "regex_pattern_mismatch.py",
        "playwright_selector_zero.py",
    ):
        shutil.copy2(
            str(TOOLKIT_ROOT / "templates" / "codex" / "gap_fix_diagnose" / strat),
            str(project / ".codex" / "gap_fix_diagnose" / strat),
        )

    target_file = project / "tests" / "test_demo_failing.py"
    target_file.write_text(
        "import unittest\n"
        "\n"
        "class DemoStaleLiteral(unittest.TestCase):\n"
        "    def test_x(self):\n"
        "        self.assertEqual('foo', 'bar')\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n",
        encoding="utf-8",
    )

    probes = {
        "schema_version": 2,
        "probes": [
            {
                "id": "demo-stale-literal",
                "description": "Demo probe; test file has stale literal foo that should be bar.",
                "severity": "warn",
                "auto_run": False,
                "applies_when": {
                    "path_globs": ["tests/test_demo_failing.py"],
                },
                "evidence": {"required_tools": ["code-grader"]},
                "falsification": {
                    "type": "log_assertion",
                    "description": "Run target test; expect pass.",
                    "runner": {
                        "measurement_command": (
                            sys.executable + " tests/test_demo_failing.py"
                        ),
                        "required_patterns": ["OK"],
                        "forbidden_patterns": ["FAILED"],
                    },
                },
            }
        ],
    }
    (project / ".agent-toolkit" / "acceptance-probes.json").write_text(
        json.dumps(probes, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    target_abs = str(target_file.resolve()).replace("\\", "/")
    simulated_stderr = (
        "F\n"
        "FAIL: test_x (__main__.DemoStaleLiteral)\n"
        "Traceback (most recent call last):\n"
        '  File "' + target_abs + '", line 5, in test_x\n'
        "    self.assertEqual('foo', 'bar')\n"
        "AssertionError: 'foo' != 'bar'\n"
        "FAILED (failures=1)\n"
    )
    state = {
        "demo-stale-literal": {
            "ts": 0,
            "status": "refuted",
            "returncode": 1,
            "stderr_tail": simulated_stderr,
        }
    }
    (project / ".agent-toolkit" / ".auto_probes_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    (project / ".agent-toolkit" / "decision-log.md").write_text(
        "# Decision Log - demo\n\nAppend-only ADR-style log.\n", encoding="utf-8",
    )

    return project


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Run without --dry-run; actually patches file.")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        project = _setup_workspace(td_path, args.apply)

        cli = project / ".codex" / "tools" / "gap_fix_cycle.py"
        cmd = [sys.executable, str(cli), "--probe", "demo-stale-literal",
               "--max-iter", "1"]
        if not args.apply:
            cmd.append("--dry-run")

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            cwd=str(project), timeout=60, env=env,
        )

        log_dir = project / ".agent-toolkit" / ".gap_fix_log"
        log_files = list(log_dir.glob("*.json")) if log_dir.exists() else []
        summary = {}
        if log_files:
            summary = json.loads(log_files[0].read_text(encoding="utf-8"))

        decision_log_after = (project / ".agent-toolkit" / "decision-log.md").read_text(encoding="utf-8")
        target_text_after = (project / "tests" / "test_demo_failing.py").read_text(encoding="utf-8")

        out = {
            "cli_rc": proc.returncode,
            "cli_stdout": proc.stdout or "",
            "cli_stderr": proc.stderr or "",
            "summary": summary,
            "decision_log_appended": "ADR-gap-fix" in decision_log_after,
            "target_file_patched": ("'bar'" in target_text_after
                                    and target_text_after.count("'foo'") == 0),
            "target_file_full": target_text_after,
            "apply_mode": args.apply,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    sys.exit(main())
