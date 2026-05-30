"""Live MCP smoke driver: spawn each start_*_mcp.py wrapper, send JSON-RPC initialize +
tools/list (+ optional tools/call for env_status), and report PASS/FAIL per server.
This proves the wrappers boot, register tools, and answer a request through stdio.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable

SERVERS = [
    {
        "name": "codebase",
        "wrapper": ROOT / ".codex" / "start_codebase_mcp.py",
        "expected_tools": [
            "workspace_status",
            "discover_modules",
            "module_dependencies",
            "find_inheritance_chain",
            "list_canonical_decisions",
            "lookup_canonical_decision",
        ],
        "extra_calls": [
            {"name": "lookup_canonical_decision", "arguments": {"topic": "determinism"}},
        ],
    },
    {
        "name": "postgres",
        "wrapper": ROOT / ".codex" / "start_postgres_mcp.py",
        "expected_tools": ["env_status", "list_databases", "describe_table", "query_readonly"],
        "extra_calls": [{"name": "env_status", "arguments": {}}],
    },
    {
        "name": "realdata_test",
        "wrapper": ROOT / ".codex" / "start_realdata_test_mcp.py",
        "expected_tools": [
            "env_status",
            "build_smoke_test_command",
            "eval_orm_expression",
            "consistency_check_eval",
            "compare_with_expected",
        ],
        "extra_calls": [{"name": "env_status", "arguments": {}}],
    },
    {
        "name": "jira_production",
        "wrapper": ROOT / ".codex" / "start_jira_production_mcp.py",
        "expected_tools": [
            "env_status",
            "get_issue",
            "search_issues",
            "list_projects",
            "my_assigned_issues",
        ],
        "extra_calls": [{"name": "env_status", "arguments": {}}],
        "expected_server_name": "jira_production",
    },
    {
        "name": "jira_preproduction",
        "wrapper": ROOT / ".codex" / "start_jira_preproduction_mcp.py",
        "expected_tools": [
            "env_status",
            "get_issue",
            "search_issues",
            "list_projects",
            "my_assigned_issues",
        ],
        "extra_calls": [{"name": "env_status", "arguments": {}}],
        "expected_server_name": "jira_preproduction",
    },
]


def build_requests(extra_calls: List[Dict[str, Any]]) -> bytes:
    requests: List[Dict[str, Any]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    for index, call in enumerate(extra_calls, start=3):
        requests.append({"jsonrpc": "2.0", "id": index, "method": "tools/call", "params": call})
    return ("\n".join(json.dumps(req) for req in requests) + "\n").encode("utf-8")


def parse_responses(raw: bytes) -> List[Dict[str, Any]]:
    responses: List[Dict[str, Any]] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            responses.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return responses


def run_server(spec: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
    payload = build_requests(spec.get("extra_calls", []))
    started_at = time.monotonic()
    try:
        proc = subprocess.run(
            [PYTHON, str(spec["wrapper"])],
            input=payload,
            cwd=str(ROOT),
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "name": spec["name"],
            "ok": False,
            "error": f"timeout after {timeout}s",
            "stderr": (exc.stderr or b"").decode("utf-8", errors="replace")[-1000:],
        }
    elapsed = time.monotonic() - started_at
    responses = parse_responses(proc.stdout)
    by_id = {r.get("id"): r for r in responses}
    server_info = (by_id.get(1) or {}).get("result", {}).get("serverInfo") or {}
    tools_payload = (by_id.get(2) or {}).get("result", {}).get("tools") or []
    tool_names = [t.get("name") for t in tools_payload]

    issues: List[str] = []
    if not server_info:
        issues.append("missing serverInfo (initialize failed)")
    if not tool_names:
        issues.append("tools/list returned empty")
    expected_name = spec.get("expected_server_name") or spec["name"]
    if server_info.get("name") and server_info.get("name") != expected_name:
        issues.append(
            f"serverInfo.name={server_info.get('name')!r} (expected {expected_name!r})"
        )
    for required_tool in spec.get("expected_tools", []):
        if required_tool not in tool_names:
            issues.append(f"missing tool: {required_tool}")

    extra_results: List[Dict[str, Any]] = []
    for index, _ in enumerate(spec.get("extra_calls", []), start=3):
        response = by_id.get(index) or {}
        result = response.get("result") or {}
        is_error = bool(result.get("isError"))
        extra_results.append(
            {
                "id": index,
                "is_error": is_error,
                "text_preview": (
                    (result.get("content") or [{}])[0].get("text", "") or response.get("error", "")
                )[:200],
            }
        )

    return {
        "name": spec["name"],
        "ok": not issues,
        "elapsed_s": round(elapsed, 2),
        "returncode": proc.returncode,
        "server_info": server_info,
        "tool_count": len(tool_names),
        "issues": issues,
        "extra_calls": extra_results,
        "stderr_tail": (proc.stderr or b"").decode("utf-8", errors="replace")[-400:],
    }


def main() -> int:
    print(f"Workspace: {ROOT}")
    print(f"Python: {PYTHON}\n")
    results = [run_server(spec) for spec in SERVERS]
    fail_count = 0
    for outcome in results:
        status = "PASS" if outcome["ok"] else "FAIL"
        if not outcome["ok"]:
            fail_count += 1
        print(f"[{status}] {outcome['name']}  ({outcome['elapsed_s']}s, "
              f"tools={outcome['tool_count']}, rc={outcome['returncode']})")
        if outcome.get("server_info"):
            print(f"        serverInfo: {outcome['server_info']}")
        for issue in outcome["issues"]:
            print(f"        - issue: {issue}")
        for extra in outcome["extra_calls"]:
            tag = "ERR" if extra["is_error"] else "OK"
            print(f"        - tools/call id={extra['id']} {tag}: {extra['text_preview'][:120]}...")
        if outcome["stderr_tail"].strip():
            print(f"        stderr_tail: {outcome['stderr_tail'].strip()[:300]}")
        print()
    print(f"Summary: {len(results) - fail_count}/{len(results)} servers PASSED")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
