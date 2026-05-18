"""feature_probe_suggest pre-commit hook — pattern detection tests."""
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / ".codex" / "precommit_hooks" / "feature_probe_suggest.py"


def _import_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("feature_probe_suggest_under_test", str(HOOK))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["feature_probe_suggest_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestFeatureSuggestPatterns(unittest.TestCase):

    def setUp(self):
        self.mod = _import_module()

    def _scan(self, diff_text: str) -> list:
        """Run pattern matching on a synthetic diff body."""
        hits = []
        for line in diff_text.splitlines():
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for label, pat, advice in self.mod.PATTERNS:
                if pat.search(line):
                    hits.append(label)
        return hits

    def test_01_http_route_detected(self):
        diff = '+    @http.route("/web/dataset/new_endpoint", auth="user")\n'
        self.assertIn("HTTP route", self._scan(diff))

    def test_02_controller_method_detected(self):
        diff = "+    def new_endpoint_handler(self, **kw):\n"
        self.assertIn("Controller method", self._scan(diff))

    def test_03_api_depends_detected(self):
        diff = "+    @api.depends('partner_id', 'state')\n"
        self.assertIn("api.depends / api.constrains", self._scan(diff))

    def test_04_api_constrains_detected(self):
        diff = "+    @api.constrains('amount_total')\n"
        self.assertIn("api.depends / api.constrains", self._scan(diff))

    def test_05_cron_nextcall_detected(self):
        diff = "+    nextcall = fields.Datetime()\n"
        self.assertIn("Cron method (@api.model + nextcall)", self._scan(diff))

    def test_06_no_match_in_normal_code(self):
        diff = "+    x = 1 + 2\n+    y = foo.bar()\n"
        self.assertEqual(self._scan(diff), [])

    def test_07_removed_lines_not_flagged(self):
        diff = "-    @http.route('/old_endpoint')\n-    def old_method(self):\n"
        self.assertEqual(self._scan(diff), [])


if __name__ == "__main__":
    unittest.main()
