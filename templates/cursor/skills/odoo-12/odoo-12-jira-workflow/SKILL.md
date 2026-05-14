---
name: odoo-12-jira-workflow
description: Read and search JIRA tickets through the jira_production and jira_preproduction MCP servers. Use when the user mentions a ticket key, asks for sprint/standup context, or needs requirements pulled into the conversation.
---

# Odoo 12 — JIRA Workflow

Two profiles are wired up. **Pick the right one.**

| Profile         | MCP server name      | When                                                            |
|-----------------|----------------------|-----------------------------------------------------------------|
| Production      | `jira_production`    | Live tickets, sprint/standup queries, post-merge bug triage.    |
| Pre-Production  | `jira_preproduction` | UAT verification, regression tickets, release rehearsal.        |

Base URLs and credentials live ONLY in `.codex/mcp.local.env` under `{{ENV_PREFIX}}_JIRA_PRODUCTION_*` and `{{ENV_PREFIX}}_JIRA_PREPRODUCTION_*`. The MCP starter wrappers map the profile-prefixed vars onto the generic `{{ENV_PREFIX}}_JIRA_*` vars at launch. To see the URL the current session resolved to, call `env_status` on the corresponding MCP server. Never hard-code URLs or credentials anywhere else.

## Tools (same on both servers)

| Tool                 | Purpose                                                              |
|----------------------|----------------------------------------------------------------------|
| `env_status`         | Confirm profile, base URL and that credentials are loaded.           |
| `get_issue`          | Read a normalised issue (summary, comments, attachments).            |
| `get_issue_raw`      | Same issue, full REST payload when you need custom fields.           |
| `search_issues`      | JQL search; cap with `maxResults` (default 20, max 100).             |
| `list_projects`      | Browse projects, optionally filtered by name substring.              |
| `my_assigned_issues` | Open issues assigned to the configured user (defaults exclude Done). |

## Workflow

1. **Pick the profile first.** If the user says "prod", use `jira_production`. If they say "preprod"/"UAT"/"staging JIRA", use `jira_preproduction`. If unspecified and the ticket lives in production, default to production.
2. **Start with `env_status`** the first time per session to confirm the URL is reachable.
3. **Read before writing.** Always `get_issue` the ticket the user references before drafting a change.
4. **Cite the key.** When summarising, link `[KEY](base_url/browse/KEY)`.

## Anti-patterns

- Mixing profiles in one answer ("ticket NK-100 in prod and NK-100 in preprod"). Confirm which profile you are reading.
- Pasting the full issue body. Pull the fields you need; the MCP normaliser already truncates.
- Using JIRA to bypass the codebase MCP for code questions. JIRA is for intent, the codebase MCP is for code.
