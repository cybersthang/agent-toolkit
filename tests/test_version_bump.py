# -*- coding: utf-8 -*-
"""Verify __version__ matches CHANGELOG latest entry (eval c1)."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLKIT_ROOT / "lib"))


class TestVersionBump(unittest.TestCase):

    def test_installer_version_present(self):
        from installer import __version__
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_version_string_matches_changelog(self):
        """The __version__ value should appear as a [X.Y.Z] section in
        CHANGELOG.md — keeps package metadata + release notes in sync."""
        from installer import __version__
        changelog = (TOOLKIT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        section_pattern = re.compile(
            r"^\#{1,3}\s*\[?" + re.escape(__version__) + r"\]?",
            re.MULTILINE,
        )
        self.assertTrue(
            section_pattern.search(changelog),
            f"__version__={__version__} not found in CHANGELOG.md sections. "
            f"Latest sections: " + ", ".join(
                re.findall(r"^\#{1,3}\s*\[?(\d+\.\d+\.\d+)\]?", changelog,
                           re.MULTILINE)[:5]
            )
        )


if __name__ == "__main__":
    unittest.main()
