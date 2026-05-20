#!/usr/bin/env python
"""gap_fix_cycle — diagnose-patch-rerun loop for REFUTED probes.

Engine for `gap-fix-cycle` skill. Loops up to max_iter on a single
probe id:

  1. read last falsifier stderr from .agent-toolkit/.auto_probes_state.json
  2. invoke each diagnose strategy under .codex/gap_fix_diagnose/*.py
  3. apply the first proposed Patch via straight file Edit (string
     replace) + append decision-log entry
  4. re-run probe via .codex/tools/falsify.py
  5. exit loop on PROVEN OR max_iter reached

Safety: never touches files outside `probe.applies_when.path_globs`.

Usage:
  python .codex/tools/gap_fix_cycle.py --probe <id>
  python .codex/tools/gap_fix_cycle.py --probe <id> --max-iter 3 --dry-run
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES_PATH = REPO_ROOT / ".agent-toolkit" / "acceptance-probes.json"
STATE_PATH = REPO_ROOT / ".agent-toolkit" / ".auto_probes_state.json"
CONFIG_PATH = REPO_ROOT / ".agent-toolkit" / "gap_fix.json"
DECISION_LOG = REPO_ROOT / ".agent-toolkit" / "decision-log.md"
DIAGNOSE_DIR = REPO_ROOT / ".codex" / "gap_fix_diagnose"
FALSIFY_CLI = REPO_ROOT / ".codex" / "tools" / "falsify.py"
LOG_DIR = REPO_ROOT / ".agent-toolkit" / ".gap_fix_log"


_DEFAULT_CONFIG = {
    "max_iter": 3,
    "timeout_per_iter_s": 300,
    "decision_log_append": True,
    "respect_hard_stops": [
        "prod_db_write", "git_push_force",
        "credentials_write", "git_push_main_branch",
    ],
}


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def _load_probe(probe_id: str) -> Optional[Dict[str, Any]]:
    data = _load_json(PROBES_PATH)
    for p in data.get("probes") or []:
        if isinstance(p, dict) and p.get("id") == probe_id:
            return p
    return None


def _load_strategies() -> List:
    """Discover diagnose strategy modules at .codex/gap_fix_diagnose/*.py."""
    if not DIAGNOSE_DIR.is_dir():
        return []
    mods = []
    for path in sorted(DIAGNOSE_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"_gap_fix_strategy_{path.stem}", str(path))
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "matches") and hasattr(mod, "diagnose"):
                mods.append(mod)
        except Exception as e:
            print(f"[gap-fix] strategy {path.name} load failed: {e}",
                  file=sys.stderr)
    return mods


def _path_globs_for_probe(probe: Dict[str, Any]) -> List[str]:
    aw = probe.get("applies_when") or {}
    return aw.get("path_globs") or []


def _is_in_scope(file_rel: str, globs: List[str]) -> bool:
    rel = file_rel.replace("\\", "/")
    for g in globs:
        if fnmatch.fnmatch(rel, g.replace("\\", "/")):
            return True
    return False


def _apply_patch(workspace: Path, patch: Dict[str, Any]) -> bool:
    """Apply {file, old_string, new_string} via straight text replace."""
    file_rel = patch.get("file")
    old_s = patch.get("old_string", "")
    new_s = patch.get("new_string", "")
    if not file_rel or not old_s:
        return False
    target = workspace / file_rel
    if not target.exists():
        return False
    try:
        text = target.read_text(encoding="utf-8-sig", errors="replace")
        if old_s not in text:
            return False
        new_text = text.replace(old_s, new_s, 1)
        target.write_text(new_text, encoding="utf-8")
        return True
    except OSError:
        return False


def _append_decision_log(probe_id: str, iter_n: int,
                         patch: Dict[str, Any]) -> None:
    if not DECISION_LOG.exists():
        return
    try:
        entry = (
            f"\n## ADR-gap-fix · probe `{probe_id}` · iter {iter_n}\n"
            f"- **Date**: {time.strftime('%Y-%m-%d')}\n"
            f"- **Status**: Proposed (auto)\n"
            f"- **Context**: Probe `{probe_id}` REFUTED; gap-fix-cycle applied patch.\n"
            f"- **Decision**: Modified `{patch.get('file')}` per diagnose "
            f"strategy `{patch.get('_strategy', '?')}`. Rationale: "
            f"{patch.get('rationale', '(none)')[:300]}\n"
            f"- **Enforcement**: re-run `python .codex/tools/falsify.py "
            f"--probe {probe_id}` to verify.\n"
        )
        with open(DECISION_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        pass


def _run_falsify(probe_id: str, timeout_s: int) -> Dict[str, Any]:
    if not FALSIFY_CLI.exists():
        return {"status": "no-falsify"}
    try:
        proc = subprocess.run(
            [sys.executable, str(FALSIFY_CLI), "--probe", probe_id],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    rc = proc.returncode
    return {
        "status": "proven" if rc == 0 else ("refuted" if rc == 1 else "error"),
        "returncode": rc,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
    }


def run_cycle(probe_id: str, max_iter: int = 3,
              dry_run: bool = False) -> Dict[str, Any]:
    probe = _load_probe(probe_id)
    if not probe:
        return {"status": "error", "msg": f"probe '{probe_id}' not found"}

    config = dict(_DEFAULT_CONFIG)
    config.update(_load_json(CONFIG_PATH))
    timeout = int(config.get("timeout_per_iter_s", 300))
    log_decisions = bool(config.get("decision_log_append", True))

    strategies = _load_strategies()
    state = _load_json(STATE_PATH)
    globs = _path_globs_for_probe(probe)

    iterations: List[Dict[str, Any]] = []

    for iter_n in range(1, max_iter + 1):
        last_state = state.get(probe_id) or {}
        last_stderr = last_state.get("stderr_tail") or ""

        # Step 1: diagnose
        proposed: Optional[Dict[str, Any]] = None
        for strat in strategies:
            try:
                if not strat.matches(probe, last_stderr):
                    continue
                proposal = strat.diagnose(probe, last_stderr, REPO_ROOT)
                if proposal:
                    proposed = dict(proposal)
                    proposed["_strategy"] = getattr(strat, "__name__", "?")
                    break
            except Exception as e:
                print(f"[gap-fix] strategy error: {e}", file=sys.stderr)

        if not proposed:
            iterations.append({
                "iter": iter_n, "status": "no-strategy-match",
                "stderr_tail": last_stderr[:200]
            })
            break

        # Step 2: scope check
        file_rel = proposed.get("file") or ""
        if globs and not _is_in_scope(file_rel, globs):
            iterations.append({
                "iter": iter_n, "status": "out-of-scope",
                "file": file_rel, "globs": globs,
            })
            break

        # Step 3: dry-run or apply
        if dry_run:
            iterations.append({
                "iter": iter_n, "status": "would-patch",
                "patch": {k: proposed.get(k) for k in
                          ("file", "old_string", "new_string",
                           "rationale", "_strategy")},
            })
            break

        applied = _apply_patch(REPO_ROOT, proposed)
        if not applied:
            iterations.append({
                "iter": iter_n, "status": "patch-failed",
                "file": file_rel,
            })
            break

        if log_decisions:
            _append_decision_log(probe_id, iter_n, proposed)

        # Step 4: re-run
        result = _run_falsify(probe_id, timeout)
        iterations.append({
            "iter": iter_n, "status": "patched-and-rerun",
            "patch_strategy": proposed.get("_strategy"),
            "patch_file": file_rel,
            "rerun_status": result.get("status"),
            "rerun_rc": result.get("returncode"),
        })

        # Update state
        state[probe_id] = {
            "ts": time.time(),
            "status": result.get("status"),
            "returncode": result.get("returncode"),
            "stderr_tail": (result.get("stderr") or "")[-400:],
        }
        _save_json(STATE_PATH, state)

        if result.get("status") == "proven":
            break

    final_status = iterations[-1] if iterations else {}
    summary = {
        "probe_id": probe_id,
        "max_iter": max_iter,
        "iterations": iterations,
        "iter_count": len(iterations),
        "final_status": final_status.get("rerun_status")
                        or final_status.get("status"),
        "dry_run": dry_run,
    }

    # Persist run log
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"{probe_id}_{int(time.time())}.json"
        log_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        summary["log_path"] = str(log_path)
    except OSError:
        pass
    return summary


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", required=True)
    ap.add_argument("--max-iter", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ns = ap.parse_args(argv[1:])
    summary = run_cycle(ns.probe, max_iter=ns.max_iter, dry_run=ns.dry_run)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    final = (summary.get("final_status") or "").lower()
    if final == "proven":
        return 0
    if final in ("refuted", "patch-failed", "out-of-scope",
                 "no-strategy-match", "timeout", "error"):
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
