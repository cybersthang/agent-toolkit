# -*- coding: utf-8 -*-
"""Diagnose strategy — Playwright "selector resolved to 0 elements".

Common pattern when the DOM selector in the probe script doesn't match
the rendered page (template renamed a class, an action didn't fire,
etc.). The proposal here is INFORMATIONAL: this strategy emits a
patch into the probe script's TODO marker rather than a guessed
selector — the diagnose-patch loop should usually escalate to DEV
because guessing selectors is dangerous.

Returns a patch only when the script is the auto-generated one (has
the marker `Auto-generated probe script for`), in which case it adds
a `pass  # NEED SELECTOR REVIEW` comment so subsequent runs surface
the issue rather than silently re-attempting.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional


_SELECTOR_ZERO_RX = re.compile(
    r"selector resolved to 0 elements", re.IGNORECASE
)


def matches(probe: Dict[str, Any], last_stderr: str) -> bool:
    return bool(last_stderr and _SELECTOR_ZERO_RX.search(last_stderr))


def diagnose(probe: Dict[str, Any], last_stderr: str,
             workspace: Path) -> Optional[Dict[str, Any]]:
    runner = ((probe.get("falsification") or {}).get("runner") or {})
    spec_file_rel = runner.get("spec_file")
    if not spec_file_rel:
        return None
    target = workspace / spec_file_rel
    if not target.exists():
        return None
    try:
        text = target.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    marker = "Auto-generated probe script for"
    if marker not in text:
        # Don't modify hand-written scripts — escalate to DEV instead.
        return None
    need_review_line = "# NEED SELECTOR REVIEW: Playwright selector resolved to 0 elements"
    if need_review_line in text:
        return None  # Already noted.

    # Insert annotation right after the marker comment block.
    new_text_marker = "        # NEED SELECTOR REVIEW: Playwright selector resolved to 0 elements"
    return {
        "file": spec_file_rel,
        "old_string": "        _login(page)",
        "new_string": "        _login(page)\n" + new_text_marker,
        "rationale": (
            "Playwright reported `selector resolved to 0 elements`. "
            "Auto-generated script lacks DOM context; added NEED REVIEW "
            "annotation. DEV should adjust selector or page-load wait."
        ),
    }
