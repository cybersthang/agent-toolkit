#!/usr/bin/env python
"""Stub MCP server for testing mcp_call.py success path.

Reads JSON-RPC lines from stdin; responds to `initialize` +
`tools/call`. Exits after handling the first tool/call request.

The stub returns a fixed result `{"echo": <args>, "stub": true}` for
ANY tool name — letting tests assert wire-level behaviour without
needing a real backend.

Set env var `FAKE_MCP_RETURN_ERROR=1` to make the stub respond with
an MCP isError envelope (for testing rc=1 path).

Set env var `FAKE_MCP_FAIL_PROTOCOL=1` to emit malformed JSON
(for testing error handling).
"""
from __future__ import annotations

import json
import os
import sys


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    if os.environ.get("FAKE_MCP_FAIL_PROTOCOL") == "1":
        sys.stdout.write("not valid json\n")
        sys.stdout.flush()
        return 0

    return_error = os.environ.get("FAKE_MCP_RETURN_ERROR") == "1"

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method") or ""
        req_id = msg.get("id")

        if method == "initialize":
            _send({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "fake-mcp-server",
                        "version": "0.1.0",
                    },
                },
            })
        elif method == "notifications/initialized":
            pass
        elif method == "tools/call":
            params = msg.get("params") or {}
            tool_name = params.get("name") or ""
            args = params.get("arguments") or {}
            if return_error:
                _send({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "isError": True,
                        "content": [{
                            "type": "text",
                            "text": "stub-error: %s rejected" % tool_name,
                        }],
                    },
                })
            else:
                _send({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "isError": False,
                        "stub": True,
                        "tool": tool_name,
                        "echo": args,
                        "content": [{
                            "type": "text",
                            "text": "stub-ok",
                        }],
                    },
                })
            return 0
        else:
            _send({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": "method not found"},
            })

    return 0


if __name__ == "__main__":
    sys.exit(main())
