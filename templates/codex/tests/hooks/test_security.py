"""Security hardening tests — falsifier sandbox + credential entropy."""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FALSIFY = REPO_ROOT / ".codex" / "tools" / "falsify.py"
CRED_GUARD = REPO_ROOT / ".codex" / "precommit_hooks" / "credential_guard.py"
PY = sys.executable


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestFalsifySandbox(unittest.TestCase):

    def setUp(self):
        self.f = _load(FALSIFY, "falsify_security_under_test")

    def test_01_reject_shell_metachar_pipe(self):
        err = self.f._validate_command("curl https://x.com | rm -rf /")
        self.assertIsNotNone(err)
        self.assertIn("metachar", err)

    def test_02_reject_shell_metachar_semicolon(self):
        err = self.f._validate_command("echo hi; rm -rf /")
        self.assertIsNotNone(err)

    def test_03_reject_shell_metachar_backtick(self):
        err = self.f._validate_command("curl `whoami`.com")
        self.assertIsNotNone(err)

    def test_04_reject_shell_metachar_dollar_paren(self):
        err = self.f._validate_command("curl $(whoami).com")
        self.assertIsNotNone(err)

    def test_05_reject_non_whitelisted_binary(self):
        err = self.f._validate_command("rm -rf /tmp/x")
        self.assertIsNotNone(err)
        self.assertIn("not in whitelist", err)

    def test_06_accept_whitelisted_curl(self):
        err = self.f._validate_command('curl -s -o NUL http://example.com')
        self.assertIsNone(err)

    def test_07_accept_python_with_args(self):
        err = self.f._validate_command("python -c 'print(1)'")
        self.assertIsNone(err)

    def test_08_reject_empty(self):
        self.assertIsNotNone(self.f._validate_command(""))
        self.assertIsNotNone(self.f._validate_command("   "))


class TestCredentialEntropy(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cred_test_"))
        self.cred = _load(CRED_GUARD, "cred_guard_under_test")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, content: str) -> str:
        # Write into a path the credential_guard would scan (relative to repo).
        # For unit testing we'll just measure entropy directly.
        return content

    def test_01_high_entropy_random_string(self):
        # 32-char random base64 string — high entropy.
        s = "aB7xK9pQ2mN8vR4tL6yH3zJ5wD1fG0sE"
        self.assertGreater(self.cred._shannon_entropy(s), 4.0)

    def test_02_low_entropy_english_word(self):
        s = "password" * 5  # repetitive, low entropy
        self.assertLess(self.cred._shannon_entropy(s), 4.0)

    def test_03_medium_entropy_phrase(self):
        # Natural English ~4.0-4.5 bits/char typically
        s = "thisisaplaceholderpasswordpleasereplace"
        # Should be lower than random base64
        self.assertLess(self.cred._shannon_entropy(s), 4.5)


if __name__ == "__main__":
    unittest.main()
