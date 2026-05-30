<!--
v0.12.0 — Copy to `.github/PULL_REQUEST_TEMPLATE.md` if your project uses
GitHub PRs. Adapts agent-toolkit's anti-bloat rules into a 3-tick checklist
the reviewer (or AI agent) must fill before merge.
-->

## What changed

<!-- 1-3 sentences. Why now? What user-facing behaviour shifts? -->

## Reuse + complexity discipline (v0.12.0 toolkit rules)

- [ ] **Grep Before Write** — Before adding any new top-level `def` / `class`, I grepped the workspace for similar identifiers and cited findings in the spec or commit body (or confirmed `Searched: <pattern> → 0 hits`).
- [ ] **LOC delta** — This PR adds ≤ 200 LOC per file (excluding tests / migrations). If over, the deviation is justified in the description below.
- [ ] **Complexity** — No new function has loop nest ≥ 3, body ≥ 60 LOC, or branch count ≥ 12 without a one-line Big-O / trade-off comment above the definition.

## Reuse Metric (paste from `.agent-toolkit/specs/<slug>.md` `reuse_targets:`)

| Existing symbol | How this PR reuses it |
|---|---|
| `<path>:<fn>` | <called / extended with parameter X / wrapped> |
| _(none — confirmed via grep)_ | _(state the searches that returned 0 hits)_ |

## Test evidence

- [ ] `pytest tests/` green (cite added test files).
- [ ] If feature-scope: `acceptance_evals` defined in spec + `/verify` PASS attached.

## Out of scope (will not be done in this PR)

<!-- Honest list of follow-ups deferred. Empty = none deferred. -->

---

agent-toolkit v0.12.0+ — reuse + LOC + complexity gates documented in `templates/cursor/rules/_common/`.
