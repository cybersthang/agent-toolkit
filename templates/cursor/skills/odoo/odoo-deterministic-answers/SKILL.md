---
name: odoo-deterministic-answers
description: Keep recurring project answers consistent across conversations using the canonical decisions registry. Use whenever the user asks "how do we do X in this project" or any question that has a single right answer. Works for any Odoo major version (12, 17, 18, 19, 20, future) — the registry is version-agnostic and per-project.
---

# Deterministic Answers — Single Source of Truth (version-agnostic)

The agent must answer the same project question the same way every conversation. This skill enforces that.

## Where the canonical answers live

`.codex/canonical_decisions.json` (registry, version-controlled with explicit `version` integer).

The registry seed shipped by the toolkit varies per preset
(`canonical_decisions.json` for Odoo 12, `canonical_decisions.odoo-17.json`
for Odoo 17, etc.). After install the project owner curates entries
locally — `setup.py update` never overwrites this file.

Tools (via `codebase` MCP):

| Tool                        | Purpose                                                  |
|-----------------------------|----------------------------------------------------------|
| `list_canonical_decisions`  | List all entries; filter by `topic_contains`.            |
| `lookup_canonical_decision` | Match a topic / alias / question fragment.               |

## Workflow for ANY recurring question

1. Before answering, call `lookup_canonical_decision({topic: "..."})`.
2. If `match_count >= 1`, **return the registered answer verbatim** and cite `registry_path` + `version`. Do not paraphrase, do not extend, do not "improve" it.
3. If `match_count == 0`, propose a new entry — show the proposed `{id, topic, aliases, question, answer, source}` block and ask the user to approve before adding (or suggest `/adr-add` for the WHY context).
4. If the user explicitly contradicts the registry, do **not** silently override. Treat the conflict as a registry update request.

## What counts as a "recurring question"

- Stack / language / framework versions (incl. which Odoo major).
- Where things live in the repo (addon roots, custom module location).
- API conventions (decorators, sudo policy, error types) — version-specific values live as separate entries (e.g. `api-decorators-odoo-12` vs `api-decorators-odoo-17`).
- Verification recipe.
- MCP routing.
- Server endpoints / credentials policy.
- Security defaults.

## What does **not** belong in the registry

- One-shot debugging conclusions.
- Per-ticket implementation details.
- Anything that depends on the current branch state.

## Why this matters

If the agent gives one answer today and a contradictory answer tomorrow, the user loses trust. The registry is the contract that makes the agent reproducible.

For version-specific questions (e.g. "which API decorator do we use for `create()`?"), keep separate entries per Odoo major (`api-decorators-odoo-12`, `api-decorators-odoo-17`, …) so the answer stays correct as the project upgrades.
