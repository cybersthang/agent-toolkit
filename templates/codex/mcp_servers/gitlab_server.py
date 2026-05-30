from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from common import SimpleMcpServer, ToolDefinition


# Read-only GitLab CI MCP. Mirrors jira_server.py: stdlib urllib only
# (dependency-free), credentials from `.codex/mcp.local.env` via the
# `{{ENV_PREFIX}}_GITLAB_*` env vars set by start_gitlab_mcp.py.
#
# Scope by design: READ-ONLY (a PAT with `read_api` is enough). No
# trigger/retry/cancel tools — taking authoring CI actions would conflict
# with the toolkit's git_guardrails philosophy (the AGENT does not perform
# state-changing remote actions without explicit DEV authority). The point
# is to *see why the build broke* and pull the failing logs so the agent can
# fix the code locally.

DEFAULT_BASE_URL = "https://gitlab.com"
MAX_TRACE_CHARS = 100_000
DEFAULT_TAIL_LINES = 200


def configured_server_name() -> str:
    return os.environ.get("{{ENV_PREFIX}}_GITLAB_SERVER_NAME") or "gitlab"


def configured_base_url() -> str:
    base = (os.environ.get("{{ENV_PREFIX}}_GITLAB_URL") or DEFAULT_BASE_URL).strip()
    base = base.rstrip("/")
    # Tolerate a base that already includes the API suffix.
    if base.endswith("/api/v4"):
        base = base[: -len("/api/v4")]
    return base


def configured_token() -> str:
    token = (os.environ.get("{{ENV_PREFIX}}_GITLAB_TOKEN") or "").strip()
    if not token:
        raise ValueError(
            "{{ENV_PREFIX}}_GITLAB_TOKEN is required (a GitLab personal access "
            "token with the read_api scope)"
        )
    return token


def default_project() -> str:
    return (os.environ.get("{{ENV_PREFIX}}_GITLAB_PROJECT") or "").strip()


def resolve_project(arguments: dict[str, Any]) -> str:
    """Return the URL-ready project id segment.

    Accepts a numeric project id ('123') or a namespaced path
    ('group/sub/project'). Falls back to {{ENV_PREFIX}}_GITLAB_PROJECT.
    """
    project = str(arguments.get("project") or default_project()).strip()
    if not project:
        raise ValueError(
            "project is required — pass `project` (numeric id or 'group/project' "
            "path) or set {{ENV_PREFIX}}_GITLAB_PROJECT in mcp.local.env"
        )
    if project.isdigit():
        return project
    return quote(project, safe="")


def auth_headers() -> dict[str, str]:
    return {
        "PRIVATE-TOKEN": configured_token(),
        "Accept": "application/json",
        "User-Agent": f"codex-{configured_server_name()}-mcp/0.1",
    }


def read_response_body(response: Any) -> str:
    raw = response.read()
    content_type = response.headers.get("Content-Type", "")
    match = re.search(r"charset=([\w.-]+)", content_type)
    encoding = match.group(1) if match else "utf-8"
    return raw.decode(encoding, errors="replace")


def gitlab_get(path: str, params: dict[str, str] | None = None,
               raw_text: bool = False) -> Any:
    """GET {base}/api/v4{path}. Returns parsed JSON, or raw text when
    raw_text=True (job traces are plain text, not JSON)."""
    url = configured_base_url() + "/api/v4" + path
    if params:
        url += "?" + urlencode(params)
    request = Request(url, headers=auth_headers())
    try:
        with urlopen(request, timeout=60) as response:
            body = read_response_body(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitLab HTTP {exc.code}: {detail[:1000]}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitLab connection failed: {exc.reason}") from exc

    if raw_text:
        return body
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GitLab returned non-JSON response: {body[:1000]}") from exc


def tail_text(text: str, tail_lines: int, max_chars: int = MAX_TRACE_CHARS) -> tuple[str, bool]:
    """Return (tail, truncated). Keep the LAST tail_lines lines (build errors
    live at the end of a trace) and cap total chars."""
    lines = text.splitlines()
    truncated = False
    if tail_lines and len(lines) > tail_lines:
        lines = lines[-tail_lines:]
        truncated = True
    out = "\n".join(lines)
    if len(out) > max_chars:
        out = "...[earlier output truncated]\n" + out[-max_chars:]
        truncated = True
    return out, truncated


def normalize_pipeline(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": p.get("id"),
        "iid": p.get("iid"),
        "status": p.get("status"),
        "ref": p.get("ref"),
        "sha": p.get("sha"),
        "source": p.get("source"),
        "web_url": p.get("web_url"),
        "created_at": p.get("created_at"),
        "updated_at": p.get("updated_at"),
    }


def normalize_job(j: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": j.get("id"),
        "name": j.get("name"),
        "stage": j.get("stage"),
        "status": j.get("status"),
        "allow_failure": j.get("allow_failure"),
        "failure_reason": j.get("failure_reason"),
        "web_url": j.get("web_url"),
        "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"),
        "duration": j.get("duration"),
    }


