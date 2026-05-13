---
name: odoo-12-deterministic-answers
description: Keep recurring project answers consistent across conversations using the canonical decisions registry. Use whenever the user asks "how do we do X in this project" or any question that has a single right answer.
---

# Deterministic Answers — Single Source of Truth

The agent must answer the same project question the same way every conversation. This skill enforces that.

## Where the canonical answers live

`.codex/canonical_decisions.json` (registry, version-controlled with explicit `version` integer).

Tools (via `nakivo_codebase` MCP):

| Tool                        | Purpose                                                  |
|-----------------------------|----------------------------------------------------------|
| `list_canonical_decisions`  | List all entries; filter by `topic_contains`.            |
| `lookup_canonical_decision` | Match a topic / alias / question fragment.               |

## Workflow for ANY recurring question

1. Before answering, call `lookup_canonical_decision({topic: "..."}).
2. If `match_count >= 1`, **return the registered answer verbatim** and cite `registry_path` + `version`. Do not paraphrase, do not extend, do not "improve" it.
3. If `match_count == 0`, propose a new entry — show the proposed `{id, topic, aliases, question, answer, source}` block and ask the user to approve before adding.
4. If the user explicitly contradicts the registry, do **not** silently override. Treat the conflict as a registry update request.

## What counts as a "recurring question"

- Stack / language / framework versions.
- Where things live in the repo.
- API conventions (decorators, sudo policy, error types).
- Verification recipe.
- MCP routing.
- Server endpoints / credentials policy.
- Security defaults.

## What does **not** belong in the registry

- One-shot debugging conclusions.
- Per-ticket implementation details.
- Anything that depends on the current branch state.

## Why this matters

If the agent answers "we use `@api.multi`" today and "we use `@api.one`" tomorrow, the user loses trust. The registry is the contract that makes the agent reproducible.
