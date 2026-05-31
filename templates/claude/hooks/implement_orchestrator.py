#!/usr/bin/env python
"""Stop hook — master orchestrator for Phase 5.1-5.4 audit chain.

Closes Gap 1 from v0.7.2 self-review: the chain previously relied on
AGENT voluntarily invoking each tool per SKILL.md instructions.
This hook fires at Stop time and auto-chains the 4 validators:

  Phase 5.1 — implement_noted_validator   (hallucinated SD check)
  Phase 5.2 — missing_sd_detector         (omitted SD check)
  Phase 5.3 — diff_hunk_annotator         (auto-tag + emit template)
              + diff_annotation_validator (untagged hunk check)
  Phase 5.4 — verify_lint_scope (delegated — runs after this hook)

Trigger conditions (all required):
  - Branch ≠ trunk (main/master/trunk/develop)
  - Spec exists at .agent-toolkit/specs/**/<slug>.md
  - Spec has affected_modules frontmatter
  - implement-noted file exists next to spec
  - Assistant text contains done-claim OR Verify Report marker

Output:
  - Single aggregated additionalContext message listing each phase's
    verdict + remediation hints.
  - Cached in .agent-toolkit/.orchestrator_state.json (60s TTL) so
    re-Stop within same response doesn't re-run.

Bypass markers:
  - `orchestrator-skip: <reason>` — skip entire chain single-shot.

Universal kill-switch: `AGENT_TOOLKIT_DISABLE=1`.

Failure modes: a chained-tool error is caught → advisory "skipped" line (exit 0),
never a block. An uncaught exception in the hook logic itself fails CLOSED via
`run_main_safe` (exit 1) since v0.20.0 — set `AGENT_TOOLKIT_NO_STRICT=1` to restore
the old exit-0-silent behavior.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, read_jsonl_transcript, split_current_turn,
    run_main_safe, emit_fire_event, get_enforce_mode,
)

wrap_utf8_stdio()


CACHE_REL = ".agent-toolkit/.orchestrator_state.json"
CACHE_TTL_SECONDS = 60

VALIDATOR_REL = ".codex/tools/implement_noted_validator.py"
DETECTOR_REL = ".codex/tools/missing_sd_detector.py"
ANNOTATOR_REL = ".codex/tools/diff_hunk_annotator.py"
ANN_VALIDATOR_REL = ".codex/tools/diff_annotation_validator.py"

TRUNK_BRANCHES = {"main", "master", "trunk", "develop"}

DONE_CLAIM_RE = re.compile(
    r"\b("
    r"implement\s+done|implement\s+xong"
    r"|implementation\s+(?:done|complete|finished)"
    r"|sprint\s+(?:hoàn\s*tất|done|complete|finished)"
    r"|feature\s+ready\s+for\s+(?:review|/verify)"
    r")\b",
    re.IGNORECASE,
)
VERIFY_REPORT_RE = re.compile(r"(?im)^\s*#+\s*verify\s+report\b")
BYPASS_RE = re.compile(r"orchestrator-skip\s*:\s*(\S+)", re.IGNORECASE)


def _exit_silent() -> None:
    sys.exit(0)


def _emit_context(message: str) -> None:
    # Phase C v0.9.1: fire event capture
    try:
        emit_fire_event("implement_orchestrator.py", verdict="warn")
    except Exception:
        pass
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": message,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def _emit_block(message: str) -> None:
    """T6 (F2.2): blocking variant — used when enforce_mode=block AND a positive
    scope-integrity problem is found. The fire-event verdict now reflects the real
    decision (block), replacing the previously-hardcoded `warn`."""
    try:
        emit_fire_event("implement_orchestrator.py", verdict="block")
    except Exception:
        pass
    print(json.dumps({"decision": "block", "reason": message}, ensure_ascii=False))
    sys.exit(0)


_BLOCKING_DETECTOR_VERDICTS = {"missing-sd", "fabricated-sd", "missing-and-fabricated"}


def _should_block(results: Dict[str, Dict[str, Any]]) -> bool:
    """T6 (F2.2 + R4 de-risk): a POSITIVE missing/fabricated-SD finding worth blocking
    on (under enforce_mode block). The detector verdict is only trustworthy when the
    snapshot captured changes (`modified_count > 0`); an absent/empty snapshot yields
    modified_count==0 where 'fabricated-sd' would be a false positive — so we degrade
    to warn there (never wrongly block on missing snapshot data)."""
    det = results.get("detector") or {}
    if det.get("error") or det.get("verdict") not in _BLOCKING_DETECTOR_VERDICTS:
        return False
    # review round-1 LOW: a subprocess-fallback / third-party detector could emit a
    # non-numeric modified_count — coerce defensively so this never raises (which
    # would fail-closed via run_main_safe instead of degrading to warn).
    try:
        return int(det.get("modified_count") or 0) > 0
    except (TypeError, ValueError):
        return False


def _resolve_branch(workspace: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(workspace), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
        )
        if proc.returncode == 0:
            out = (proc.stdout or "").strip()
            if out and out != "HEAD":
                return out
        proc2 = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=str(workspace), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
        )
        if proc2.returncode == 0:
            return (proc2.stdout or "").strip()
        return ""
    except (subprocess.SubprocessError, OSError):
        return ""


def _branch_to_slug(branch: str) -> str:
    if "/" in branch:
        return branch.rsplit("/", 1)[1]
    return branch


def _spec_for_slug(workspace: Path, slug: str) -> Optional[Path]:
    for base in (".agent-toolkit/specs", "specs"):
        sd = workspace / base
        if not sd.is_dir():
            continue
        for p in sd.rglob(f"{slug}.md"):
            if p.stem == slug:
                return p
    return None


def _spec_has_affected_modules(spec_path: Path) -> bool:
    try:
        text = spec_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    end = text[3:].find("\n---")
    if end < 0:
        return False
    fm = text[3:3 + end]
    return bool(re.search(
        r"^\s*affected_modules\s*:\s*\n((?:\s+- .+\n?)+)",
        fm, re.MULTILINE,
    ))


def _extract_assistant_text(turn: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for msg in turn:
        if (msg.get("role") or msg.get("type")) != "assistant":
            continue
        content = (msg.get("message") or {}).get("content") or msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text":
                    parts.append(b.get("text") or "")
    return "\n".join(parts)


def _import_tool(workspace: Path, rel_path: str):
    """Phase F v0.9.0 — in-process import of tool module.
    Returns module OR None on import failure (caller falls back to subprocess)."""
    tool_path = workspace / rel_path
    if not tool_path.exists():
        return None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            f"_orch_tool_{tool_path.stem}", str(tool_path))
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _call_tool_inproc(workspace: Path, rel_path: str,
                       func_name: str, *args, **kwargs) -> Dict[str, Any]:
    """Phase F v0.9.0 — call tool's library API directly (no subprocess).
    Saves ~2s startup per call. Falls back to error dict if import fails.

    Caller specifies module-level function name + args. Each tool's
    library API signature differs — caller knows the contract."""
    mod = _import_tool(workspace, rel_path)
    if mod is None:
        return {"error": f"tool-import-failed: {rel_path}"}
    fn = getattr(mod, func_name, None)
    if fn is None:
        return {"error": f"function-not-found: {rel_path}::{func_name}"}
    try:
        result = fn(*args, **kwargs)
        if isinstance(result, dict):
            return result
        return {"result": result}
    except Exception as e:  # noqa: BLE001
        return {"error": f"function-call-failed: {e}"}


def _run_tool_json(workspace: Path, rel_path: str,
                    args: List[str], timeout: int = 30) -> Dict[str, Any]:
    """Fallback: subprocess invocation when in-process import not feasible.
    Kept for tools that don't expose library API (e.g. diff_hunk_annotator
    with --write side-effect)."""
    tool_path = workspace / rel_path
    if not tool_path.exists():
        return {"error": f"tool-missing: {rel_path}"}
    try:
        proc = subprocess.run(
            [sys.executable, str(tool_path), *args,
             "--workspace", str(workspace), "--json"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        if (proc.stdout or "").strip():
            return json.loads(proc.stdout)
        return {"error": "empty-output", "stderr_tail": (proc.stderr or "")[-200:]}
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        return {"error": str(e)}


def _load_cache(workspace: Path) -> Dict[str, Any]:
    p = workspace / CACHE_REL
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(workspace: Path, slug: str, verdict: Dict[str, Any],
                impl_noted_path: Optional[Path] = None) -> None:
    p = workspace / CACHE_REL
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        all_cache = _load_cache(workspace)
        entry: Dict[str, Any] = {"ts": int(time.time()), "verdict": verdict}
        if impl_noted_path and impl_noted_path.exists():
            try:
                entry["impl_noted_mtime"] = int(impl_noted_path.stat().st_mtime)
            except OSError:
                pass
        all_cache[slug] = entry
        # v0.21 T05 (M10): atomic write.
        from _common import atomic_write_json as _aw
        _aw(p, all_cache)
    except OSError:
        pass


def _is_cache_fresh(workspace: Path, slug: str,
                    impl_noted_path: Optional[Path] = None) -> bool:
    """P3 v0.8.0: cache HIT only if ts <60s AND impl-noted mtime unchanged.
    Edit to impl-noted invalidates cache so iter-2 re-runs orchestrator."""
    cache = _load_cache(workspace).get(slug) or {}
    ts = cache.get("ts") or 0
    if (time.time() - ts) >= CACHE_TTL_SECONDS:
        return False
    cached_mtime = cache.get("impl_noted_mtime")
    if impl_noted_path is None or not impl_noted_path.exists():
        return cached_mtime is None
    try:
        current_mtime = int(impl_noted_path.stat().st_mtime)
    except OSError:
        return False
    return cached_mtime == current_mtime


def _aggregate_message(slug: str, results: Dict[str, Dict[str, Any]]) -> str:
    lines = [f"[implement-orchestrator] Phase 5.1-5.4 audit for `{slug}`:"]
    any_issue = False
    for phase, label, result in [
        ("5.1", "implement-noted validator", results.get("validator") or {}),
        ("5.2", "missing-SD detector", results.get("detector") or {}),
        ("5.3", "diff annotation", results.get("annotator") or {}),
    ]:
        if "error" in result:
            lines.append(f"  - Phase {phase} {label}: skipped ({result['error']})")
            continue
        verdict = result.get("verdict") or "?"
        if verdict not in ("clean", "?"):
            any_issue = True
        if phase == "5.1":
            issue_count = len(result.get("issues") or [])
            lines.append(f"  - Phase {phase} {label}: {verdict} "
                         f"({issue_count} issues)")
        elif phase == "5.2":
            missing = len(result.get("missing_files") or [])
            lines.append(f"  - Phase {phase} {label}: {verdict} "
                         f"({missing} missing-SD files)")
        elif phase == "5.3":
            tagged = result.get("tagged") or 0
            total = result.get("total_hunks") or 0
            lines.append(f"  - Phase {phase} {label}: {tagged}/{total} hunks tagged")

    if any_issue:
        lines.append("")
        lines.append("Resolve via: update implement-noted entries,")
        lines.append("add `scope-creep-allowed: <file> <reason>` bypass,")
        lines.append("or `orchestrator-skip: <reason>` single-shot bypass.")
    else:
        lines.append("")
        lines.append("All phases clean → proceed to /verify.")
    return "\n".join(lines)


def main() -> int:
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        _exit_silent()

    raw = sys.stdin.read()
    if not raw.strip():
        _exit_silent()

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _exit_silent()

    if envelope.get("stop_hook_active"):
        _exit_silent()

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    transcript_path = envelope.get("transcript_path")
    if not transcript_path:
        _exit_silent()
    tpath = Path(transcript_path)
    if not tpath.exists():
        _exit_silent()

    messages = read_jsonl_transcript(tpath)
    if not messages:
        _exit_silent()
    turn = split_current_turn(messages)
    asst_text = _extract_assistant_text(turn)
    if not asst_text:
        _exit_silent()

    if BYPASS_RE.search(asst_text):
        _exit_silent()

    if not (DONE_CLAIM_RE.search(asst_text) or VERIFY_REPORT_RE.search(asst_text)):
        _exit_silent()

    branch = _resolve_branch(workspace)
    if not branch or branch in TRUNK_BRANCHES:
        _exit_silent()
    slug = _branch_to_slug(branch)

    spec_path = _spec_for_slug(workspace, slug)
    if not spec_path:
        _exit_silent()
    if not _spec_has_affected_modules(spec_path):
        _exit_silent()

    impl_noted = spec_path.parent / f"{slug}.implement-noted.md"
    if not impl_noted.exists():
        _exit_silent()  # implement_notes_gate already warns separately

    # P3 v0.8.0: cache invalidated by impl-noted mtime.
    # T6 (review round-1 HIGH): under block mode do NOT honor the cache short-circuit
    # — the SD-mismatch depends on the source-file snapshot diff, which can change
    # WITHOUT the impl-noted mtime, so a stale CLEAN cache (from a prior clean Stop)
    # must not suppress a now-block-worthy state. Warn mode keeps the cache (avoids
    # re-spamming the advisory).
    block_mode = get_enforce_mode(
        workspace, "implement_orchestrator", default="warn") == "block"
    if not block_mode and _is_cache_fresh(workspace, slug, impl_noted_path=impl_noted):
        _exit_silent()

    # Phase 5.1 — validator (Phase F v0.9.0: in-process import)
    validator_result = _call_tool_inproc(
        workspace, VALIDATOR_REL, "validate",
        impl_noted, workspace,
    )
    # Fall back to subprocess if in-process failed
    if "error" in validator_result and "tool-import-failed" in validator_result.get("error", ""):
        validator_result = _run_tool_json(
            workspace, VALIDATOR_REL, [str(impl_noted)], timeout=15)

    # Phase 5.2 — detector (Phase F v0.9.0: in-process import)
    detector_result = _call_tool_inproc(
        workspace, DETECTOR_REL, "detect",
        slug, workspace,
    )
    if "error" in detector_result and "tool-import-failed" in detector_result.get("error", ""):
        detector_result = _run_tool_json(
            workspace, DETECTOR_REL, [slug], timeout=15)

    # Phase 5.3 — annotator (write template) + annotation validator
    annotator_result: Dict[str, Any] = {}
    try:
        ann_tool = workspace / ANNOTATOR_REL
        if ann_tool.exists():
            proc = subprocess.run(
                [sys.executable, str(ann_tool), slug,
                 "--workspace", str(workspace), "--write"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=15,
            )
            annotator_result = {"verdict": "emitted" if proc.returncode == 0 else "error"}
        else:
            annotator_result = {"error": "annotator-missing"}
    except (subprocess.SubprocessError, OSError) as e:
        annotator_result = {"error": str(e)}

    # Optionally validate annotation completeness (if file exists)
    ann_file = spec_path.parent / f"{slug}.diff-annotations.md"
    if ann_file.exists():
        ann_v = _run_tool_json(workspace, ANN_VALIDATOR_REL, [str(ann_file)], timeout=10)
        if "verdict" in ann_v:
            annotator_result.update({
                "annotation_verdict": ann_v.get("verdict"),
                "tagged": ann_v.get("tagged"),
                "total_hunks": ann_v.get("total_hunks"),
            })

    results = {
        "validator": validator_result,
        "detector": detector_result,
        "annotator": annotator_result,
    }

    msg = _aggregate_message(slug, results)
    # T6 (F2.2): block on a positive, snapshot-backed scope-integrity problem under
    # block mode (computed above). Default warn → advisory additionalContext, the
    # pre-v0.34 behavior is unchanged for warn-mode default installs.
    blocking = block_mode and _should_block(results)
    # A blocking verdict is never cached, and under block mode the cache read above is
    # skipped entirely — so the chain re-evaluates every Stop until the DEV fixes the
    # impl-noted. The warn/clean path caches to avoid re-spamming the same context.
    if not blocking:
        _save_cache(workspace, slug, results, impl_noted_path=impl_noted)
    else:
        _emit_block(msg)
    _emit_context(msg)
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
