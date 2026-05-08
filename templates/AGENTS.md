# {{PROJECT_NAME}} Agent Instructions

> Installed by **agent-toolkit** with preset `{{PRESET_NAME}}`.
> To refresh from latest toolkit: `python <toolkit>/setup.py update {{WORKSPACE_ROOT}}`.

This file is the entry-point for any AI coding agent in this workspace.
The heavy material lives in:

- `.cursor/rules/*.mdc` (always-apply project rules)
- `.cursor/skills/*` (focused skills)
- `.codex/canonical_decisions.json` (single source of truth for recurring answers)
- `.codex/audit_findings_locked.md` (locked audit findings, if present)

## Workspace

- Root: `{{WORKSPACE_ROOT}}`
- Stack: {{STACK_LABEL}}
- Language: {{STACK_LANGUAGE}} {{STACK_LANGUAGE_VERSION}}
- Python interpreter: `{{PYTHON_BIN}}`
- Default database: `{{DEFAULT_DB}}`
- Default reply language: {{RESPONSE_LANGUAGE}}

## Addon / Code roots

{{ADDON_ROOTS}}

## MCP Servers

{{MCP_SERVERS}}

Credentials live in `.codex/mcp.local.env` (gitignored). Configure via the
`.codex/mcp.local.env.example` template.

## Operating Principles

1. **Think before coding.** State assumptions, surface tradeoffs.
2. **Simplicity first.** Smallest solution that satisfies the request.
3. **Surgical changes.** Every changed line traces to the user's request.
4. **Goal-driven execution.** Define success criteria up front, verify against them.
5. **MCP before file reads.** Use the right MCP server for discovery and DB lookups.
6. **Canonical answers, not guesses.** For recurring questions, call
   `codebase.lookup_canonical_decision` first.

## Hard rules

- Do not edit committed config files to add credentials.
- Do not invent answers for recurring questions; lookup or propose registry update.
- Do not add features outside the request without asking first.
