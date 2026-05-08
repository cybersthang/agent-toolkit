from __future__ import annotations

import base64
import json
import os
import re
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from common import SimpleMcpServer, ToolDefinition


DEFAULT_FIELDS = (
    "summary,status,description,comment,attachment,issuelinks,created,updated,"
    "reporter,assignee,priority,issuetype,labels,components,versions,fixVersions"
)
MAX_BODY_CHARS = 120_000


def configured_profile() -> str:
    return (os.environ.get("NAKIVO_JIRA_PROFILE") or "production").strip().lower()


def configured_server_name() -> str:
    return os.environ.get("NAKIVO_JIRA_SERVER_NAME") or f"jira_{configured_profile()}"


def configured_base_url() -> str:
    base_url = os.environ.get("NAKIVO_JIRA_BASE_URL", "").strip()
    if not base_url:
        raise ValueError("NAKIVO_JIRA_BASE_URL is required")
    return base_url.rstrip("/")


def jira_credentials() -> tuple[str, str]:
    user = os.environ.get("NAKIVO_JIRA_USER", "").strip()
    password = os.environ.get("NAKIVO_JIRA_PASSWORD", "")
    if not user or not password:
        raise ValueError("NAKIVO_JIRA_USER and NAKIVO_JIRA_PASSWORD are required")
    return user, password


def auth_headers() -> dict[str, str]:
    user, password = jira_credentials()
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "User-Agent": f"codex-{configured_server_name()}-mcp/0.2",
    }


def read_response_body(response: Any) -> str:
    raw = response.read()
    content_type = response.headers.get("Content-Type", "")
    match = re.search(r"charset=([\w.-]+)", content_type)
    encoding = match.group(1) if match else "utf-8"
    return raw.decode(encoding, errors="replace")


