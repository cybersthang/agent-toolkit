"""PASS-claim contract — acceptance probes registry + matching + evidence."""
from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .strip import strip_inert_text


PROBES_REL = ".agent-toolkit/acceptance-probes.json"

DEFAULT_PASS_CLAIM_REGEX = (
    r"\b(passed|tests?\s*pass(ed)?|all\s*pass|verified|"
    r"đã\s*verify|đã\s*test(\s*xong)?|đã\s*chạy\s*xong|hoàn\s*thành|"
    r"implementation\s*done|ready\s*to\s*ship|works\s*correctly|"
    r"hoạt\s*động\s*đúng)\b"
)

DEFAULT_REQUIRED_TOOL_PREFIXES = ("mcp__realdata_test__", "mcp__postgres__")


def discover_required_prefixes(
    workspace: Path,
    exclude_servers: Optional[Tuple[str, ...]] = None,
) -> Tuple[str, ...]:
    """Discover MCP tool prefixes available in `.mcp.json` for this project.

    Used as fallback when `_defaults.required_tool_prefixes` is missing or
    when the configured prefixes don't match any real MCP server. Without
    this, the PASS-claim hook would hard-require `mcp__realdata_test__` /
    `mcp__postgres__` prefixes that may not exist on projects with
    differently-named MCP servers (e.g. `mcp__nakivo-odoo12__`).

    `exclude_servers` parameter:
      - None (default) → no exclusion: ALL declared MCP servers count as
        evidence (incl. `playwright`). Behavior-verification specs (BLOCK /
        ASYNC / DOM observable) rely on Playwright as primary evidence.
      - Tuple of server names → exclude those (project can pass
        `("codebase",)` if e.g. `mcp__codebase__` is read-only discovery,
        not real-data verification).

    Real-world fix 2026-05-18: prior version hardcoded exclude `{playwright}`
    → behavior-verification spec couldn't satisfy PASS-claim because hook
    refused to count `mcp__playwright__browser_navigate` as evidence even
    though the entire spec was about UI behavior observable through DOM.
    Per-probe `evidence.required_tools` whitelist is the right place to
    constrain to data-only MCPs when needed, not a global exclude.

    Returns tuple of `mcp__<server>__` prefixes from `.mcp.json`.
    Falls back to DEFAULT_REQUIRED_TOOL_PREFIXES when `.mcp.json`
    missing/malformed.
    """
    mcp_path = workspace / ".mcp.json"
    if not mcp_path.exists():
        return DEFAULT_REQUIRED_TOOL_PREFIXES
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_REQUIRED_TOOL_PREFIXES
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return DEFAULT_REQUIRED_TOOL_PREFIXES
    excl = set(exclude_servers or ())
    prefixes = tuple(
        f"mcp__{name}__"
        for name in servers
        if isinstance(name, str) and name.strip() and name not in excl
    )
    return prefixes or DEFAULT_REQUIRED_TOOL_PREFIXES

DEFAULT_PASS_EXEMPT_MARKERS = ("[meta-review]", "[meta]")

PROBE_SKIP_RE = re.compile(
    r"probe-skip\s*:\s*([A-Za-z0-9_\-,\s]+?)(?:\s+|$)(.*?)(?:\n|$)",
    re.IGNORECASE,
)


def load_probes_registry(workspace: Path) -> Dict[str, Any]:
    """Load acceptance-probes.json. utf-8-sig tolerates BOM. Fails open."""
    path = workspace / PROBES_REL
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def edited_paths_in_turn(tool_calls: List[Dict[str, Any]]) -> List[str]:
    """Extract file_path from Edit/Write/MultiEdit calls."""
    out: List[str] = []
    for call in tool_calls:
        name = call.get("name") or ""
        if name not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            continue
        inp = call.get("input") or {}
        fp = inp.get("file_path") or inp.get("notebook_path")
        if fp:
            out.append(str(fp).replace("\\", "/"))
    return out


def _glob_matches_any(paths: List[str], globs: List[str]) -> bool:
    if not globs or not paths:
        return False
    for p in paths:
        for g in globs:
            if fnmatch.fnmatch(p, g.replace("\\", "/")):
                return True
    return False


def _task_tags_in_text(text: str) -> List[str]:
    return [m.lower() for m in re.findall(r"\[task:\s*([A-Za-z0-9_\-./]+)\]", text)]


