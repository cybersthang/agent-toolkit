#!/usr/bin/env python
"""mcp-call — generic CLI bridge to invoke an MCP tool from hooks/scripts.

Many agent-toolkit hooks need to call an MCP tool (e.g.
`mcp__realdata_test__run_module_test`) from subprocess context. Claude
Code's main agent has direct MCP access, but hooks run as standalone
subprocesses and can't. This CLI uses two invocation paths:

  1. **Direct MCP server subprocess** (default): spawn the server
     command from `.mcp.json` and speak JSON-RPC 2.0 over stdin/stdout.
     Self-contained, no external CLI required — works on CI / headless
     machines / fresh dev boxes.

  2. **`claude --print --mcp-call <server>:<tool>`** (opt-in): set env
     var `TOOLKIT_MCP_CLIENT=claude_cli` to prefer this. It reuses
     Claude Code's connection-pooled MCP client and avoids the per-call
     server spawn cost. NOTE: as of 2026-05-20 this flag is not yet
     published in the Claude Code CLI surface — kept as a future-proof
     path; set the env var only after verifying `claude --help` shows
     `--mcp-call`.

Default behavior (path 1) does cold-spawn the server per call — ~1-2 s
overhead. For heavy auto-runner workflows install a long-lived MCP
client (path 2) or run hooks via the Claude Code main agent's tool
surface instead.

Schema (CLI args):

  mcp-call <server> <tool> --args '{"key":"val"}' [--timeout 60]

Stdout: JSON tool_result on success.
Stderr: error messages.
Exit codes:
  0 — tool returned result
  1 — tool returned error (isError=true in MCP envelope)
  2 — invocation failure (server not configured, etc.)

Examples:

  python .codex/tools/mcp_call.py realdata_test run_module_test \\
      --args '{"module_name":"my_module","module_action":"update","allow_db_write":true}'

  python .codex/tools/mcp_call.py postgres query_readonly \\
      --args '{"sql":"SELECT 1 AS test","limit":1}'
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_CONFIG = REPO_ROOT / ".mcp.json"


def _load_mcp_config() -> Dict[str, Any]:
    """Read project .mcp.json (fail-open empty dict)."""
    if not MCP_CONFIG.exists():
        return {}
    try:
        return json.loads(MCP_CONFIG.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def _via_claude_cli(server: str, tool: str, args: Dict[str, Any],
                    timeout: int) -> Optional[Dict[str, Any]]:
    """Try invoking via Claude CLI. Returns parsed JSON or None
    if Claude CLI unavailable (caller falls back to direct-spawn)."""
    claude = shutil.which("claude")
    if not claude:
        return None
    cmd = [
        claude, "--print",
        "--mcp-call", f"{server}:{tool}",
        "--mcp-args", json.dumps(args, ensure_ascii=False),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout + 10,
        )
    except subprocess.TimeoutExpired:
        return {"_invocation_error": "claude-cli-timeout"}
    except (OSError, FileNotFoundError):
        return None

    if proc.returncode != 0:
        return {
            "_invocation_error": "claude-cli-rc=%d" % proc.returncode,
            "stderr": proc.stderr,
        }
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"_invocation_error": "claude-cli-bad-json", "stdout": proc.stdout}


def _via_direct_spawn(server: str, tool: str, args: Dict[str, Any],
                      timeout: int) -> Dict[str, Any]:
    """Fallback: spawn the MCP server subprocess and speak JSON-RPC.

    Implementation NOTE: full MCP protocol speaks JSON-RPC 2.0 with
    initialize -> notifications/initialized -> tools/call. To stay
    dependency-free this script does the minimum handshake. Projects
    that need richer MCP semantics should install the `mcp` Python
    package and set $TOOLKIT_MCP_CLIENT=mcp_sdk.
    """
    config = _load_mcp_config()
    servers = config.get("mcpServers") or {}
    entry = servers.get(server)
    if not entry:
        return {"_invocation_error": f"server '{server}' not in .mcp.json"}
    cmd = [entry.get("command")] + list(entry.get("args") or [])
    if not cmd[0]:
        return {"_invocation_error": f"server '{server}' has no command"}

    env = os.environ.copy()
    env.update(entry.get("env") or {})

    req_init = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "agent-toolkit-mcp-call",
                           "version": "1.0"},
        },
    })
    req_initialized = json.dumps({
        "jsonrpc": "2.0", "method": "notifications/initialized",
        "params": {},
    })
    req_call = json.dumps({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": tool, "arguments": args},
    })

    try:
        proc = subprocess.run(
            cmd,
            input="\n".join([req_init, req_initialized, req_call]) + "\n",
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env=env, timeout=timeout + 10,
        )
    except subprocess.TimeoutExpired:
        return {"_invocation_error": "direct-spawn-timeout"}
    except (OSError, FileNotFoundError) as e:
        return {"_invocation_error": f"direct-spawn-failed: {e}"}

    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == 2:
            if "error" in msg:
                return {"_invocation_error": "mcp-error",
                        "error": msg["error"]}
            return msg.get("result") or {}

    return {"_invocation_error": "no-response-from-server",
            "stdout_tail": (proc.stdout or "")[-500:],
            "stderr_tail": (proc.stderr or "")[-500:]}


def call(server: str, tool: str, args: Dict[str, Any],
         timeout: int = 60) -> Dict[str, Any]:
    """Public API used by other toolkit scripts. Returns parsed
    tool_result OR {"_invocation_error": "..."} on failure.

    Default path: direct-spawn JSON-RPC. To prefer the Claude CLI path
    (opt-in, requires `claude --mcp-call` flag), set env var
    `TOOLKIT_MCP_CLIENT=claude_cli`.
    """
    if os.environ.get("TOOLKIT_MCP_CLIENT", "").lower() == "claude_cli":
        via_claude = _via_claude_cli(server, tool, args, timeout)
        if via_claude is not None and "_invocation_error" not in via_claude:
            return via_claude
        # Fall through to direct spawn if claude path failed.
    return _via_direct_spawn(server, tool, args, timeout)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="MCP tool invocation bridge")
    ap.add_argument("server", help="MCP server name (key in .mcp.json)")
    ap.add_argument("tool", help="MCP tool name")
    ap.add_argument("--args", default="{}",
                    help="JSON-encoded arguments object")
    ap.add_argument("--timeout", type=int, default=60,
                    help="Tool timeout in seconds")
    ns = ap.parse_args(argv[1:])
    try:
        args_obj = json.loads(ns.args)
    except json.JSONDecodeError as e:
        print(f"--args is not valid JSON: {e}", file=sys.stderr)
        return 2

    result = call(ns.server, ns.tool, args_obj, timeout=ns.timeout)
    if "_invocation_error" in result:
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if isinstance(result, dict) and result.get("isError"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
