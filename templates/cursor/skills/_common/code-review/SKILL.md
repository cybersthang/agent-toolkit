---
name: code-review
description: Exhaustive single-pass code review — surfaces ALL Blocker + Medium + Low findings in ONE conversation, with reproducible PROOF per finding. Open this skill whenever the user asks "review", "audit", "phân tích sâu", "tìm bug", "kiểm tra code", or "còn gì cần fix nữa không?". Stack-agnostic; pair with the per-stack overlay (e.g. odoo-12-code-review) for framework specifics.
---

# Code Review — Exhaustive Single-Pass (Stack-Agnostic Core)

> Mục tiêu: tìm cho hết — Blocker dễ thấy, Medium dễ trượt, Low dễ bỏ qua —
> trong cùng một session. Không drip-feed sang session sau. Không thay đổi
> count giữa các lần chạy trên cùng một code base.

This skill is the **shared methodology**. Combine with a per-stack overlay
(`odoo-12-code-review`, `odoo-17-code-review`, …) for framework-specific
checks. The overlay extends the dimensions; this file owns the workflow,
severity rubric, and proof contract.

## 0. Lock-file precedence (ALWAYS first)

Before touching the code, look for an existing lock file:

```
.codex/audit_findings_locked.md
.codex/audit_findings_<module>_locked.md
```

If one exists:

1. Cite the recorded count verbatim (e.g. `3 BLOCKER + 9 MEDIUM + 30 LOW = 42`).
2. Only propose a different number when:
   - code in scope has changed since the lock timestamp (`git log` after that date),
   - reproducible proof contradicts a specific entry,
   - the user explicitly requests a re-audit.
3. Any count change updates the lock file's revision header with a one-paragraph rationale. Never silently rewrite.

If no lock file exists, proceed with a fresh exhaustive pass and lock the
result at the end (Step 5).

## 1. Scope + discovery (use MCP, do NOT broad-read)

1. Confirm scope with the user if ambiguous: a module, a feature, a PR diff?
2. Use the codebase MCP (`workspace_status`, `discover_modules`, `read_manifest`,
   `find_inheritance_chain`, `list_test_targets`, `search_xml_ids`,
   `search_text`, `read_file_chunk`) — never `grep -r` the whole tree blindly.
3. For large surfaces, spawn parallel Explore agents — one per dimension —
   and merge their findings.
4. Always cite `path:line` so the user can click through.

## 2. Dimensions matrix (cover ALL — say so explicitly if you skip one)

For each dimension, enumerate findings at **every** severity. If a dimension
has zero findings at a severity, write "none — verified by <evidence>". The
silent gap is what lets Mediums and Lows escape between sessions.

| # | Dimension | Probe for |
|---|-----------|-----------|
| 1 | Data schema / persisted JSON | orphan fields, producer-consumer mismatch, schema drift between fresh-install XML and Python default |
| 2 | SQL touchpoints | missing index for WHERE/ORDER BY, ILIKE on compressed/encoded blob, JSON path that bypasses gzip wrapper |
| 3 | Background workers / cron | daemon thread can die silently (un-wrapped raise inside `while True`), unbounded queue, drift between `nextcall` and effective frequency, races on shared dict |
| 4 | HTTP controllers / API | missing auth, CSRF on state-changing endpoints, no size cap on payload, decompression bomb, error swallowed without log |
| 5 | ORM hooks / monkey-patch | install/uninstall asymmetry, registry rebuild safety, `setattr` on a class that's reloaded each upgrade |
| 6 | XML / view references | field referenced in view but not declared, XML ID renamed without migration, inheritance ordering |
| 7 | Frontend consumers (JS / OWL / QWeb / templates) | reads a key the backend stopped writing (or vice-versa), missing escape, leftover jQuery in a 17-style codebase |
| 8 | Test coverage | new branch with no test, fixture variety, round-trip equality (`load(dump(x)) == x`), boundary values |
| 9 | Config / security / data XML | `noupdate` flag, hard-coded `xmlid` ref, multi-company `ir.rule` absent, missing `ir.model.access` row for a new model |
| 10 | Edge cases | empty input, huge input, concurrent input, unicode/non-ASCII, timezone, leap second/DST, NaN/Inf in math |
| 11 | Unit consistency | ms vs s vs ns mixed without conversion, byte vs bit, decimal vs binary KiB/KB |
| 12 | Naming consistency | same concept under different names across model/view/JS/SQL surfaces |
| 13 | Double-counting in aggregations | parent total + child subtree overlap, recursive sum that visits both branches |
| 14 | Drift formulas | `accounted vs wall` direction, sign convention, tolerance threshold (`<` vs `<=`), AND/OR confusion in compound predicates |
| 15 | Concurrency / resource leaks | dict that only grows, thread-local that misses a `finally`, lock acquired twice on the same path, file/socket left open |
| 16 | Internationalisation | `json.dumps(..., ensure_ascii=True)` mangling Vietnamese / non-ASCII identifiers, missing `_()` on user-facing strings |