def jira_get_json(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    url = configured_base_url() + path
    if params:
        url += "?" + urlencode(params)
    request = Request(url, headers=auth_headers())
    try:
        with urlopen(request, timeout=60) as response:
            body = read_response_body(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"JIRA HTTP {exc.code}: {body[:1000]}") from exc
    except URLError as exc:
        raise RuntimeError(f"JIRA connection failed: {exc.reason}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JIRA returned non-JSON response: {body[:1000]}") from exc


def strip_wiki_markup(value: Any) -> str:
    if not value:
        return ""
    text = unescape(str(value))
    text = re.sub(r"!([^!\n]+)!", r"[attachment: \1]", text)
    text = re.sub(r"\[([^|\]]+)\|([^\]]+)\]", r"\1 <\2>", text)
    text = re.sub(r"\{[^{}\n]+\}", "", text)
    return text.strip()


def shorten(value: Any, limit: int = MAX_BODY_CHARS) -> str:
    text = strip_wiki_markup(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def normalize_user(value: Any) -> dict[str, Any] | None:
    if not value:
        return None
    return {
        "name": value.get("name") or value.get("key"),
        "displayName": value.get("displayName"),
        "emailAddress": value.get("emailAddress"),
    }


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    comments = ((fields.get("comment") or {}).get("comments")) or []
    attachments = fields.get("attachment") or []

    return {
        "key": issue.get("key"),
        "id": issue.get("id"),
        "self": issue.get("self"),
        "summary": fields.get("summary"),
        "issueType": (fields.get("issuetype") or {}).get("name"),
        "status": (fields.get("status") or {}).get("name"),
        "priority": (fields.get("priority") or {}).get("name"),
        "reporter": normalize_user(fields.get("reporter")),
        "assignee": normalize_user(fields.get("assignee")),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "components": [item.get("name") for item in fields.get("components") or []],
        "labels": fields.get("labels") or [],
        "description": shorten(fields.get("description")),
        "comments": [
            {
                "id": comment.get("id"),
                "author": normalize_user(comment.get("author")),
                "created": comment.get("created"),
                "updated": comment.get("updated"),
                "body": shorten(comment.get("body")),
            }
            for comment in comments
        ],
        "attachments": [
            {
                "id": item.get("id"),
                "filename": item.get("filename"),
                "mimeType": item.get("mimeType"),
                "size": item.get("size"),
                "content": item.get("content"),
            }
            for item in attachments
        ],
        "issueLinks": fields.get("issuelinks") or [],
    }


def env_status(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": configured_profile(),
        "server_name": configured_server_name(),
        "base_url": os.environ.get("NAKIVO_JIRA_BASE_URL", ""),
        "user": os.environ.get("NAKIVO_JIRA_USER", ""),
        "password_configured": bool(os.environ.get("NAKIVO_JIRA_PASSWORD")),
    }


def list_projects(arguments: dict[str, Any]) -> dict[str, Any]:
    payload = jira_get_json("/rest/api/2/project")
    projects = [
        {
            "key": item.get("key"),
            "name": item.get("name"),
            "id": item.get("id"),
        }
        for item in (payload if isinstance(payload, list) else [])
    ]
    name_contains = str(arguments.get("name_contains", "")).strip().lower()
    if name_contains:
        projects = [p for p in projects if name_contains in (p["name"] or "").lower()]
    return {"count": len(projects), "projects": projects}


def my_assigned_issues(arguments: dict[str, Any]) -> dict[str, Any]:
    user, _ = jira_credentials()
    max_results = max(1, min(int(arguments.get("maxResults", 25)), 100))
    status_filter = str(arguments.get("status_not", "Done,Closed,Resolved")).strip()
    jql = f'assignee = "{user}"'
    if status_filter:
        jql += f' AND status not in ({status_filter})'
    jql += " ORDER BY updated DESC"
    return search_issues({"jql": jql, "maxResults": max_results})


def get_issue(arguments: dict[str, Any]) -> dict[str, Any]:
    key = str(arguments.get("key", "")).strip()
    if not key:
        raise ValueError("key is required")
    fields = str(arguments.get("fields") or DEFAULT_FIELDS)
    issue = jira_get_json(f"/rest/api/2/issue/{quote(key)}", {"fields": fields})
    return normalize_issue(issue)


def get_issue_raw(arguments: dict[str, Any]) -> dict[str, Any]:
    key = str(arguments.get("key", "")).strip()
    if not key:
        raise ValueError("key is required")
    fields = str(arguments.get("fields") or DEFAULT_FIELDS)
    return jira_get_json(f"/rest/api/2/issue/{quote(key)}", {"fields": fields})


def search_issues(arguments: dict[str, Any]) -> dict[str, Any]:
    jql = str(arguments.get("jql", "")).strip()
    if not jql:
        raise ValueError("jql is required")
    max_results = max(1, min(int(arguments.get("maxResults", 20)), 100))
    fields = str(arguments.get("fields") or "summary,status,assignee,updated")
    payload = jira_get_json(
        "/rest/api/2/search",
        {
            "jql": jql,
            "fields": fields,
            "maxResults": str(max_results),
        },
    )
    return {
        "total": payload.get("total"),
        "startAt": payload.get("startAt"),
        "maxResults": payload.get("maxResults"),
        "issues": [normalize_issue(issue) for issue in payload.get("issues") or []],
    }


SERVER = SimpleMcpServer(
    name=configured_server_name(),
    version="0.2.0",
    tools=[
        ToolDefinition(
            name="env_status",
            description="Show configured JIRA profile, URL and username without exposing the password.",
            input_schema={"type": "object", "properties": {}},
            handler=env_status,
        ),
        ToolDefinition(
            name="get_issue",
            description="Read a JIRA issue and return normalized fields, comments, and attachments.",
            input_schema={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "fields": {"type": "string"},
                },
                "required": ["key"],
            },
            handler=get_issue,
        ),
        ToolDefinition(
            name="get_issue_raw",
            description="Read a JIRA issue and return the raw REST API JSON.",
            input_schema={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "fields": {"type": "string"},
                },
                "required": ["key"],
            },
            handler=get_issue_raw,
        ),
        ToolDefinition(
            name="search_issues",
            description="Search JIRA issues using JQL.",
            input_schema={
                "type": "object",
                "properties": {
                    "jql": {"type": "string"},
                    "fields": {"type": "string"},
                    "maxResults": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "required": ["jql"],
            },
            handler=search_issues,
        ),
        ToolDefinition(
            name="list_projects",
            description="List JIRA projects, optionally filtered by case-insensitive name substring.",
            input_schema={
                "type": "object",
                "properties": {"name_contains": {"type": "string"}},
            },
            handler=list_projects,
        ),
        ToolDefinition(
            name="my_assigned_issues",
            description="Search issues assigned to the configured JIRA user, excluding closed statuses by default.",
            input_schema={
                "type": "object",
                "properties": {
                    "maxResults": {"type": "integer", "minimum": 1, "maximum": 100},
                    "status_not": {"type": "string"},
                },
            },
            handler=my_assigned_issues,
        ),
    ],
)


if __name__ == "__main__":
    SERVER.serve()
