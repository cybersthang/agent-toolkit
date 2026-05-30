#!/usr/bin/env python
"""Stand-in for `.codex/tools/falsify.py` that records argv to a JSON
file. Used by `test_hooks_integration.py` to verify auto_run_probes
hook passes the right probe id.

Echoes `{"stub": true, "verdict": "proven"}` to stdout; exits 0.

Set RECORDING_FALSIFY_RC=N to force a different exit code.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    rec_path = os.environ.get("RECORDING_FILE")
    if rec_path:
        try:
            existing = []
            p = Path(rec_path)
            if p.exists():
                existing = json.loads(p.read_text(encoding="utf-8"))
            existing.append({"argv": sys.argv[1:]})
            p.write_text(json.dumps(existing, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        except OSError:
            pass

    print(json.dumps({"stub": True, "verdict": "proven"}))
    return int(os.environ.get("RECORDING_FALSIFY_RC", "0"))


if __name__ == "__main__":
    sys.exit(main())