If a dimension is N/A for the scope (e.g. no HTTP controllers), state that
explicitly: *"Dimension 4 N/A — no controller code in scope (verified via
`search_text('http.route')` → 0 hits)."* Don't silently skip.

## 3. Severity rubric (apply uniformly, no agent-claim trust)

| Severity | Bar | Examples |
|----------|-----|----------|
| **BLOCKER** | Causes data loss, silent corruption, makes a feature unusable, or is a remotely exploitable CVE. Reproducible PROOF tracing trigger → observable failure required. | Daemon worker dies silently on first DB outage; OR-vs-AND mismatch in consistency check; SQL search on gzip-encoded JSON returns 0 hits on 50% of rows |
| **MEDIUM** | Correctness gap with a workaround, OR security/performance risk under specific (plausible) conditions. Reproducible PROOF required — but the conditions may be insider-only / under load / on edge data. | CSRF disabled on state-changing JSON endpoint; gzip decompression with no size cap (insider abuse); JSON dump without `ensure_ascii=False` breaking Unicode search; default value drift between Python field and XML data-load; pagination missing on dashboard endpoint; in-memory dict that only grows |
| **LOW** | Cleanup, naming, documentation, missing tests, hard-coded references, multi-company gap, or speculative bug needing unlikely runtime conditions. | `tottime/cumtime` cProfile-style naming mixed with `_ns` keys; hard-coded `base.user_admin` in `security.xml`; missing `_truncated` flag on a capped list; no multi-company `ir.rule` on a shared model; comment-only documentation of an init order |

Demotion rule: if a finding cannot meet its bar, demote — don't keep
speculative BLOCKERS. Overstatement loses user trust faster than a missed Low.

## 4. Per-finding contract (the PROOF line)

Each finding emits a block of this exact shape:

```
### [BLOCKER|MEDIUM|LOW] #<short-id>: <one-line title>
- File: <path>:<line-start>-<line-end>
- Dimension: <dimension number + name>
- Proof: <ONE sentence tracing trigger code line A → observable failure at line B (or DB/UI symptom).>
- Fix idea: <one or two sentences, estimated effort>
- Live-verify (optional): <expression you would run via realdata_test, OR "static-only — no DB needed">
```

If you cannot write the proof line, the finding does not exist — drop it.
This is the rule that prevents "9 mediums one session, 4 the next".

## 5. Reporting format

Open the report with a count table the user can paste into the lock file:

```
| Pass | BLOCKER | MEDIUM | LOW | Method |
|------|---------|--------|-----|--------|
| REV-N (this session) | X | Y | Z | <agent + verification notes> |
```

Then the findings, grouped by severity, ordered by dimension. End with:

- **Dimensions skipped**: list with reason.
- **Live-verified findings**: list ids that were checked via the
  `realdata_test` / `postgres` MCP (proof beyond static read).
- **Open questions for the user**: anything you couldn't resolve without a
  decision.

