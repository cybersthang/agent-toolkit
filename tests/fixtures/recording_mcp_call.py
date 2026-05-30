#!/usr/bin/env python
"""Stand-in for `.codex/tools/mcp_call.py` that records its argv to a
JSON file instead of actually invoking an MCP server.

Used by `test_hooks_integration.py` to verify that
auto_test_runner / auto_run_probes / daemon_manager pass correct
server + tool + args payload.

Behaviour:
  - Reads RECORDING_FILE env var (path to write argv JSON).
  - Writes {"argv": sys.argv, "args_json": parsed --args} to that file.
  - Echoes stub JSON `{"stub": true, "ok": true}` to stdout.
  - Exits 0.

Set RECORDING_MCP_RC=N to force a different exit code (test rc=1 / rc=2).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    rec_path = os.environ.get("RECORDING_FILE")
    if rec_path:
        argv_dict = {"argv": sys.argv[1:]}
        # Best-effort: parse --args N+1
        try:
            i = sys.argv.index("--args")
            if i + 1 < len(sys.argv):
                argv_dict["args_json"] = json.loads(sys.argv[i + 1])
        except (ValueError, json.JSONDecodeError):
            pass
        try:
            existing = []
            p = Path(rec_path)
            if p.exists():
                existing = json.loads(p.read_text(encoding="utf-8"))
            existing.append(argv_dict)
            p.write_text(json.dumps(existing, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        except OSError:
            pass

    print(json.dumps({"stub": True, "ok": True}))
    return int(os.environ.get("RECORDING_MCP_RC", "0"))


if __name__ == "__main__":
    sys.exit(main())
