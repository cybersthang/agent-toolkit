"""probe_coverage pre-commit hook tests."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple
sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / ".codex" / "precommit_hooks" / "probe_coverage.py"
PY = sys.executable


def _run_hook(workspace: Path, files: List[str]) -> Tuple[int, str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    # Hook uses REPO_ROOT computed from its own __file__, so we can't easily
    # redirect it to a temp workspace without copying the hook. Workaround:
    # we'll run the actual hook against the real repo with synthetic file paths.
    # The hook only reads .agent-toolkit/acceptance-probes.json and
    # coverage_config.json from REPO_ROOT, so this still tests the logic.
    proc = subprocess.run(
        [PY, str(HOOK)] + files,
        capture_output=True, text=True, encoding="utf-8", env=env,
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


class TestCoverageGate(unittest.TestCase):

    def test_01_uncovered_feature_file_blocks(self):
        # Use a path under a generic addon root that no real probe in the
        # project registry would have registered (random uuid-ish module
        # name keeps this test green even after a real probe is added).
        rc, _, err = _run_hook(REPO_ROOT,
                              ["addons-root/addons/_unregistered_xyz_/controllers/main.py"])
        # The path matches feature globs but no probe covers it → block.
        # If the project's coverage_config.json `feature_globs` does NOT
        # include the path above, the hook returns 0 (out of scope), and
        # the test would silently pass-by-luck — assert that the feature
        # glob list actually exercises the path.
        config_path = REPO_ROOT / ".agent-toolkit" / "coverage_config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
            feature_globs = cfg.get("feature_globs") or []
            in_scope = any(
                __import__("fnmatch").fnmatch(
                    "addons-root/addons/_unregistered_xyz_/controllers/main.py",
                    g.replace("\\", "/"),
                )
                for g in feature_globs
            )
            if not in_scope:
                self.skipTest("test path not in scope of this project's feature_globs")
        self.assertEqual(rc, 1)
        self.assertIn("WITHOUT registered probe", err)

    def test_02_exempt_path_allows(self):
        # OCA paths are exempt by config.
        rc, _, _ = _run_hook(REPO_ROOT, ["OCA/web/foo/controllers/main.py"])
        self.assertEqual(rc, 0)

    def test_03_out_of_scope_path_allows(self):
        # README.md doesn't match any feature glob.
        rc, _, _ = _run_hook(REPO_ROOT, ["README.md"])
        self.assertEqual(rc, 0)

    def test_04_test_file_exempt(self):
        rc, _, _ = _run_hook(REPO_ROOT, ["addons-root/addons/foo/tests/test_x.py"])
        self.assertEqual(rc, 0)

    def test_05_covered_path_allows(self):
        # Dynamic: pick the first registered probe and synthesize a
        # concrete path that matches its first path_glob. This stays
        # green across projects without hard-coding any module name.
        probes_path = REPO_ROOT / ".agent-toolkit" / "acceptance-probes.json"
        if not probes_path.exists():
            self.skipTest("no acceptance-probes.json")
        data = json.loads(probes_path.read_text(encoding="utf-8-sig"))
        probes = [p for p in (data.get("probes") or [])
                  if isinstance(p, dict) and not p.get("_stub")]
        if not probes:
            self.skipTest("no probes registered (toolkit fresh-install)")
        first_glob = ((probes[0].get("applies_when") or {}).get("path_globs") or [None])[0]
        if not first_glob:
            self.skipTest("first probe lacks path_globs")
        # `**/*.py` needs >=1 intermediate dir to fnmatch; emit `sub/x.py`.
        concrete = (first_glob
                    .replace("**/*.py", "sub/x.py")
                    .replace("**/*", "sub/x.py")
                    .replace("**/", "sub/")
                    .replace("**", "sub")
                    .replace("*", "x"))
        rc, out, err = _run_hook(REPO_ROOT, [concrete])
        self.assertEqual(rc, 0,
                         msg=f"expected covered, hook rc={rc} on path {concrete}\n"
                             f"stdout: {out}\nstderr: {err}")


if __name__ == "__main__":
    unittest.main()
