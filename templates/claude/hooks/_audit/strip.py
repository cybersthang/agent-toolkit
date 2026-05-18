"""Context-aware text stripping — removes inert content before claim regex.

Triple-backtick code blocks, inline `code`, blockquotes, markdown link
display text, and table rows are common false-positive sources for
claim regex. Strip them BEFORE running claim/progress/PASS detection.
"""
from __future__ import annotations

import re

_TRIPLE_BACKTICK_RE = re.compile(r"```[\s\S]*?```")
_INLINE_BACKTICK_RE = re.compile(r"`[^`\n]*`")
_BLOCKQUOTE_LINE_RE = re.compile(r"(?m)^\s*>.*$")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_TABLE_ROW_RE = re.compile(r"(?m)^\s*\|.*\|\s*$")


def _md_link_replacement(m: "re.Match") -> str:
    """Replace markdown link with display text + space padding so the
    output has the same length as the input (preserves char offsets +
    enables idempotency)."""
    full = m.group(0)
    display = m.group(1)
    # If display contains chars that could re-trigger another rule
    # (backticks, blockquote, table delimiters), neutralize them so
    # a second strip pass produces identical output.
    safe = display.replace("`", " ").replace("|", " ").replace("\n>", "\n ")
    if len(safe) > len(full):
        safe = safe[:len(full)]
    return safe + " " * (len(full) - len(safe))


def strip_inert_text(text: str) -> str:
    """Return text with code blocks, inline code, blockquotes, markdown
    link display, and table rows removed. Length-preserving (space
    substitution) so character offsets in error messages stay sane AND
    operation is idempotent: strip(strip(x)) == strip(x)."""
    if not text:
        return text
    out = _TRIPLE_BACKTICK_RE.sub(lambda m: " " * len(m.group(0)), text)
    out = _INLINE_BACKTICK_RE.sub(lambda m: " " * len(m.group(0)), out)
    out = _BLOCKQUOTE_LINE_RE.sub(lambda m: " " * len(m.group(0)), out)
    out = _MD_LINK_RE.sub(_md_link_replacement, out)
    out = _TABLE_ROW_RE.sub(lambda m: " " * len(m.group(0)), out)
    return out
