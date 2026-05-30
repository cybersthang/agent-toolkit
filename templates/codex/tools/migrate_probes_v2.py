#!/usr/bin/env python
"""Migrate `.agent-toolkit/acceptance-probes.json` from v1 → v2.

v1 probes had only `evidence.required_tools` + optional `falsification`
(no explicit runner). v2 adds:

  - `schema_version: 2` at root.
  - Per probe: `auto_run: bool`, `recipe_drift_tolerance: enum`.
  - Per probe.falsification: `type` enum extended with
    `playwright_python`, `mcp_call`.

Safe migration: existing probes get sensible defaults, never blow away
fields. Idempotent — re-running on v2 is a no-op.

Usage:

  python templates/codex/tools/migrate_probes_v2.py <project-root>
  python templates/codex/tools/migrate_probes_v2.py <project-root> --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _is_v2(data: dict) -> bool:
    return data.get("schema_version") == 2


def _backup(path: Path) -> Path:
    bak = path.with_suffix(path.suffix + ".v1.bak")
    bak.write_bytes(path.read_bytes())
    return bak


def _upgrade_probe(probe: dict) -> dict:
    """Apply v1 → v2 transform to a single probe entry.

    Defaults:
      - auto_run = False (must opt-in to avoid surprise runs).
      - recipe_drift_tolerance = "medium".
      - falsification.type unchanged unless null/missing.
    """
    if "auto_run" not in probe:
        probe["auto_run"] = False
    if "recipe_drift_tolerance" not in probe:
        probe["recipe_drift_tolerance"] = "medium"

    fal = probe.get("falsification") or {}
    if isinstance(fal, dict):
        # If type unset but description present, leave type=null;
        # spec-vs-evidence-diff will WARN that the probe lacks an
        # executable runner. Don't auto-pick a type — DEV must decide.
        probe["falsification"] = fal
    return probe


def migrate(probes_path: Path, dry_run: bool = False) -> dict:
    if not probes_path.exists():
        return {"status": "missing", "path": str(probes_path)}

    raw = probes_path.read_text(encoding="utf-8-sig")
    data = json.loads(raw)

    if _is_v2(data):
        return {"status": "already-v2", "path": str(probes_path),
                "probe_count": len(data.get("probes") or [])}

    upgraded_probes = [_upgrade_probe(p) for p in (data.get("probes") or [])]
    new_data = dict(data)
    new_data["schema_version"] = 2
    new_data["probes"] = upgraded_probes

    summary = {
        "status": "would-migrate" if dry_run else "migrated",
        "path": str(probes_path),
        "probes_upgraded": len(upgraded_probes),
        "added_fields": ["schema_version", "auto_run",
                         "recipe_drift_tolerance"],
    }
    if dry_run:
        return summary

    bak = _backup(probes_path)
    summary["backup"] = str(bak)
    probes_path.write_text(
        json.dumps(new_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project_root", type=Path,
                    help="Path to project root (parent of .agent-toolkit/).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print diff plan without writing.")
    args = ap.parse_args(argv[1:])

    probes_path = args.project_root / ".agent-toolkit" / "acceptance-probes.json"
    result = migrate(probes_path, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "missing" else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
