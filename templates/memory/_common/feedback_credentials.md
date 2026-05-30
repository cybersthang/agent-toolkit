---
name: Credentials policy
description: Real credentials live only in .codex/mcp.local.env (gitignored); committed config and example files use placeholders only.
type: feedback
---
Real JIRA / Postgres / Odoo credentials must live ONLY in `.codex/mcp.local.env` (gitignored at `.gitignore` line 10). Committed files (`mcp.local.env.example`, `config.toml.example`, any `.py` server, any `.md` rule/skill) must contain placeholders or env-var names — never real passwords.

**Why:** When the user provides credentials in chat, the natural temptation is to inline them into start scripts so things "just work." That leaks them into git history and Cursor cloud sync. The wrappers (`start_*_mcp.py`) are designed to load from the env file at startup precisely to keep secrets out of source.

**How to apply:** Each new MCP server gets a profile-specific env-var prefix (e.g. `{{ENV_PREFIX}}_JIRA_PRODUCTION_*`, `{{ENV_PREFIX}}_JIRA_PREPRODUCTION_*`). The wrapper maps the prefix onto the generic `{{ENV_PREFIX}}_JIRA_*` vars before re-execing the server. To add a new profile: add the prefix block to `.codex/mcp.local.env` (real values) and `.codex/mcp.local.env.example` (placeholders), then create a wrapper modeled on `start_jira_preproduction_mcp.py`. Confirm `.gitignore` already covers the env file before writing real values.
