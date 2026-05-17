---
name: verify-feature
description: Vibe-flow Phase 5 — reconcile the coded feature against the original spec using real data. Each User Story → 1 probe via MCP → Gap/Blocker/Pass table. Auto-triggers when the agent self-detects tasks PASS, or when the user types `/verify`. Open this skill WHEN: a spec at status=implementing is moving to done; the user says "verify", "check against real data", "any gaps", "match the requirements yet".
---

# Verify Feature — Vibe-flow Phase 5

> Purpose: "compile passes + mock tests pass" does NOT mean "feature meets
> the requirement". Verify is the only gatekeeper that checks "does the
> feature actually behave on real data the way the spec promised".

## When to apply

- All tasks in the spec are PASS → the agent auto-invokes.
- The user types `/verify [slug]` ad-hoc.
- The user says "check the real data for <X>", "verify <X> has any gaps",
  "does it match the requirements", "any blocker".

## When to SKIP

- Spec status=`draft` or `grilled` (not yet coded) → refuse, suggest `/go` first.
- Spec has no User Stories (the spec is poorly written) → refuse, suggest `/plan`.
- The MCP server is not reachable → fall back to manual smoke test.

## 8-step procedure

### Step 1 — Load + parse the spec

Read `.agent-toolkit/specs/<slug>.md`. Extract:
- User Stories (numbered list).
- Implementation Decisions (identify which model / table / endpoint was coded).
- Testing Strategy (pre-designed probes if any).
- Out of Scope (stories NOT to verify — skip with a note).

### Step 1.5 — Read `acceptance_evals` block in frontmatter FIRST (REQUIRED)

If the spec frontmatter has the `acceptance_evals:` key (produced by
`/eval-define` or `/eval-backfill`), the agent **MUST**:

1. Load each entry in the block.
2. Map each entry → User Story (via the `story:` field).
3. Re-use the defined probe; do NOT re-design from scratch. This is the
   machine-readable contract; re-designing defeats the eval-driven workflow.
4. For entries with `smoke: verified` + `smoke_result.executed_at`:
   - If `executed_at` < 5 minutes ago → may re-use; mark `(cached)` in the Verify Report.
   - If > 5 minutes → MUST re-run the probe (verify is point-in-time, not
     a history lookup).
5. For entries with `smoke: pending` → run now; update `smoke: verified` +
   `smoke_result`.

Stories without a corresponding acceptance_eval → fall back to Step 2 (ad-hoc
probe design).

### Step 1.7 — Locate the observable BEFORE designing the probe (REQUIRED)

> Principle: "measure Y where Y actually lives, not where it is convenient to query".

Before writing SQL/Bash, the agent must answer: **where does Y for this Story live?**

| Layer | When | Right probe tool |
|---|---|---|
| **Raw DB column / persisted JSON** | Spec says "X is stored in field Y" | `postgres_read_query` |
| **In-memory mutation at read time** | Spec / code comment says "in-place attach", "computed at read", "memoize at endpoint" | HTTP probe to the endpoint (curl with session cookie / Playwright authed) — do NOT query the DB |
| **JS browser state** | Field is sent/rendered by JS, not persisted server-side | Playwright `browser_evaluate` reading DOM / `performance.getEntries()` |
| **Empirical behaviour** | Runtime claim (BLOCK/ASYNC/cached/idempotent/...) | Apply `[[claim-falsification]]` skill — perturb test |
| **Log file** | Side-effect log, not persisted in DB | `Bash grep <log>` |
| **External system** | Jira, Slack, etc. | Corresponding MCP |

**Bug pattern (abstract)**: probing a raw DB column for a field `X` that is
computed on-the-fly at endpoint-read time (in-memory mutation, no UPDATE
ever runs) → field is NULL on 100% of rows → Verify treats NULL = bug →
false BLOCKER.

Code-side symptom: search for a classifier method whose docstring says
"in-place attach" / "computed at read" / "memoize at endpoint"; absence of
`cr.execute('UPDATE … SET X')` in the write path. Right layer for the probe:
HTTP call to the endpoint (with auth cookie / `Playwright authed`), read
`X` from the JSON response.

### Step 1.8 — Classifier-shape detection (REQUIRED for classification features)

Before designing User-Story probes, check the spec frontmatter:

- If `feature_kind: classification` is set OR the implementation contains
  per-row tag/label assignments (grep for `role = '`, `tag = '`,
  `severity = '`, etc.) → the feature is a CLASSIFIER, not a single-shot
  predicate.
- One acceptance_eval per User Story is NOT enough coverage. The spec
  authors enumerated the cases they thought of; the long tail is
  unverified.
- Invoke `[[classifier-output-audit]]` BEFORE Step 2. Its findings
  become an extra section in the Verify Report (between User Stories
  and Gaps).

