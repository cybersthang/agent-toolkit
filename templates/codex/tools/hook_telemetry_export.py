#!/usr/bin/env python
"""G6 v0.11.0 — export hook telemetry to JSONL for cross-machine aggregation.

Reads ring-buffer state files written by the hooks (during normal session
operation) and appends new events to a date-partitioned JSONL file. The
JSONL files are append-only and safe to sync to shared storage (NFS,
S3, git-lfs) without merge conflicts.

Sources read:
  .agent-toolkit/.hook_fire_log.json   — emit_fire_event() ring buffer (1000 max)
  .agent-toolkit/.hook_crash_log.json  — _log_hook_crash() ring buffer (50 max)

Output:
  .agent-toolkit/telemetry/hooks-YYYY-MM-DD.jsonl   — append-only, UTC date

Dedup:
  .agent-toolkit/telemetry/.last_export_ts.json     — high-water mark

Optional adapters (placeholders, not yet wired):
  --otlp-url <url>     POST events to OTLP HTTP/JSON endpoint (NYI, stub)

Usage:
  # Run from project root, typically via cron / git-pre-push hook:
  python <toolkit>/templates/codex/tools/hook_telemetry_export.py
  python .../hook_telemetry_export.py --workspace /path/to/project --since 1d
  python .../hook_telemetry_export.py --otlp-url https://otel.example.com/v1/logs

Exit codes:
  0  success (with or without events to export)
  2  invalid arguments
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


FIRE_LOG_REL = ".agent-toolkit/.hook_fire_log.json"
CRASH_LOG_REL = ".agent-toolkit/.hook_crash_log.json"
TELEMETRY_DIR_REL = ".agent-toolkit/telemetry"
HIGH_WATER_REL = ".agent-toolkit/telemetry/.last_export_ts.json"


def _read_events(path: Path) -> List[Dict[str, Any]]:
    """Read either {"events": [...]} or raw list shape. Empty on any error."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict):
        events = data.get("events") or []
        if isinstance(events, list):
            return [e for e in events if isinstance(e, dict)]
    elif isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    return []


def _read_high_water(workspace: Path) -> int:
    path = workspace / HIGH_WATER_REL
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    if isinstance(data, dict):
        return int(data.get("ts") or 0)
    return 0


def _write_high_water(workspace: Path, ts: int) -> None:
    path = workspace / HIGH_WATER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"ts": ts, "iso": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()}),
        encoding="utf-8",
    )


def _enrich(event: Dict[str, Any], source: str, workspace: Path) -> Dict[str, Any]:
    """Tag the event with host + workspace + source kind so cross-machine
    aggregates can disambiguate (5 devs × 5 projects = 25 streams in one
    bucket otherwise indistinguishable)."""
    enriched = dict(event)
    enriched.setdefault("ts", int(time.time()))
    enriched["_source"] = source
    enriched["_host"] = socket.gethostname()
    enriched["_workspace"] = str(workspace)
    return enriched


def _filter_new(events: Iterable[Dict[str, Any]], since: int) -> List[Dict[str, Any]]:
    return [e for e in events if int(e.get("ts") or 0) > since]


def _jsonl_path_for_today(workspace: Path) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return workspace / TELEMETRY_DIR_REL / f"hooks-{today}.jsonl"


def _append_jsonl(path: Path, events: List[Dict[str, Any]]) -> int:
    """Append events as JSONL. Returns count written. Atomic per-line write
    (each event is one line; concurrent appenders are safe on POSIX up to
    PIPE_BUF lines)."""
    if not events:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("a", encoding="utf-8") as fh:
        for evt in events:
            fh.write(json.dumps(evt, ensure_ascii=False))
            fh.write("\n")
            written += 1
    return written


def _post_otlp(url: str, events: List[Dict[str, Any]]) -> int:
    """Stub for OTLP HTTP/JSON endpoint. Currently writes events to a
    parallel marker file so DEV can see the intent without requiring
    the requests dep. Real impl deferred — install `requests` or
    `httpx` and post to `url + '/v1/logs'` with OTLP log shape.
    """
    # The full OTLP shape (resourceLogs → scopeLogs → logRecords) is heavy
    # for a stub. Just record that we *would* send N events to url.
    if not events:
        return 0
    print(
        f"[otlp-stub] would POST {len(events)} events to {url} "
        f"(install `requests`/`httpx` + implement OTLP encoder to wire)",
        file=sys.stderr,
    )
    return len(events)


def export(workspace: Path, *,
           since: Optional[int] = None,
           otlp_url: Optional[str] = None,
           dry_run: bool = False) -> Dict[str, Any]:
    """Run one export pass. Returns summary dict for caller.

    `since`: only events with `ts > since` are exported. Defaults to the
    high-water mark from the previous run.
    `otlp_url`: optional OTLP HTTP endpoint (currently stub).
    `dry_run`: if True, count events but don't write files.
    """
    high_water = since if since is not None else _read_high_water(workspace)

    fire = [_enrich(e, "fire", workspace) for e in _read_events(workspace / FIRE_LOG_REL)]
    crash = [_enrich(e, "crash", workspace) for e in _read_events(workspace / CRASH_LOG_REL)]

    all_events = sorted(fire + crash, key=lambda e: int(e.get("ts") or 0))
    new_events = _filter_new(all_events, high_water)

    summary: Dict[str, Any] = {
        "workspace": str(workspace),
        "high_water_before": high_water,
        "fire_total": len(fire),
        "crash_total": len(crash),
        "new_events": len(new_events),
        "wrote_jsonl": 0,
        "wrote_otlp": 0,
    }

    if dry_run or not new_events:
        return summary

    jsonl_path = _jsonl_path_for_today(workspace)
    summary["wrote_jsonl"] = _append_jsonl(jsonl_path, new_events)
    summary["jsonl_path"] = str(jsonl_path)

    if otlp_url:
        summary["wrote_otlp"] = _post_otlp(otlp_url, new_events)

    latest_ts = max(int(e.get("ts") or 0) for e in new_events)
    _write_high_water(workspace, latest_ts)
    summary["high_water_after"] = latest_ts
    return summary


def _parse_since(value: str) -> Optional[int]:
    """Parse `--since` arg. Supports `1d`/`1h`/`1m`/`now` or epoch seconds."""
    if not value:
        return None
    value = value.strip().lower()
    if value == "now":
        return int(time.time())
    if value.endswith("d"):
        return int(time.time()) - int(value[:-1]) * 86400
    if value.endswith("h"):
        return int(time.time()) - int(value[:-1]) * 3600
    if value.endswith("m"):
        return int(time.time()) - int(value[:-1]) * 60
    try:
        return int(value)
    except ValueError:
        raise SystemExit(f"--since: invalid value {value!r}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Export hook telemetry to JSONL.")
    ap.add_argument("--workspace", type=Path,
                    default=Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    ap.add_argument("--since", type=str, default=None,
                    help="Only export events newer than this. Accepts '1d', "
                         "'1h', '1m', 'now', or epoch seconds. Defaults to "
                         "stored high-water mark.")
    ap.add_argument("--otlp-url", type=str, default=None,
                    help="OTLP HTTP/JSON endpoint (currently stub).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Count events but don't write files.")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress summary print.")
    args = ap.parse_args(argv)

    since = _parse_since(args.since) if args.since else None
    summary = export(args.workspace.resolve(),
                     since=since,
                     otlp_url=args.otlp_url,
                     dry_run=args.dry_run)

    if not args.quiet:
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
