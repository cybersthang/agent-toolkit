#!/usr/bin/env python
"""Stop hook — advisory report on recipe-vs-script drift across probes.

Reads `.agent-toolkit/acceptance-probes.json` + each probe's `runner.
spec_file`, tokenizes the recipe description vs script text, and
emits a warning when a load-bearing token in the recipe is missing
from the script.

Fails open: never blocks Stop. Output is plain text appended to the
agent's surface so the next turn sees it.

Config: `.agent-toolkit/recipe_drift.json` (see _DEFAULT_CONFIG).
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

sys.path.insert(0, str(Path(__file__).parent))
from _common import run_main_safe


if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


_DEFAULT_CONFIG = {
    "enabled": True,
    "ignore_words": [
        "the", "a", "an", "is", "of", "to", "in", "on", "at", "and",
        "or", "but", "with", "for", "from", "by", "as", "be", "this",
        "that", "are", "was", "were", "via", "etc", "and", "must",
        "should", "all", "each", "any", "any", "do", "does", "did",
        "có", "không", "phải", "thì", "là", "trên", "dưới", "với",
        "cho", "của", "và", "hay", "hoặc", "mà"
    ],
    "load_bearing_keywords": {
        "loose": ["postgres", "p99", "1000", "freeze", "sigstop",
                  "docker", "kill"],
        "medium": [
            "longpoll", "longpolling", "shadow", "blockui", "rpc",
            "indexeddb", "ms", "postgres", "p99", "p50", "freeze",
            "sigstop", "docker", "kill", "tabs", "groupby",
            "microbench", "delta", "fetch", "xhr"
        ],
        "strict": []
    },
    "default_tolerance": "medium",
    "max_probes_reported": 5
}


def _load_config(workspace: Path) -> Dict[str, Any]:
    path = workspace / ".agent-toolkit" / "recipe_drift.json"
    cfg = json.loads(json.dumps(_DEFAULT_CONFIG))
    if path.exists():
        try:
            override = json.loads(path.read_text(encoding="utf-8-sig"))
            cfg.update(override)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def _load_probes(workspace: Path) -> List[Dict[str, Any]]:
    p = workspace / ".agent-toolkit" / "acceptance-probes.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return []
    return [pr for pr in (data.get("probes") or []) if isinstance(pr, dict)]


def _tokenize(text: str, ignore: Set[str]) -> Set[str]:
    if not text:
        return set()
    toks = re.findall(r"[a-z0-9]{2,}", text.lower())
    return set(t for t in toks if t not in ignore)


def _drift_for_probe(probe: Dict[str, Any], workspace: Path,
                     config: Dict[str, Any]) -> List[str]:
    falsi = probe.get("falsification") or {}
    desc = falsi.get("description") or ""
    runner = falsi.get("runner") or probe.get("runner") or {}
    spec_file_rel = runner.get("spec_file")
    if not desc or not spec_file_rel:
        return []
    spec_path = workspace / spec_file_rel
    if not spec_path.exists():
        return [f"runner.spec_file does not exist: {spec_file_rel}"]
    try:
        script_text = spec_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []

    ignore = set(config.get("ignore_words") or [])
    tolerance = probe.get("recipe_drift_tolerance") or config.get(
        "default_tolerance", "medium")
    load_bearing = set(
        (config.get("load_bearing_keywords") or {}).get(tolerance) or []
    )
    desc_tokens = _tokenize(desc, ignore)
    script_tokens = _tokenize(script_text, ignore)

    if tolerance == "strict":
        missing = desc_tokens - script_tokens
    else:
        missing = (desc_tokens & load_bearing) - script_tokens

    if not missing:
        return []
    return [f"recipe mentions {sorted(missing)} not present in {spec_file_rel}"]


def main() -> int:
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        return 0
    if os.environ.get("AGENT_TOOLKIT_DRIFT_DISABLE") == "1":
        return 0

    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if envelope.get("stop_hook_active"):
        return 0

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()
    config = _load_config(workspace)
    if not config.get("enabled"):
        return 0

    probes = _load_probes(workspace)
    if not probes:
        return 0

    findings: List[str] = []
    cap = int(config.get("max_probes_reported", 5))
    for p in probes:
        if len(findings) >= cap:
            findings.append(
                f"... +{sum(1 for _ in probes) - cap} more probes "
                f"(set max_probes_reported higher to see all)")
            break
        drifts = _drift_for_probe(p, workspace, config)
        if drifts:
            findings.append(f"probe `{p.get('id')}` — " + "; ".join(drifts))

    if findings:
        print(
            "[spec-drift] recipe vs script divergences (advisory):\n"
            + "\n".join("  - " + f for f in findings)
        )
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
