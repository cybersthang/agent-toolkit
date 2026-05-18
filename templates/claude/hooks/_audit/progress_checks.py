"""Hallucinated-progress checks (categories A-E)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .strip import strip_inert_text
from .transcript import latest_todos_state


ALL_PROGRESS_CHECKS = (
    "action_ghost",
    "tool_result_fabrication",
    "phantom_citation",
    "todo_inconsistency",
    "overcount",
)

# A. Past-tense action → must have matching mutating tool_use.
ACTION_GHOST_CLAIM_RE = re.compile(
    r"\b(đã\s*(thêm|sửa|t(ạ|a)o|x(ó|o)a|fix|fixed|vi(ế|e)t|c(à|a)i|"
    r"c(ậ|a)p\s*nh(ậ|a)t|chuy(ể|e)n|đ(ổ|o)i|build|move|rename|extract|refactor|"
    r"đ(ổ|o)i\s*t(ê|e)n|tách|gộp)|"
    r"(added|edited|created|deleted|wrote|implemented|installed|"
    r"updated|moved|renamed|extracted|refactored|patched|inserted|"
    r"replaced)\b)",
    re.IGNORECASE | re.UNICODE,
)
ACTION_GHOST_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"}

# B. Tool-result fabrication: claim success but tool_result has is_error or non-zero exit.
TOOL_SUCCESS_CLAIM_RE = re.compile(
    r"\b(pass(ed|es)?|succe(ss|eded)?|no\s*errors?|exit\s*0|"
    r"ch(ạ|a)y\s*th(à|a)nh\s*c(ô|o)ng|kh(ô|o)ng\s*c(ó|o)\s*l(ỗ|o)i|"
    r"green|build\s*ok|all\s*green|works(\s*fine)?|hoạt\s*đ(ộ|o)ng\s*đ(ú|u)ng)\b",
    re.IGNORECASE | re.UNICODE,
)
TOOL_EXIT_NONZERO_RE = re.compile(r"\bexit\s*code\s*[:\s]*([1-9]\d*)\b", re.IGNORECASE)

# C. Phantom citation.
# Extension alternation MUST be longest-first: regex alternation matches the
# FIRST matching alternative, not the longest, so `js` would shadow `json` /
# `jsx`, `ts` would shadow `tsx`, `c` would shadow `cpp`, `h` would shadow
# `hpp`. Real-world false-positive caught 2026-05-18: `invariants.json` was
# mis-matched as `invariants.js`, causing phantom_citation false-block.
CITATION_RE = re.compile(
    r"(?<![A-Za-z0-9_])([A-Za-z0-9_./\\-]+\.(json|jsx|js|tsx|ts|yaml|yml|"
    r"hpp|cpp|html|scss|toml|ps1|java|sql|css|xml|md|py|sh|go|rs|rb|c|h))"
    r"(?::(\d+)(?:-(\d+))?)?",
    re.IGNORECASE,
)
CITATION_READING_TOOLS = {"Read", "Grep", "Glob", "NotebookRead"}

# D. TodoWrite inconsistency.
COMPLETION_CLAIM_RE = re.compile(
    r"\b(hoàn\s*thành\s*t(ấ|a)t\s*c(ả|a)|all\s*done|"
    r"t(ấ|a)t\s*c(ả|a)\s*xong|xong\s*h(ế|e)t|finished\s*everything|"
    r"đã\s*xong\s*t(ấ|a)t\s*c(ả|a)|complete(d|ly)?\s*all|"
    r"ho(à|a)n\s*t(ấ|a)t\s*to(à|a)n\s*b(ộ|o))\b",
    re.IGNORECASE | re.UNICODE,
)

# E. Overcount.
COUNT_CLAIM_RE = re.compile(
    r"\b(?:đã\s*(?:sửa|edit|s(ử|u)a|fix|fixed|thay\s*đ(ổ|o)i|c(ậ|a)p\s*nh(ậ|a)t|"
    r"update|updated|created|t(ạ|a)o|edited|modified|thêm|added|viết|wrote|"
    r"refactor|refactored|tách|extracted|đ(ổ|o)i|renamed)\s*"
    r"(\d+)\s*(file|files|tệp|t(ậ|a)p\s*tin|method|methods|function|functions|"
    r"h(à|a)m|class|classes|endpoint|endpoints|bug|bugs|l(ỗ|o)i|issue|issues|"
    r"thay\s*đ(ổ|o)i|changes?|test|tests)|"
    r"(?:modified|edited|updated|fixed|created|added|wrote|refactored|extracted|"
    r"renamed)\s*(\d+)\s*(files?|tệp|methods?|functions?|h(à|a)m|classes?|"
    r"endpoints?|bugs?|l(ỗ|o)i|issues?|changes?|tests?))\b",
    re.IGNORECASE | re.UNICODE,
)

PROGRESS_SKIP_RE = re.compile(
    r"progress-skip\s*:\s*([A-Za-z0-9_,\s]+?)(?:\s+|$)(.*?)(?:\n|$)",
    re.IGNORECASE,
)


def check_action_ghost(text: str, tool_calls: List[Dict[str, Any]]) -> Optional[str]:
    stripped = strip_inert_text(text)
    m = ACTION_GHOST_CLAIM_RE.search(stripped)
    if not m:
        return None
    for call in tool_calls:
        if (call.get("name") or "") in ACTION_GHOST_TOOLS:
            return None
    snippet = stripped[max(0, m.start() - 30): m.end() + 30].strip()
    return (
        f"action_ghost: Response claim past-tense '{m.group(0)}' nhưng turn này KHÔNG có "
        f"Edit/Write/MultiEdit/Bash tool_use nào. Trích: '…{snippet}…'"
    )


def check_tool_result_fabrication(
    text: str,
    tool_calls: List[Dict[str, Any]],
    results_by_id: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    if not TOOL_SUCCESS_CLAIM_RE.search(strip_inert_text(text)):
        return None
    failing: List[str] = []
    for call in tool_calls:
        tid = call.get("id") or ""
        name = call.get("name") or ""
        if name not in ("Bash", "BashOutput") and not name.startswith("mcp__"):
            continue
        result = results_by_id.get(tid)
        if not result:
            continue
        if result.get("is_error") is True:
            failing.append(f"{name}({tid[:8]}): is_error=true")
            continue
        rcontent = result.get("content")
        rtext = ""
        if isinstance(rcontent, str):
            rtext = rcontent
        elif isinstance(rcontent, list):
            for b in rcontent:
                if isinstance(b, dict) and b.get("type") == "text":
                    rtext += b.get("text") or ""
        em = TOOL_EXIT_NONZERO_RE.search(rtext)
        if em:
            failing.append(f"{name}({tid[:8]}): exit code {em.group(1)}")
    if not failing:
        return None
    return (
        "tool_result_fabrication: Response claim success/pass/no-errors nhưng "
        f"{len(failing)} tool_result trong turn này thực ra báo lỗi: "
        + "; ".join(failing[:5])
    )


def check_phantom_citation(
    text: str,
    tool_calls: List[Dict[str, Any]],
    workspace: Path,
) -> Optional[str]:
    link_urls: List[str] = []
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", text):
        url = m.group(2).split("#", 1)[0].strip()
        if url:
            link_urls.append(url)
    cites = CITATION_RE.findall(text)
    if not cites:
        return None
    seen_paths: set = set()
    for call in tool_calls:
        name = call.get("name") or ""
        if name not in CITATION_READING_TOOLS:
            continue
        inp = call.get("input") or {}
        for k in ("file_path", "path", "notebook_path", "pattern", "glob"):
            v = inp.get(k)
            if isinstance(v, str):
                seen_paths.add(v.replace("\\", "/"))
    for u in link_urls:
        try:
            norm = u.replace("\\", "/").lstrip("./")
            if (workspace / u).exists() or (workspace / norm).exists():
                seen_paths.add(norm)
        except OSError:
            continue

    def _normalize(p: str) -> str:
        return p.replace("\\", "/").lstrip("./")

    def _basename(p: str) -> str:
        return p.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

    def _seen(p: str) -> bool:
        np = _normalize(p)
        if any(np in s.replace("\\", "/") for s in seen_paths):
            return True
        cite_base = _basename(np)
        if cite_base and any(_basename(s) == cite_base for s in seen_paths):
            return True
        try:
            if (workspace / p).exists() or (workspace / np).exists():
                return True
        except OSError:
            pass
        return False

    bad: List[str] = []
    for tup in cites:
        path = tup[0]
        if not path or "/" not in path and "\\" not in path and "." not in path:
            continue
        if len(path) < 4:
            continue
        if not _seen(path):
            bad.append(path)
    if not bad:
        return None
    seen_ids: List[str] = []
    for p in bad:
        if p not in seen_ids:
            seen_ids.append(p)
        if len(seen_ids) >= 5:
            break
    return (
        "phantom_citation: Response cite "
        f"{len(seen_ids)} file/path không Read/Grep trong turn này VÀ không tồn tại "
        f"trong workspace: {', '.join(seen_ids)}"
    )


def check_todo_inconsistency(text: str, all_messages: List[Dict[str, Any]]) -> Optional[str]:
    if not COMPLETION_CLAIM_RE.search(strip_inert_text(text)):
        return None
    todos = latest_todos_state(all_messages)
    if not todos:
        return None
    open_items = [t for t in todos if (t.get("status") or "") in ("pending", "in_progress")]
    if not open_items:
        return None
    names = [t.get("content", "")[:60] for t in open_items[:5]]
    return (
        f"todo_inconsistency: Response claim 'hoàn thành tất cả' nhưng TodoWrite state "
        f"vẫn có {len(open_items)} todo open: " + " | ".join(names)
    )


def check_overcount(text: str, tool_calls: List[Dict[str, Any]]) -> Optional[str]:
    matches = COUNT_CLAIM_RE.findall(strip_inert_text(text))
    if not matches:
        return None
    claimed: List[int] = []
    for tup in matches:
        for g in tup:
            if isinstance(g, str) and g.isdigit():
                try:
                    claimed.append(int(g))
                except ValueError:
                    pass
                break
    if not claimed:
        return None
    actual_paths: set = set()
    for call in tool_calls:
        name = call.get("name") or ""
        if name not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            continue
        inp = call.get("input") or {}
        fp = inp.get("file_path") or inp.get("notebook_path")
        if fp:
            actual_paths.add(str(fp).replace("\\", "/"))
    actual = len(actual_paths)
    bad = [n for n in claimed if n > actual]
    if not bad:
        return None
    return (
        f"overcount: Response claim 'sửa {max(bad)} file' nhưng turn này chỉ có "
        f"{actual} unique file_path trong Edit/Write/MultiEdit tool_uses."
    )


def progress_skip_requested(text: str) -> Optional[Tuple[List[str], str]]:
    matches = PROGRESS_SKIP_RE.findall(text)
    if not matches:
        return None
    for ids_chunk, reason in matches:
        cats = [tok.strip().lower() for tok in re.split(r"[,\s]+", ids_chunk) if tok.strip()]
        if cats:
            return cats, reason.strip() or "<no reason>"
    return None


def run_progress_checks(
    text: str,
    tool_calls: List[Dict[str, Any]],
    results_by_id: Dict[str, Dict[str, Any]],
    all_messages: List[Dict[str, Any]],
    workspace: Path,
    disabled: set,
) -> List[str]:
    violations: List[str] = []
    if "action_ghost" not in disabled:
        v = check_action_ghost(text, tool_calls)
        if v: violations.append(v)
    if "tool_result_fabrication" not in disabled:
        v = check_tool_result_fabrication(text, tool_calls, results_by_id)
        if v: violations.append(v)
    if "phantom_citation" not in disabled:
        v = check_phantom_citation(text, tool_calls, workspace)
        if v: violations.append(v)
    if "todo_inconsistency" not in disabled:
        v = check_todo_inconsistency(text, all_messages)
        if v: violations.append(v)
    if "overcount" not in disabled:
        v = check_overcount(text, tool_calls)
        if v: violations.append(v)
    return violations