The audit may surface mismatches the User Stories don't cover; treat
each mismatch group like a GAP/BLOCKER with the proposed fix already
written (typically "add signal s_k to path A" or "re-route inputs of
kind K to path B").

### Step 2 — Design a probe per User Story

3 probe types (pick the right one for the story):

#### (a) ORM probe — default

Use for stories about model behaviour, computed field, constraint, workflow.

```python
# Probe template (replace <model>, <date_field>, <method>):
self.env['<model>'].search([
    ('<date_field>', '>=', '<from>'),
    ('<date_field>', '<', '<to>')
]).<method>()
# Expected: <assertion-on-return-shape>
```

Run via MCP `mcp__<stack>-<version>__run_python_tests`.

#### (b) Postgres probe — for data integrity

Use for stories about count, JOIN, security rule, orphan record.

```sql
-- Probe template (replace <table>, <field>, <expected_groups>)
SELECT m.id, m.name, array_agg(g.name) AS groups
FROM <table> m
LEFT JOIN <link_table> mg ON mg.<menu_fk> = m.id
LEFT JOIN <group_table> g ON g.id = mg.<group_fk>
WHERE m.<filter_field> = '<expected_value>'
GROUP BY m.id, m.name;
-- Expected: groups CONTAINS '<allowed>', NOT CONTAINS '<denied>'.
```

Run via MCP `mcp__<stack>-<version>__postgres_read_query`.

#### (c) HTTP probe — for controller / portal

```bash
curl -s -X POST http://<host>:<port>/<route> \
     -H "Content-Type: application/json" \
     -d '{"<field>":"<value>"}' | jq .
# Expected: <assertion-on-json-shape>
```

### Step 3 — Run probes in PARALLEL (REQUIRED, not just "avoid serial")

**Hard requirement**: all probes for one `/verify` invocation must travel in
**ONE assistant message**, as N parallel tool_use blocks. Forbidden:

- Send probe 1 → wait for response → send probe 2 (implicit serial).
- Send some probes in this message, others in the next message.

Reason: verify captures one point-in-time snapshot. If probe 1 and probe 5
are 10 s apart in wall-clock, the data has changed (cron, another user
logged in, new log written) — diffs between them no longer mean "same
state". The `evidence_audit` Stop hook has an enforcement rule (ADR-007):
reject the Verify Report when probe count > 1 and spread > 3 s wall-clock.

**Single exception**: a probe that depends on the output of the previous
probe (e.g. probe 2 needs `tab_id` from probe 1) — write `(sequential —
depends on #N)` in the Verify Report.

When probes are re-used from `acceptance_evals` (Step 1.5) and the
`smoke_result` is < 5 minutes old, citing is allowed — note `(cached from
<ISO>)` so the user sees the source.

### Step 4 — Diff actual vs expected → classify

Each probe → one of 3 statuses:

| Status | When |
|---|---|
| ✅ **PASS** | Actual = Expected (or within defined tolerance). |
| 🟡 **GAP** | Actual ≠ Expected but does NOT break the flow (config missing, default wrong, cosmetic). |
| 🔴 **BLOCKER** | The feature does NOT work: exception, empty return, wrong data type, wrong security. |

Distinction GAP vs BLOCKER:
- BLOCKER: if the user deployed today, the end-user hits the problem immediately → unusable.
- GAP: usable, but a part diverges from the spec → fixable in a follow-up PR.

### Step 5 — Root cause assumption per GAP/BLOCKER

Each GAP/BLOCKER must have:
- One line **Root cause [assumption]** — best guess.
- One line **Proposed fix** — code-level change.

Tag `[assumption]` so `evidence_audit` does not reject — verify cannot be
100% sure of the cause without deep debugging.

### Step 6 — Emit the Verify Report (fixed format)

```markdown
## Verify Report — <slug> · <ISO datetime>
Spec: .agent-toolkit/specs/<slug>.md · status before: implementing

| # | User Story (short) | Probe | Expected | Actual | Status |
|---|---|---|---|---|---|
| 1 | ... | ORM: ... | ... | ... | ✅ / 🟡 / 🔴 |
...

### Gaps / Blockers
🔴 #1 BLOCKER: <title>
  Root cause [assumption]: ...
  Proposed fix: ...

🟡 #3 GAP: <title>
  Root cause [assumption]: ...
  Proposed fix: ...

### Summary
- Total stories: N
- ✅ PASS: X (Y%)
- 🟡 GAP: Z
- 🔴 BLOCKER: W
- **Verdict**: READY / NEEDS FIX / NOT READY (≥1 BLOCKER)

→ Spec status: <verified | gaps-found>
→ Next steps: ...
```

### Step 7 — Update spec + autonomy state

Edit spec frontmatter:
- All PASS → `status: verified`, append a "## Verify History" section with timestamp.
- GAPs only → `status: gaps-found` (release-eligible if the user accepts GAPs).
- ≥1 BLOCKER → `status: blocked`, do NOT release.

If autonomy is ON:
- All PASS → autonomy auto-OFF, banner switches to "✅ DONE — autonomy released".
- Issues remain → keep autonomy ON so the agent can keep fixing.

### Step 8 — Coverage self-check (REQUIRED)

After printing the Verify Report, the agent MUST run the lint script to
confirm every entry in `acceptance_evals:` was consumed:

```bash
cat <verify-report-text>.md | {{PYTHON_BIN}} {{WORKSPACE_ROOT}}/.codex/lint_verify_report.py <spec-slug>
```

`.codex/` is the agent-toolkit installer convention; if the project has
renamed the helpers directory, adjust the path (see `agent-toolkit.config.json`).

The script reads the spec frontmatter, lists eval ids, scans the report by
word-boundary match → exit code:

| Exit | Meaning | Action |
|---|---|---|
| `0` | PASS — report cited every acceptance_eval | Print `Lint: ✓ N/N evals covered` in Summary, **proceed**. |
| `1` | FAIL — eval(s) missing; the script prints the missing ids | MUST re-emit the Verify Report with the missing items, do NOT commit a spec status change. |
| `2` | ERROR — spec missing / YAML invalid | Tell the user, fix the spec; treat as abort. |
| `3` | SKIP — spec has no `acceptance_evals` block | Print `Lint: ⊝ no acceptance_evals — skipped` in Summary, **proceed**. Suggest the user run `/eval-define` (status=grilled) or `/eval-backfill` (status=implementing). |

If the agent skips Step 8 → ADR-007 violation; the `evidence_audit` Stop
hook probe-spread check will tighten in a future iteration.

## Special rules

### "No probe can be designed for this story"

Some stories are inherently subjective (UX, performance promise). In that case:
- Do NOT hide — print a row with status `🟡 GAP: probe not yet designed`.
- Note "needs manual smoke by user".
- The spec cannot reach `verified` 100% via /verify — only "verified-automated".

### "MCP timeout or probe error"

- Probe timeout > 30 s → status `🟡 GAP: probe timeout, manual verify`.
- Probe errors because model/table doesn't exist → status `🔴 BLOCKER:
  feature not installed or module not upgraded`.

### "Which DB does verify run against"

Default: the dev/test DB defined in project config. NEVER verify against the
prod DB. If the spec demands prod data → print a warning + require the user
to confirm explicitly via `/verify --on-prod` (not yet implemented, treat as
refused).

## Anti-rationalizations

| Temptation | Counter |
|---|---|
| "Tests PASS, no need to verify" | Tests = behaviour you defined. Verify = behaviour the user REQUESTED. Tests can be wrong and still pass. |
| "Probe is hard to design, skip this story" | That is a 🟡 GAP, print it. Silent skip = misleading the user about completeness. |
| "Actual is slightly off, let it pass" | Diff > 0 = GAP. The user decides accept-vs-fix, not the agent. |
| "I can guess the root cause, no [assumption] tag needed" | Verify hasn't debugged — every root cause is a guess, must be tagged. |

## Red flags — the skill is failing if

- Verify Report does not have a full N-row table for N User Stories.
- A 🔴 BLOCKER exists but spec status is set to `verified` (should be `blocked`).
- Probes run serially instead of parallel; spread > 3 s wall-clock.
- Root causes do NOT have `[assumption]` tag → evidence_audit rejects.
- Autonomy state was not updated after verify (still ON when all PASS).
- **An `acceptance_evals` block exists in frontmatter but the agent
  designed ad-hoc probes** — must re-use (Step 1.5).
- **Probe SQL queries the raw DB for data that actually lives at the
  endpoint** — false BLOCKER (Step 1.7 was skipped).
- **Cached `smoke_result` > 5 minutes old was re-used without re-running** —
  verify is not a history lookup; must re-measure.
- **Runtime claim (BLOCK/cached/idempotent/...) verified via passive query
  instead of perturb test** — `[[claim-falsification]]` was not applied.
- **Story 5+ has no acceptance_eval and the agent skipped it** — must
  print 🟡 GAP "probe not designed", do NOT skip silently.

## Sibling skills

- `plan-feature` — phase 1, source spec.
- `grill` — phase 2, refine spec.
- `claim-falsification` — perturb-test pattern; verify-feature calls it
  for "empirical behaviour" probes (Step 1.7).
- `<stack>-<version>-data-verification` — detailed ORM probe recipes.
- `<stack>-<version>-debug-troubleshoot` — invoked if a BLOCKER needs deep debug.
- `code-review` — final gate after verify PASS.

## Reference

- ADR-002 (.agent-toolkit/decision-log.md) — decision to add phase 5.
- ADR-006 — perturb-test evidence required for classification claims.
- ADR-007 (2026-05-17) — verify-feature boost: auto-consume acceptance_evals
  + locate-observable-first + parallel-required + re-run policy.
- Original — Phase 5 was not copied from mattpocock; it is a Nakivo-flow
  addition.
