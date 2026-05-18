---
description: Run an exhaustive single-pass code review on the requested scope (module / PR / file). Reads .codex/audit_findings_*_locked.md FIRST to honor existing counts, then surfaces NEW findings as a delta. Uses code-review + odoo-code-review + doubt-driven-review skills. Forces Proof line + Doubt-pass line per finding.
allowed-tools: Read, Edit, Glob, Grep, Bash
argument-hint: "[scope: module name | PR number | file path]"
---

# /review — Exhaustive code review with lock-file precedence

## Goal

Produce an exhaustive review with **stable count** across runs on the same
code base. Avoid the failure mode where a fresh review counts X
findings, the next run counts Y, and dev loses trust in the audit.

Argument: `$ARGUMENTS` — scope (one of: module name like `<your_module>`,
PR `<TICKET-NNNN>`, file path, or empty for "current branch diff").

## Step-by-step

1. **Lock-file precedence (ALWAYS first)**
   - `Glob .codex/audit_findings*_locked.md` to find existing audit files.
   - If a lock file matches the scope (e.g. `audit_findings_<module>_locked.md`):
     - `Read` the file. Cite the recorded count VERBATIM:
       `<N> BLOCKER + <M> MEDIUM + <K> LOW = <total> (REV-<n>)`.
     - Only propose a different count when:
       - Code in scope changed since the lock timestamp (`git log` after that date).
       - User explicitly requests a re-audit.
       - Reproducible proof contradicts a specific entry.
     - Any count change updates the lock file's revision header with a
       one-paragraph rationale. **Never silently rewrite.**
   - If no lock file exists for this scope, proceed to a fresh exhaustive
     pass and propose locking the result at the end.

2. **Open the review skills** (in order, no parallel):
   - `code-review` — methodology, severity rubric, proof contract.
   - Stack overlay: `odoo-code-review` for Odoo modules; pick the
     overlay matching the project stack.
   - `doubt-driven-review` — per-finding adversarial check.

3. **Discovery — use codebase MCP, not blind grep**:
   - `mcp__codebase__workspace_status` — confirm scope.
   - `mcp__codebase__discover_modules` if scope is a module.
   - `mcp__codebase__read_manifest` for dependencies.
   - `mcp__codebase__find_inheritance_chain` for ORM extensions.
   - `mcp__codebase__list_test_targets` to know what tests exist.
   - `Grep` / `Read` only for narrow follow-ups after MCP discovery.

4. **Run through ALL dimensions** (from `code-review` SKILL.md):
   - Data schema / persisted JSON
   - SQL touchpoints
   - Background workers / cron
   - HTTP controllers / API
   - ORM hooks / monkey-patch
   - Security / auth / CSRF
   - Test coverage gaps
   - Performance hotspots
   - Plus stack-specific dimensions from overlay
   For each dimension: enumerate findings at every severity. If zero,
   write `none — verified by <evidence>`. Silent gaps let Mediums and
   Lows escape across sessions.

5. **Per-finding output contract** (from intent_router):
   ```
   ### <ID> — <one-line title>
   **Severity**: BLOCKER / MEDIUM / LOW
   **Proof**: `path:line` cite + tool used (`Read`, `Grep`,
     `mcp__postgres__query_readonly`, `mcp__realdata_test__eval_orm_expression`).
     Claims without a tool reference are rejected by evidence-audit hook.
   **Doubt-pass**: strongest doubt + how refuted (or "unknown — user question").
   **Falsification probe** (BLOCKER + MEDIUM only): a real-data check
     that would flip ACTUAL if the finding is wrong (e.g. inject
     time.sleep, query a count, run a smoke test).
   **Fix sketch**: one-paragraph proposed remediation.
   ```

6. **Final count table**:
   ```
   | Severity | Count | Delta from REV-<n> lock |
   |----------|-------|--------------------------|
   | BLOCKER  | X     | +N / -M / =              |
   | MEDIUM   | Y     | +N / -M / =              |
   | LOW      | Z     | +N / -M / =              |
   ```

7. **Lock proposal**:
   - If lock file exists and counts unchanged → confirm REV-<n> still
     valid, no update needed.
   - If counts changed → propose a REV-<n+1> entry with one-paragraph
     rationale. STOP for user approval.
   - If no lock file yet → propose creating
     `.codex/audit_findings_<scope>_locked.md` with the new counts.
     STOP for user approval.

## Refuse / clarify when

- Scope is "review everything" with no narrower target. Ask the user
  to pick a module / PR / file — exhaustive review on the whole repo
  is not actionable.
- Lock file exists but user explicitly asks for "fresh review,
  ignore lock" — confirm they understand counts may diverge, then
  proceed.
- The agent has no MCP access (codebase MCP not running). Run
  `mcp__codebase__workspace_status` first; if it errors, ask user to
  start the server before proceeding.

## What NOT to do

- Do NOT silently rewrite a locked count. ADR-style: append a new
  revision header explaining the change.
- Do NOT make a finding without a `Proof:` line — evidence-audit
  hook will block the response.
- Do NOT split one finding across two severities to inflate counts.
  If a finding has both blocker and non-blocker effects, list as the
  higher severity with the secondary effect mentioned in Doubt-pass.
- Do NOT skip the `Doubt-pass:` line. The strongest internal doubt
  is the cheapest verification — bypassing it is how false-positives
  reach the user.

## Stack portability

This command is stack-agnostic:
- Lock-file location (`.codex/audit_findings_*_locked.md`) is a
  project-level convention; same pattern works for non-Odoo projects.
- Skill overlays (`<stack>-code-review`) are loaded dynamically; for
  Django/Rails/etc., swap to the corresponding overlay.
- MCP tool names are referenced by string; project-specific MCPs
  (postgres / realdata_test) work the same way as Odoo's.
