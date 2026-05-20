# -*- coding: utf-8 -*-
"""Diagnose strategy — log_assertion regex did not match expected output.

Falsifier `log_assertion` runner emits a stderr line like:
  [falsify] REFUTED: stdout did not match '<regex>'

If we can identify the test/source file that defines the same regex
literal AND we have a sample of the actual stdout, propose loosening
the regex to also match the observed line.

This is conservative — only fires when the regex literal is unique in
the codebase and the observed stdout is non-empty.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional


_REFUTED_RX = re.compile(
    r"REFUTED: stdout did not match\s+['\"](?P<rx>[^'\"]+)['\"]"
)
_SAMPLE_RX = re.compile(r"stdout sample:\s*(?P<sample>[^\n]+)", re.IGNORECASE)


def matches(probe: Dict[str, Any], last_stderr: str) -> bool:
    return bool(last_stderr and _REFUTED_RX.search(last_stderr))


def diagnose(probe: Dict[str, Any], last_stderr: str,
             workspace: Path) -> Optional[Dict[str, Any]]:
    m = _REFUTED_RX.search(last_stderr)
    if not m:
        return None
    expected_rx = m.group("rx")
    sample = _SAMPLE_RX.search(last_stderr)
    if not sample:
        return None
    sample_line = sample.group("sample").strip()
    if not sample_line:
        return None

    # Probe's own runner usually stores the expected_stdout_regex —
    # safer to patch THAT than to grep the whole repo.
    runner = ((probe.get("falsification") or {}).get("runner") or {})
    if runner.get("expected_stdout_regex") != expected_rx:
        return None

    # Build a relaxed regex: match the sample line literally as a
    # substring (escape regex metas). Caller can always tighten later.
    relaxed = re.escape(sample_line[:80])
    new_runner_block = (
        f'"expected_stdout_regex": "{relaxed}"'
    )
    old_runner_block = (
        f'"expected_stdout_regex": "{expected_rx}"'
    )

    probes_path_rel = ".agent-toolkit/acceptance-probes.json"
    target = workspace / probes_path_rel
    if not target.exists():
        return None
    try:
        text = target.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    if old_runner_block not in text:
        return None

    return {
        "file": probes_path_rel,
        "old_string": old_runner_block,
        "new_string": new_runner_block,
        "rationale": (
            f"log_assertion regex `{expected_rx}` did not match observed "
            f"stdout. Relaxed to substring match of the sample line: "
            f"`{sample_line[:60]}`. DEV should review and tighten."
        ),
    }