def _as_int(value: Any, name: str) -> int:
    """Coerce a GitLab numeric id (int or numeric string) to int, with a
    clear error. Schemas declare these as integers but a wrapper may pass a
    string."""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer, got {value!r}")


def _fetch_pipeline_jobs(project: str, pipeline_id: int | str) -> list[dict[str, Any]]:
    """Fetch ALL jobs of a pipeline, following pagination. GitLab caps
    per_page at 100, so a pipeline with >100 jobs needs multiple pages —
    without this loop, build_errors could miss a failing job on page 2+ and
    report a false green. Stops at the first short/empty page; hard cap at
    50 pages (5000 jobs) as a runaway guard."""
    jobs: list[dict[str, Any]] = []
    for page in range(1, 51):
        batch = gitlab_get(
            f"/projects/{project}/pipelines/{pipeline_id}/jobs",
            {"per_page": "100", "page": str(page)},
        )
        if not isinstance(batch, list) or not batch:
            break
        jobs.extend(batch)
        if len(batch) < 100:
            break
    return jobs


def _latest_pipeline_obj(project: str, ref: str = "") -> dict[str, Any] | None:
    params = {"per_page": "1", "order_by": "id", "sort": "desc"}
    if ref:
        params["ref"] = ref
    payload = gitlab_get(f"/projects/{project}/pipelines", params)
    if isinstance(payload, list) and payload:
        return payload[0]
    return None


# ── tools ──────────────────────────────────────────────────────────────────

def env_status(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "server_name": configured_server_name(),
        "url": configured_base_url(),
        "project": default_project(),
        "token_configured": bool((os.environ.get("{{ENV_PREFIX}}_GITLAB_TOKEN") or "").strip()),
    }


def latest_pipeline(arguments: dict[str, Any]) -> dict[str, Any]:
    project = resolve_project(arguments)
    ref = str(arguments.get("ref") or "").strip()
    p = _latest_pipeline_obj(project, ref)
    if p is None:
        return {"message": f"no pipelines found{f' for ref {ref}' if ref else ''}"}
    return normalize_pipeline(p)


def pipeline_jobs(arguments: dict[str, Any]) -> dict[str, Any]:
    project = resolve_project(arguments)
    if arguments.get("pipeline_id") is None:
        raise ValueError("pipeline_id is required")
    pipeline_id = _as_int(arguments.get("pipeline_id"), "pipeline_id")
    scope = str(arguments.get("scope") or "").strip().lower()
    jobs = [normalize_job(j) for j in _fetch_pipeline_jobs(project, pipeline_id)]
    if scope:
        jobs = [j for j in jobs if (j.get("status") or "").lower() == scope]
    return {"pipeline_id": pipeline_id, "count": len(jobs), "jobs": jobs}


def job_trace(arguments: dict[str, Any]) -> dict[str, Any]:
    project = resolve_project(arguments)
    if arguments.get("job_id") is None:
        raise ValueError("job_id is required")
    job_id = _as_int(arguments.get("job_id"), "job_id")
    tail_lines = int(arguments.get("tail_lines") or DEFAULT_TAIL_LINES)
    text = gitlab_get(f"/projects/{project}/jobs/{job_id}/trace", raw_text=True)
    trace, truncated = tail_text(text or "", tail_lines)
    return {
        "job_id": job_id,
        "tail_lines": tail_lines,
        "truncated": truncated,
        "trace": trace or "(empty trace — job may not have started)",
    }


