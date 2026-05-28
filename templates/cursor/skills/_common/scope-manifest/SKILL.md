---
name: scope-manifest
description: Explains the v0.23.0 scope-completeness gate (R9) — how the agent's full request scope is enumerated into a mechanical manifest (`.agent-toolkit/.scope_manifest.json`) derived from a STRUCTURED artifact (tasks.md > acceptance_evals > TodoWrite>=3), and how to resolve manifest items before claiming done/full. Read this when a Stop is BLOCKed by scope_completeness_gate, or when starting autonomous multi-item work so you self-audit completeness proactively instead of waiting for DEV to ask "đã làm đủ chưa".
---

# Scope manifest — proactive completeness self-audit (R9)

> Sibling of the gap-completeness gate. The **gap gate** tracks gaps you
> surface MID-WORK (reactive). This **scope gate** tracks the FULL request
> scope declared UPFRONT (proactive) so partial completion cannot pass
> silently.

## Why this exists

Root cause (session 2026-05-27): DEV said "làm full" (fix ALL reviewer
findings — a multi-item scope). The agent did 7/14, left 4 partial + 3
deferred, and claimed substantial progress. DEV had to ask "đã làm đầy đủ
chưa" before the agent audited — reactive, not proactive. The gap gate
could not catch this because un-done items never registered as a `G<N>`
gap. The scope gate closes that hole mechanically.

## How the manifest is built (NOT from your prompt)

The gate derives the manifest from the **highest-priority structured
source** available — it NEVER parses DEV prompt keywords like "tất cả" /
"full" (explicit anti-requirement, because in autonomous work the scope is
the artifact content, not the DEV's words):

1. **`tasks.md`** (Spec Kit) — each `## T<N>` header is one manifest item.
   The task's recorded status (`passed` → done, `skipped` → deferred, else
   pending) maps directly to the item status (no separate sync layer).
2. **`acceptance_evals`** (spec frontmatter) — each eval id is one item.
3. **Ad-hoc TodoWrite ≥ 3** — when there is no tasks.md and you maintain a
   TodoWrite list of ≥ `min_items` (default 3) items, each todo becomes one
   item (`completed` → done, else pending). Sub-agent batches do NOT
   auto-trigger — only TodoWrite.

The manifest lives at `.agent-toolkit/.scope_manifest.json` and its
lifecycle mirrors autonomy: created on autonomy start, cleared on autonomy
off / `/verify` pass.

## What this means for you (the agent)

- **Doing autonomous multi-item work?** Keep a TodoWrite list of every item
  in scope. That list *is* your self-audit checklist — the gate reads it.
- **Before claiming done / full / "hoàn tất"**, every manifest item must be
  resolved. If you claim completion with a `pending` item, the Stop is
  BLOCKed and the incomplete items are listed back to you.

## Resolving manifest items (3 tiers — mirror gap gate)

1. **Finish it** — actually complete the work. For Spec Kit, mark the task
   `passed` in tasks.md; for ad-hoc, emit `scope-done: S<N>`.
2. **`scope-defer: S<N> <reason ≥ 8 chars>`** — intentional punt with a
   reason (logged on the item).
3. **`scope-cant: S<N> <reason>`** — escalate to DEV (e.g. needs prod
   access / a decision you can't make).

Whole-gate single-shot bypass (DEV-only): DEV types
`bypass-scope-gate: <reason ≥ 8 chars>` in the next prompt.

## Enforce mode

Default `block` (per `feedback_exhaustive_analysis`, matches the gap gate).
Tune via `.agent-toolkit/enforce_mode.json` `per_hook.scope_completeness_gate`
(`warn` / `off`) and activation via `.agent-toolkit/scope_gate.json`
(`enabled`, `min_items`).

## Anti-rationalizations

| Temptation | Counter |
|---|---|
| "I did most of it, that's basically done." | Most-of-it ≠ done. Either finish the rest or `scope-defer`/`scope-cant` each remaining item with a reason. |
| "DEV didn't list these explicitly." | The manifest comes from the artifact (tasks.md / evals / your own TodoWrite), not DEV's phrasing. If it's in scope, it's an item. |
| "I'll mention the gaps in my summary." | Mentioning ≠ resolving. The gate needs a marker per item, not prose. |