## 6. Live verification (do this for Mediums when feasible)

A Medium finding survives review more credibly when you check it against
real data via the `realdata_test` MCP (`eval_orm_expression`,
`consistency_check_eval`, `compare_with_expected`) or the `postgres` MCP
(`run_select`). Examples worth verifying:

- "Default drift": query DB to see which value actually populated rows.
- "Memory dict leak": measure size growth across a short window.
- "Index missing": `EXPLAIN ANALYZE` the suspect query.
- "Race condition": run the same expression N times with
  `consistency_check_eval` — if fingerprints diverge, severity stands.

Mark verified findings explicitly: `Verified live on <db> 2026-MM-DD`.

## 7. Lock the result (Step 5 of audit-methodology)

After the report:

1. Write `.codex/audit_findings_locked.md` (or per-module variant). Header
   includes: timestamp, revision number, pass-by-pass count history with
   what changed, methodology lock paragraph repeating the rubric above.
2. Refresh a canonical decision entry in `.codex/canonical_decisions.json`
   whose answer cites the lock file path + revision + count. Future
   "what else to fix?" queries resolve through `lookup_canonical_decision`
   deterministically.

## 8. Anti-patterns (do NOT do these)

- **Drip-feed**: "5 issues this session, 5 more next session" — user loses trust. Findings either exist now and you list them, or they don't.
- **Recount drift**: same module + same code → different count two sessions in a row, with no code change and no methodology change. Methodology bug.
- **BLOCKER inflation**: speculative "if X happens, Y breaks" without showing X is reachable. Demote to LOW.
- **Trust the audit agent verbatim**: agents overstate. Verify every cite by reading the code.
- **Stop at BLOCKERS**: Mediums and Lows are the long tail. Force-enumerate per dimension or they will escape this session and re-appear as "new" findings next session.
- **Skip a dimension silently**: write "N/A — <why>" when truly inapplicable; never omit.

## 8a. Common rationalizations (force a counter-argument on each one)

When tempted to skip work or downgrade a finding, check this table. The
left column is what the agent's inner voice says; the right column is what
to do instead.

| Rationalization | Counter-argument |
|-----------------|------------------|
| "It works, that's good enough" | Working code that's silently corrupting data or unreadable creates debt that compounds. The review is the quality gate, not "it ran once". |
| "I (or the audit agent) wrote it, so I know it's correct" | Authors are blind to their own assumptions. Re-derive the proof line from scratch by reading the code, not the memory of writing it. |
| "We'll clean the LOW items up later" | Later never comes. Either list it now (so the user can decide) or delete it from consideration with justification. No "I'll come back to it". |
| "Tests pass, so it's good" | Tests are necessary but not sufficient. The dimensions matrix covers cases tests rarely catch (units, drift formulas, double-counting). |
| "AI-generated code is probably fine" | AI code needs MORE scrutiny, not less. Apply the full matrix, especially edge cases and hidden state. |
| "The audit agent already labeled it BLOCKER, that's enough" | Agents overstate. Re-verify by reading code. Demote if the proof line can't trace trigger → failure. |
| "Too many LOW findings, let me batch them" | Batching hides them. List every LOW with one-line title + line ref; the user can prioritize, but only if they see the full list. |

## 8b. Red flags (the review itself is failing if any are true)

If you catch yourself doing any of these, the review is broken — restart
that step.

- A finding has no PROOF line, or the proof is "if X happens, Y breaks" without showing X is reachable.
- A dimension was checked silently (no "none — verified by …" note).
- A LOW was dropped because "the list was getting too long".
- A previously-LOCKED count was changed without a REV-N+1 header + rationale.
- A BLOCKER was approved without a reproducible trigger → observable failure trace.
- A MEDIUM was filed without an attempt at live-verify when a relevant MCP tool exists.
- "LGTM" / "looks correct" was used as a verdict without listing what was actually checked.
- A change-set was reviewed end-to-end without first checking change size + splittability (see Step 8c).
- An audit agent's output was copied without per-finding code re-read.