def build_errors(arguments: dict[str, Any]) -> dict[str, Any]:
    """One-call 'why did my build break': resolve a pipeline (given
    pipeline_id, else the latest pipeline for ref), find the FAILED jobs
    (excluding allowed-failure), and attach the tail of each job's trace.
    """
    project = resolve_project(arguments)
    ref = str(arguments.get("ref") or "").strip()
    pipeline_id = (None if arguments.get("pipeline_id") is None
                   else _as_int(arguments.get("pipeline_id"), "pipeline_id"))
    tail_lines = int(arguments.get("tail_lines") or 80)
    max_jobs = int(arguments.get("max_jobs") or 10)

    if pipeline_id is None:
        p = _latest_pipeline_obj(project, ref)
        if p is None:
            return {"message": f"no pipelines found{f' for ref {ref}' if ref else ''}"}
        pipeline = normalize_pipeline(p)
        pipeline_id = p.get("id")
    else:
        detail = gitlab_get(f"/projects/{project}/pipelines/{pipeline_id}")
        pipeline = normalize_pipeline(detail if isinstance(detail, dict) else {})

    all_jobs = _fetch_pipeline_jobs(project, pipeline_id)
    failed = [
        j for j in all_jobs
        if (j.get("status") or "").lower() == "failed" and not j.get("allow_failure")
    ]
    if not failed:
        return {
            "pipeline": pipeline,
            "failed_count": 0,
            "message": "no failing jobs — build is green (or still running). "
                       f"pipeline status: {pipeline.get('status')}",
        }

    truncated_list = len(failed) > max_jobs
    out_jobs = []
    for j in failed[:max_jobs]:
        try:
            text = gitlab_get(f"/projects/{project}/jobs/{j.get('id')}/trace", raw_text=True)
            trace, _ = tail_text(text or "", tail_lines)
        except RuntimeError as exc:
            trace = f"(could not fetch trace: {exc})"
        entry = normalize_job(j)
        entry["trace_tail"] = trace or "(empty trace)"
        out_jobs.append(entry)

    result = {
        "pipeline": pipeline,
        "failed_count": len(failed),
        "failed_jobs": out_jobs,
    }
    if truncated_list:
        result["note"] = f"showing first {max_jobs} of {len(failed)} failed jobs"
    return result


SERVER = SimpleMcpServer(
    name=configured_server_name(),
    version="0.1.0",
    tools=[
        ToolDefinition(
            name="env_status",
            description="Show configured GitLab URL, default project, and whether a token is set (never exposes the token).",
            input_schema={"type": "object", "properties": {}},
            handler=env_status,
        ),
        ToolDefinition(
            name="latest_pipeline",
            description="Latest CI pipeline for a project (optionally filtered by ref/branch). Returns id, status, ref, sha, web_url.",
            input_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "numeric id or 'group/project' path; defaults to GITLAB_PROJECT"},
                    "ref": {"type": "string", "description": "branch/tag to filter by (optional)"},
                },
            },
            handler=latest_pipeline,
        ),
        ToolDefinition(
            name="pipeline_jobs",
            description="List jobs of a pipeline. Optional `scope` (e.g. 'failed','success','running') filters by job status.",
            input_schema={
                "type": "object",
                "properties": {
                    "pipeline_id": {"type": "integer"},
                    "project": {"type": "string"},
                    "scope": {"type": "string"},
                },
                "required": ["pipeline_id"],
            },
            handler=pipeline_jobs,
        ),
        ToolDefinition(
            name="job_trace",
            description="Fetch a job's log (trace). Returns the LAST tail_lines lines (default 200) where build errors live, char-capped.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer"},
                    "project": {"type": "string"},
                    "tail_lines": {"type": "integer", "minimum": 1},
                },
                "required": ["job_id"],
            },
            handler=job_trace,
        ),
        ToolDefinition(
            name="build_errors",
            description="One call to see WHY the build broke: resolves the latest pipeline (or a given pipeline_id) for a ref, finds the failed jobs (excluding allow_failure), and attaches each failing job's trace tail. Use this right after a push when CI is red.",
            input_schema={
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "ref": {"type": "string", "description": "branch to check; defaults to the latest pipeline on any ref"},
                    "pipeline_id": {"type": "integer", "description": "check a specific pipeline instead of the latest"},
                    "tail_lines": {"type": "integer", "minimum": 1, "description": "trace tail per job (default 80)"},
                    "max_jobs": {"type": "integer", "minimum": 1, "description": "cap failing jobs inspected (default 10)"},
                },
            },
            handler=build_errors,
        ),
    ],
)


if __name__ == "__main__":
    SERVER.serve()
