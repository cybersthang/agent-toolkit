---
name: Module-agnostic rules
description: Invariant rules and skills must not hard-code specific Odoo module names; discover modules at runtime via the codebase MCP.
type: feedback
---
Rules and skills under `.cursor/rules/` (alwaysApply) and `.cursor/skills/<name>/SKILL.md` must be **generic** — usable for any Odoo 12 addon under any addon root. Do not embed concrete module names like `nakivo_sale`, `oca_*`, or `web_*` into invariant rules. When a concrete module is needed, discover it at runtime via `nakivo_codebase.discover_modules` / `module_dependencies` / `find_inheritance_chain`.

**Why:** The user explicitly asked: "Nghiên cứu sâu để tạo các rules skills mcp tốt nhất cho Odoo12 dạng dùng được nhiều module không phải là fix cứng bất cứ module nào." Hard-coded module names rot the moment a module is renamed/removed and force the agent to re-learn the workspace each conversation.

**How to apply:** When writing or editing a rule/skill, scan it for module-name strings. If any appear in invariants, refactor to address them as "addon under root X" or "module discovered via the codebase MCP." Concrete module references are fine inside examples / sample snippets, but never inside the rule's mandatory clauses. The canonical registry is the only place project-specific names should appear, and only for facts that cannot be derived at runtime (server endpoints, language policy).
