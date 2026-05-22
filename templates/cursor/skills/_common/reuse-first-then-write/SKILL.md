---
name: reuse-first-then-write
description: 3-step probe workflow to prevent silent function duplication. Open BEFORE writing any new function/class/helper. Pairs with Reuse Probe hook (PreToolUse) and `reuse_targets` spec field.
license: MIT
---

# Reuse First, Then Write

**Purpose**: kill the #1 AI-coding bloat pattern — same logic re-implemented under a different name because the agent didn't look first.

**Tradeoff**: 5 extra seconds of grep up-front vs. unbounded duplication debt later.

## The 3-step probe

### Step 1 — Grep the workspace

Search for the identifier you are about to write AND 1–2 close variants. Use these patterns (Python example):

```
^def <name>\b
^def .*<root_word>.*\b
^class <Name>\b
```

For other languages, swap the prefix:
- JS/TS: `^(function|const|export function) <name>`
- Go: `^func( \(.*\))? <name>`
- Java: `(public|private|protected).*<name>\s*\(`

Use the codebase MCP (`search_text`) if available; fall back to `Grep`.

### Step 2 — Cite findings in your response

ONE of:

- **Hit**: `Found existing: <path>:<line> — <one-line of what it does>`
- **Miss**: `Searched: <pattern> → 0 hits`

This citation is mandatory. It gives the reviewer (and the post-Edit audit hook) a paper trail.

### Step 3 — Decide: reuse / extend / rewrite

Pick ONE with a one-line reason:

| Decision | When | Action |
|---|---|---|
| **Reuse** | Existing function matches your need (≥ 80%) | Call it directly. Stop. No new code. |
| **Extend** | Existing covers core case; you need a variant | Add a parameter / overload to the existing fn, don't fork. |
| **Rewrite** | Existing is in wrong layer / wrong contract / dead | Write new + delete (or mark deprecate) the old. State why old is wrong. |

If you cannot pick one, you have not searched deeply enough — go back to Step 1.

## Worked example (Python, fictional `<module>`)

User asks: *"add a helper that parses an ISO-8601 date string into a datetime"*

```
Step 1 — grep workspace:
  ^def parse_iso  → 0 hits
  ^def .*iso.*date → 1 hit at <module>/utils.py:42 `def iso_date_to_dt(s)`
  ^def .*parse.*date → 2 hits (both look domain-specific, not generic)

Step 2 — cite:
  Found existing: <module>/utils.py:42 — `iso_date_to_dt(s)`, accepts
  ISO-8601 string + returns naive datetime. No timezone handling.

Step 3 — decide:
  REUSE. Function already does exactly what's needed. Caller can
  add timezone afterwards if required. No new code.
```

## When the rule does NOT apply

- The new code is a **test fixture** (tests can duplicate intentionally for isolation).
- The new code is in a **migration / one-shot script** (delete after run).
- The user explicitly asked for a fresh implementation (e.g. "rewrite parse_iso, don't reuse the old one").

In all 3 cases, still **state** the rule is being skipped + why.

## Anti-patterns

| Anti-pattern | Why it fails |
|---|---|
| "I'll grep later when reviewing" | The new function is already written + already shaped wrong. Search BEFORE the cursor moves. |
| Grep only for exact match | Misses 80% of cases. Always also grep the root word (`iso`, `date`, `parse`) — that's where look-alikes hide. |
| Cite "no time to search" | The hook will fire anyway. Five seconds of grep < five minutes of un-reviewing a duplicate function. |
| Trust the AI's memory of the codebase | Memory drifts. Grep is ground truth. Re-grep every session. |

## Sibling skills + enforcement

- `karpathy-guidelines` — §"Grep Before Write" is the rule; this skill is the procedure.
- **Reuse Probe hook** (`templates/claude/hooks/reuse_probe.py`, PreToolUse on Write/Edit) — auto-greps for `^def <name>` on `.py` writes and emits warn with citations. Soft signal, not block.
- **`reuse_targets` spec frontmatter** — declarative list of functions/classes the spec INTENDS to reuse. Empty list triggers verify-lint advisory (unless `feature_kind: infrastructure`).
- **`code-review` skill dimension 17** — Function-duplication scan at PR-review time as a backstop.

The 4-layer chain (rule → skill → hook → review) means duplication has to slip past all four to land — much narrower window than relying on rule-following alone.