## 8c. Change sizing + splitting (when reviewing a PR / diff)

Apply this when the user asks "review this PR" or "review this diff". For
"review the whole module" reviews, skip — sizing doesn't apply.

Target sizes:

```
~100 lines changed   → Good. Reviewable in one sitting.
~300 lines changed   → Acceptable if it's ONE logical change + its tests.
~1000 lines changed  → Too large. Ask the author to split.
```

Splitting strategies (recommend one explicitly when flagging size):

| Strategy | How | When |
|----------|-----|------|
| **Stack** | Submit small change, base the next change on it | Sequential dependencies |
| **By file group** | Separate changes per logical group (models / views / JS) | Cross-cutting concerns |
| **Horizontal** | Land shared helper / stub first, then consumers | Layered architecture |
| **Vertical** | Break a feature into smaller end-to-end slices | Feature work |

Don't review changes >1000 LOC in one pass. Reply: "This change is too
large for a thorough review. Splitting strategy: <one of the above>."

## 8d. Dead code hygiene

After any refactor / migration / removal in the change-set:

1. List code that is now unreachable or unused (functions, fields, XML records, JS components).
2. Show the user the list with line refs.
3. **Ask before deleting** anything you're not 100 % sure about. A field that "looks unused" may be:
   - referenced by an external integration not in the workspace,
   - read by raw SQL that grep won't catch,
   - used by a noupdate XML record on a different DB.
4. Use `nakivo_codebase.search_text` / `search_xml_ids` (Odoo 12) or
   `codebase.search_text` / `search_xml_ids` (Odoo 17) to prove
   non-reference before recommending deletion.

Speculative deletion is a LOW finding ("possibly unused — verify before
delete"), not a recommended action.

## 8e. Dependency discipline (when the change adds a dep)

Before approving any new dependency (Python package, JS lib, Odoo addon,
external service):

1. Does the existing stack already solve this? (stdlib, existing addons, already-installed lib)
2. How large is the dependency? (transitive count, install size)
3. Is it actively maintained? (commits in last 12 months)
4. Are there known CVEs? (`pip-audit` / `npm audit` / OSV)
5. What is the license? (compatible with the project's license — e.g. GPL incompatible with proprietary Odoo Enterprise)
6. For Odoo addons specifically: is the version constraint compatible (`version: 12.0.x` vs `17.0.x`), and is there an uninstall path?

Flag as MEDIUM if any check fails; BLOCKER if the dep introduces a known
CVE or license conflict.

"Prefer standard library and existing addons over new dependencies. Every
dependency is a liability the project carries forever."

## 9. Self-check before reporting

Silently answer YES to all four:

1. Did I read the lock file (if it exists) and cite the recorded count?
2. Did I cover every dimension in the matrix — or explicitly mark it N/A?
3. Does every BLOCKER and MEDIUM have a one-line PROOF that traces real code?
4. Did I look for at least one finding in each (dimension × severity) cell,
   instead of stopping at Blockers?

If any answer is "no", redo that step before sending the report.

## References (load only when relevant to the current finding)

These are deeper checklists kept in separate files so the entry SKILL stays
compact. Open them when the dimension matrix points there — don't read them
all up-front.

- `references/security-checklist.md` — exhaustive security probes (auth, input, sessions, CSRF, secrets, headers, OWASP-style + Odoo-specific items: `ir.model.access`, `ir.rule`, `sudo()`, `csrf=False` policy).
- `references/performance-checklist.md` — exhaustive performance probes (N+1, indexes, batch ops, caching, prefetch, store-or-not for compute, queue caps).

## Sibling skills

- `<stack>-code-review` — framework-specific overlay (Odoo 12 / Odoo 17 / …); reuse this file's workflow + rubric.
- `<stack>-codebase-discovery` — the MCP routing used in Step 1.
- `<stack>-data-verification` — the live-verify tooling used in Step 6.
- `<stack>-deterministic-answers` — canonical decisions registry used in Step 7.
