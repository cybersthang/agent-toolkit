---
name: User profile
description: Developer running the {{PROJECT_NAME}} workspace; expects {{RESPONSE_LANGUAGE}} replies and Karpathy-style execution.
type: user
---
- Workspace: `{{WORKSPACE_ROOT}}` — {{STACK_LABEL}}, Python {{STACK_LANGUAGE_VERSION}}.
- Reply language: {{RESPONSE_LANGUAGE}} unless explicitly asked otherwise. Code/comments stay in English.
- Cares about: deterministic answers, module-agnostic rules, MCP-first workflow, Karpathy-style discipline (think before coding, smallest change, surgical edits, goal-driven verification).
- Project enforces invariants mechanically via `.claude/hooks/invariant_guard.py` reading `.agent-toolkit/invariants.json`. Memory ≠ enforcement; durable rules live there.

> Add per-developer details (name, email, expertise areas, preferences)
> via `/remember` once the project is in active use — this file is the
> portable starter; updates accumulate in `~/.claude/projects/<encoded>/memory/`.
