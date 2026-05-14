---
description: List all active invariants in .agent-toolkit/invariants.json with their scope, severity, and ADR references. Use to audit what the invariant_guard hook will enforce.
allowed-tools: Read, Bash
argument-hint: "[filter-substring]"
---

# /inv-list — Show registered invariants

## Goal

Print a table of every invariant the `invariant_guard` PreToolUse hook
will check against, plus a 1-line health check.

Argument: `$ARGUMENTS` — optional substring to filter `id` or
`description` (case-insensitive).

## Steps

1. `Read .agent-toolkit/invariants.json`.

2. Render a table with columns:
   `id` · `severity` · `applies_to` (first 2 globs, "+N more" if longer)
   · `description` · `ADR ref`.

   Sort: blocker first, then warn. Within severity: by `added` ascending.

3. For each invariant, **verify it still triggers**:
   - Pick the first `must_keep_regex` (or `must_keep_call` rendered as
     regex).
   - `Grep` for it across the `applies_to` globs.
   - If hit count is 0 → mark the row `⚠ STALE` (pattern not present
     anymore, invariant guards nothing).
   - If hit count >> 100 → mark `ℹ broad` (consider tightening
     `applies_to`).

4. Summary line: `N total · X blocker · Y warn · Z stale`.

5. If `$ARGUMENTS` non-empty: filter rows where the substring appears
   in `id` or `description` (case-insensitive).

## What NOT to do

- Do NOT modify `invariants.json` from this command. Read-only.
- Do NOT make claims about effectiveness — just report counts.
