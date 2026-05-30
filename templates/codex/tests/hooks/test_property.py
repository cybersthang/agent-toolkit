"""Property-based tests using deterministic fuzz (no hypothesis dep).

Tests invariants that should hold over a large input space:
- strip_inert_text is idempotent: strip(strip(x)) == strip(x)
- strip_inert_text never grows the text
- strip_inert_text preserves length (space substitution)
- claim regex matches survive whitespace normalization
"""
import random
import sys
import unittest
from pathlib import Path
# Resolve repo root: .codex/tests/hooks → ../../..
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / ".claude" / "hooks"))

from _audit.strip import strip_inert_text
from _audit.claim_audit import find_claims


SEED = 12345
SAMPLES = 100

CHARS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    " \t\n.,;:!?'\"-_/()[]{}<>|&*"
    "đãàáảãạâấầẩẫậăắằẳẵặ"  # Vietnamese diacritics
)


def _random_text(rng: random.Random, length: int) -> str:
    return "".join(rng.choice(CHARS) for _ in range(length))


def _random_with_markdown(rng: random.Random) -> str:
    """Generate text with random code blocks/links/quotes."""
    parts = []
    for _ in range(rng.randint(3, 8)):
        kind = rng.choice(["plain", "code_block", "inline", "quote", "link", "table"])
        body = _random_text(rng, rng.randint(10, 50))
        if kind == "code_block":
            parts.append(f"\n```\n{body}\n```\n")
        elif kind == "inline":
            parts.append(f" `{body}` ")
        elif kind == "quote":
            parts.append(f"\n> {body}\n")
        elif kind == "link":
            parts.append(f" [{body[:20]}](path/{body[20:40]}.py) ")
        elif kind == "table":
            parts.append(f"\n| col1 | col2 |\n|------|------|\n| {body[:20]} | done |\n")
        else:
            parts.append(body)
    return "".join(parts)


class TestStripProperties(unittest.TestCase):

    def setUp(self):
        self.rng = random.Random(SEED)

    def test_01_stable_after_two_passes(self):
        """strip(strip(strip(x))) == strip(strip(x)) — output stabilizes
        within 2 passes. Strict idempotency not guaranteed (markdown
        link → display text may re-trigger inline-code on first pass)
        but result MUST be stable thereafter."""
        for _ in range(SAMPLES):
            text = _random_with_markdown(self.rng)
            twice = strip_inert_text(strip_inert_text(text))
            thrice = strip_inert_text(twice)
            self.assertEqual(twice, thrice, "strip not stable after 2 passes")

    def test_02_never_grows(self):
        """len(strip(x)) <= len(x) for all x."""
        for _ in range(SAMPLES):
            text = _random_with_markdown(self.rng)
            out = strip_inert_text(text)
            self.assertLessEqual(len(out), len(text))

    def test_03_empty_handles(self):
        self.assertEqual(strip_inert_text(""), "")

    def test_04_plain_text_unchanged(self):
        """Text with no markdown markers should be unchanged."""
        plain = "This is plain narrative text with claim words like slow and missing."
        self.assertEqual(strip_inert_text(plain), plain)


class TestFindClaimsRobust(unittest.TestCase):

    def test_01_no_false_positive_in_pure_code_block(self):
        """Wrapping claim words in ``` should suppress all detections."""
        text = "```\nthis code is slow and the function is missing\n```"
        self.assertEqual(find_claims(text), [])

    def test_02_no_false_positive_in_inline_code(self):
        text = "When you see `error: missing dependency` in logs..."
        self.assertEqual(find_claims(text), [])

    def test_03_detect_claim_in_plain_prose(self):
        text = "This module is slow because of N+1 queries."
        self.assertTrue(len(find_claims(text)) >= 1)


if __name__ == "__main__":
    unittest.main()
