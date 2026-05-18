"""Generic claim audit (original layer) — catches diagnostic claims like
'X is slow / missing / root cause is Y' without evidence tool calls."""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .strip import strip_inert_text


CLAIM_PATTERNS = [
    r"\broot\s*cause\b",
    r"\bnguy(ê|e)n\s*nhân\s*(g(ố|o)c|chính)\b",
    r"\bch(ậ|a)m\b|\bslow\b|\bbottleneck\b",
    # Exclude hyphenated/slashed identifiers like `bug-to-test`, `bug_to_test`,
    # `/missing-feature` from triggering. `(?<![\w/_-])` and `(?![\w/_-])` ensure
    # the word is standalone English, not a token component of a command/file
    # name. Real-world false-positive caught 2026-05-18: `/bug-to-test` command
    # name was treated as a bug-claim.
    r"(?<![\w/_-])(thi(ế|e)u|missing)(?![\w/_-])|\bdoesn'?t\s*exist\b",
    r"(?<![\w/_-])(bug|broken)(?![\w/_-])|\bb(ị|i)\s*l(ỗ|o)i\b",
    r"\bkhông\s*ho(ạ|a)t\s*đ(ộ|o)ng\b|\bnot\s*working\b",
    r"(?<![\w/_-])(sai|wrong|incorrect)(?![\w/_-])",
    r"\bthay\s*đ(ổ|o)i\s*này\s*s(ẽ|e)\b|\bthis\s*change\s*will\b",
    r"\bnên\s*(s(ử|u)a|d(ù|u)ng|b(ỏ|o))\b|\bshould\s*(fix|use|remove)\b",
    r"\bsafe\s*to\b|\ban\s*toàn\s*đ(ể|e)\b",
]

DISCLAIMER_MARKERS = (
    "[assumption]",
    "[unverified]",
    "[chưa verify]",
    "[không chắc]",
    "tôi không chắc",
    "i'm not sure",
    "i am not sure",
    "needs verification",
    "cần xác minh",
    "chưa kiểm chứng",
)

EVIDENCE_TOOLS = {"Read", "Grep", "Glob", "NotebookRead", "BashOutput",
                  "WebFetch", "Agent", "Task"}
EVIDENCE_TOOL_PREFIXES = ("mcp__",)
EVIDENCE_BASH_SUBSTRINGS = (
    "grep", "rg ", "find ", "cat ", "head ", "tail ", "ls ", "wc ",
    "git log", "git diff", "git blame", "git show", "psql", "select ", "explain",
)


def has_disclaimer(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in DISCLAIMER_MARKERS)


def find_claims(text: str) -> List[str]:
    """Return distinct matched claim labels. Inert text stripped first."""
    seen: List[str] = []
    low = strip_inert_text(text).lower()
    for pat in CLAIM_PATTERNS:
        if re.search(pat, low, re.UNICODE):
            seen.append(pat)
    return seen


def has_evidence(tool_calls: List[Dict[str, Any]]) -> bool:
    for call in tool_calls:
        name = call.get("name") or ""
        if name in EVIDENCE_TOOLS:
            return True
        if any(name.startswith(prefix) for prefix in EVIDENCE_TOOL_PREFIXES):
            return True
        if name == "Bash":
            cmd = ((call.get("input") or {}).get("command") or "").lower()
            if any(sub in cmd for sub in EVIDENCE_BASH_SUBSTRINGS):
                return True
    return False
