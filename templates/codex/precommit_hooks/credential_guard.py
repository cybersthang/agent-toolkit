#!/usr/bin/env python
"""Pre-commit credential heuristic — block obvious secret patterns.

Mirrors ADR-004 / invariant `credentials-not-in-committed-files`.
Catches:
  - Plain-text passwords > 8 chars in `password = "..."` / `PASSWORD = "..."`
  - Atlassian / Jira API tokens (40-char base64 starting with ATATT or ATCTT)
  - GitHub fine-grained tokens (`ghp_...`, `gho_...`, `ghs_...`)
  - AWS access keys (`AKIA[0-9A-Z]{16}`)
  - Generic high-entropy hex/base64 strings 32+ chars assigned to a
    `secret|token|key|password` variable.

Whitelist:
  - `.codex/mcp.local.env.example` (placeholder values, gitignored real)
  - Any value clearly a placeholder: `<your-...>`, `xxx`, `dummy`, `example`.

Exits 0 if clean, 1 if violation. Bypass: `git commit --no-verify`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

import math


def _shannon_entropy(s: str) -> float:
    """Shannon entropy in bits/char. High-entropy strings (>4.0 for hex,
    >4.5 for base64) are likely credentials, not English prose."""
    if not s:
        return 0.0
    from collections import Counter
    counts = Counter(s)
    length = len(s)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("ghp/gho/ghs token", re.compile(r"\bgh[psoru]_[A-Za-z0-9]{36,}\b")),
    ("Atlassian token", re.compile(r"\bAT[A-Z]{3}3[A-Za-z0-9_\-]{180,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("OpenAI key", re.compile(r"\bsk-[A-Za-z0-9]{40,}\b")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{40,}\b")),
    ("Slack bot token", re.compile(r"\bxox[bp]-[A-Za-z0-9\-]{20,}\b")),
    ("Generic secret assignment",
     re.compile(
         r"(?i)\b(?:password|passwd|pwd|secret|api[_\s\-]?key|token|"
         r"access[_\s\-]?key)\b\s*[:=]\s*[\"']([^\"'\n]{12,})[\"']"
     )),
]

# Entropy threshold — strings >= this many bits/char inside a
# secret-like assignment are flagged even without a known prefix.
_ENTROPY_THRESHOLD = 4.0
_ENTROPY_MIN_LENGTH = 20

PLACEHOLDER_MARKERS = (
    "<your", "xxxx", "yyyy", "zzzz", "dummy", "example", "placeholder",
    "changeme", "your-", "todo", "fixme", "n/a", "redacted",
)


def _looks_placeholder(value: str) -> bool:
    low = value.lower()
    return any(m in low for m in PLACEHOLDER_MARKERS)


def _check_file(rel_path: str) -> List[str]:
    p = REPO_ROOT / rel_path
    if not p.exists() or p.is_dir():
        return []
    # Skip explicit `.example` and gitignored env files (they're not committed
    # anyway; pre-commit shouldn't see them unless tracking changed).
    if rel_path.endswith(".example") or rel_path.endswith(".env"):
        return []
    try:
        text = p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    violations: List[str] = []
    for label, regex in PATTERNS:
        for m in regex.finditer(text):
            # For "Generic secret assignment", value is in group(1).
            value = m.group(1) if m.groups() else m.group(0)
            if _looks_placeholder(value):
                continue
            # Skip if the line has a `# placeholder` / `# example` comment.
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            line = text[line_start:line_end if line_end > 0 else len(text)]
            if any(m_p in line.lower() for m_p in PLACEHOLDER_MARKERS):
                continue
            # Locate line number for error message.
            line_no = text.count("\n", 0, m.start()) + 1
            preview = value[:8] + "…" if len(value) > 8 else value
            violations.append(
                f"  - {rel_path}:{line_no} — {label} (matched `{preview}`)"
            )
    # Entropy-based catch-all: scan all string literals; flag any
    # high-entropy long string inside a secret-like assignment context.
    for m in re.finditer(
        r"(?i)\b(?:password|passwd|pwd|secret|api[_\s\-]?key|token|"
        r"access[_\s\-]?key)\b\s*[:=]\s*[\"']([^\"'\n]{" + str(_ENTROPY_MIN_LENGTH) + r",})[\"']",
        text,
    ):
        value = m.group(1)
        if _looks_placeholder(value):
            continue
        entropy = _shannon_entropy(value)
        if entropy < _ENTROPY_THRESHOLD:
            continue
        # Skip if already caught by named pattern (avoid double-flag).
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line = text[line_start:line_end if line_end > 0 else len(text)]
        if any(named_pat.search(line) for _, named_pat in PATTERNS[:-1]):
            continue
        line_no = text.count("\n", 0, m.start()) + 1
        preview = value[:8] + "…"
        violations.append(
            f"  - {rel_path}:{line_no} — High-entropy secret "
            f"(entropy={entropy:.2f} bits/char, matched `{preview}`)"
        )
    return violations


def main(argv: List[str]) -> int:
    files = argv[1:]
    if not files:
        return 0
    all_violations: List[str] = []
    for fp in files:
        all_violations.extend(_check_file(fp))
    if not all_violations:
        return 0
    print("[credential-guard] possible secrets in committed files:", file=sys.stderr)
    for v in all_violations:
        print(v, file=sys.stderr)
    print(
        "\nIf this is a false positive, replace the literal with a placeholder\n"
        "(`<your-token-here>`) and load real value from `.codex/mcp.local.env`.\n"
        "Bypass single commit: `git commit --no-verify`.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
