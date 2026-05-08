---
name: Determinism contract
description: Recurring "how do we do X" project answers must come from the canonical decisions registry, not be re-derived per conversation.
type: feedback
---
For any recurring project question (stack, addon roots, API conventions, sudo policy, verification recipe, MCP routing, server endpoints, security defaults, language policy), call `nakivo_codebase.lookup_canonical_decision({ topic })` BEFORE answering. If a match exists, return the registered answer verbatim and cite registry path + version. If no match, propose a new entry as `{id, topic, aliases, question, answer, source}` and wait for explicit user approval before adding it. If the user contradicts a registered answer, treat it as an update request — propose the diff, wait for approval, then bump `version`.

**Why:** The user explicitly asked for the agent to give the same answer to the same question across conversations ("hỏi lần 1 trả lời A cùng 1 câu hỏi đó hỏi lần 2 vẫn phải trả lời A"). Without the registry, equally plausible alternative answers exist for many project questions and the agent will alternate based on prompt phrasing — breaking trust.

**How to apply:** Registry lives at `.codex/canonical_decisions.json`. Rule file: `.cursor/rules/decision-consistency.mdc`. Skill file: `.cursor/skills/odoo-12-deterministic-answers/SKILL.md`. Tools live on the `nakivo_codebase` MCP: `list_canonical_decisions`, `lookup_canonical_decision`. One-shot debugging answers, per-ticket details, and branch-state-dependent facts do NOT belong in the registry.