def matching_probes(
    probes: List[Dict[str, Any]],
    text: str,
    edited_paths: List[str],
) -> List[Dict[str, Any]]:
    """Return probes whose applies_when matches this turn."""
    out: List[Dict[str, Any]] = []
    low = text.lower()
    tags = _task_tags_in_text(text)
    for probe in probes:
        if not isinstance(probe, dict):
            continue
        aw = probe.get("applies_when") or {}
        claim_re = aw.get("claim_regex")
        path_globs = aw.get("path_globs") or []
        task_tags = [t.lower() for t in (aw.get("task_tags") or [])]

        matched = False
        if claim_re:
            try:
                if re.search(claim_re, low, re.IGNORECASE | re.UNICODE):
                    matched = True
            except re.error:
                pass
        if not matched and _glob_matches_any(edited_paths, path_globs):
            matched = True
        if not matched and any(t in task_tags for t in tags):
            matched = True
        if matched:
            out.append(probe)
    return out


def probe_evidence_satisfied(
    probe: Dict[str, Any],
    tool_calls: List[Dict[str, Any]],
    results_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bool:
    """Check the turn's tool_calls satisfy this probe's evidence contract.

    If `evidence.required_result_fingerprint` is set, also verify the
    sha256 of at least one matching tool's result content equals the
    expected fingerprint. This catches agents who satisfy `required_tools`
    by making a MCP call with dummy input (e.g. `eval_orm_expression("1+1")`)
    — the fingerprint won't match the expected query's result.
    """
    import hashlib

    ev = probe.get("evidence") or {}
    required = ev.get("required_tools") or []
    min_calls = int(ev.get("min_calls") or 1)
    must_include = ev.get("must_include_call")
    expected_fp = ev.get("required_result_fingerprint")
    include_re: Optional[re.Pattern] = None
    if must_include:
        try:
            include_re = re.compile(must_include, re.IGNORECASE | re.UNICODE)
        except re.error:
            include_re = None

    hits = 0
    fingerprint_satisfied = expected_fp is None
    for call in tool_calls:
        name = call.get("name") or ""
        if name not in required:
            if not any(
                name == r or (r.endswith("*") and name.startswith(r[:-1]))
                for r in required
            ):
                continue
        if include_re is not None:
            inp_text = json.dumps(call.get("input") or {}, ensure_ascii=False)
            if not include_re.search(inp_text):
                continue
        hits += 1
        # If fingerprint required, hash the result content of THIS matching call.
        if expected_fp is not None and results_by_id is not None and not fingerprint_satisfied:
            tid = call.get("id") or ""
            result = results_by_id.get(tid) or {}
            rcontent = result.get("content")
            rtext = ""
            if isinstance(rcontent, str):
                rtext = rcontent
            elif isinstance(rcontent, list):
                for b in rcontent:
                    if isinstance(b, dict) and b.get("type") == "text":
                        rtext += b.get("text") or ""
            if rtext:
                actual_fp = hashlib.sha256(rtext.encode("utf-8")).hexdigest()
                if actual_fp == expected_fp:
                    fingerprint_satisfied = True
    return (hits >= min_calls) and fingerprint_satisfied


def default_pass_evidence_satisfied(tool_calls: List[Dict[str, Any]], prefixes: Tuple[str, ...]) -> bool:
    for call in tool_calls:
        name = call.get("name") or ""
        for p in prefixes:
            if name.startswith(p):
                return True
    return False


def probe_skip_requested(text: str, probe_ids: List[str]) -> Optional[str]:
    """Return matched reason if response contains `probe-skip: <id|all> <reason>`."""
    matches = PROBE_SKIP_RE.findall(text)
    if not matches:
        return None
    for ids_chunk, reason in matches:
        requested = [tok.strip().lower() for tok in re.split(r"[,\s]+", ids_chunk) if tok.strip()]
        if not requested:
            continue
        if "all" in requested:
            return reason.strip() or "<no reason>"
        for pid in probe_ids:
            if pid.lower() in requested:
                return reason.strip() or "<no reason>"
    return None


def pass_claim_present(text: str, pass_re: str) -> bool:
    """Return True if PASS-class regex matches the stripped text."""
    try:
        return bool(re.search(pass_re, strip_inert_text(text), re.IGNORECASE | re.UNICODE))
    except re.error:
        return False


def meta_review_mode(text: str, markers: Tuple[str, ...]) -> bool:
    low = text.lower()
    return any(m.lower() in low for m in markers)
