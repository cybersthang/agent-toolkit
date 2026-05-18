---
name: odoo-12-tdd
description: Red-Green-Refactor for Odoo 12 — write the failing test FIRST, then minimum code to pass, then refactor. Open this skill whenever the user says "viết test trước", "TDD", "tôi muốn test driven", "write test then implement", or when `spec-driven-feature` Phase 3 produced a task with a behavioral acceptance criterion.
---

# Odoo 12 TDD — Red → Green → Refactor

> The Red→Green→Refactor cycle keeps the agent honest: if you cannot
> write a failing test for the change, you do not understand the change
> yet — go back to spec. Tests-after-the-fact let the agent rationalize
> the test around whatever code happened to land.

Pair with `spec-driven-feature` (provides acceptance criteria), 
`odoo-12-data-verification` (live ORM probes), and `odoo-12-codebase-discovery`
(find test fixtures and base classes).

## When to apply

- A `spec-driven-feature` task whose acceptance criterion is behavioral
  (computed field value, constraint, workflow transition, controller
  response).
- A bug fix where you can describe the buggy behavior in one sentence —
  write that sentence as a failing test first.
- A regression-prevention task ("don't let this break again").

## When NOT to apply

- Pure data migration / `noupdate` XML edits — write a smoke probe with
  `odoo-12-data-verification` instead.
- View/template changes with no behavior — manual smoke is faster.
- Discovery work (reading + understanding existing code).
- **Empirical / behavioural claims** (RPC X blocks UI, endpoint Y is cached,
  cron Z is idempotent, ...) — these are NOT unit tests; the assertion
  layer is wrong. **Escalate to `[[claim-falsification]]`** which runs the
  perturb-test recipe on real user action (Playwright MCP). See "Test layer
  decision tree" below.

## Test layer decision tree (REQUIRED — run this BEFORE writing the test)

| Question about behaviour | Right test layer | Skill |
|---|---|---|
| Does method `Model.foo()` compute the right value? | `TransactionCase` / `SavepointCase` | this skill |
| Does workflow transition X→Y fire on event Z? | `SavepointCase` | this skill |
| Does controller `/route/path` return correct JSON shape? | `HttpCase` + `self.url_open` | this skill |
| Does ORM constraint reject bad data? | `TransactionCase` + `assertRaises` | this skill |
| **Does RPC X actually BLOCK the UI on a real user action?** | Perturb-test on real Playwright session | `[[claim-falsification]]` Recipe 1/2 |
| **Is endpoint Y cached for key K?** | Perturb-test (2 calls, same K) | `[[claim-falsification]]` Recipe 3 |
| **Is mutation Z idempotent?** | Perturb-test (call N times, observe side-effect count) | `[[claim-falsification]]` Recipe 4 |
| **Is request R fire-and-forget vs awaited?** | Perturb-test (inject delay, observe time-to-UI-ready) | `[[claim-falsification]]` Recipe 1/2 |
| **Does classifier C emit correct label on each input?** | Sample-and-audit | `[[classifier-output-audit]]` |

If question matches a row in the **bold** half — STOP, do NOT write a
`TransactionCase`. Open `claim-falsification` and follow its recipe. Reason:
unit tests assert what the test author wrote; perturb-tests refute claims
the test author cannot bias.

## Behavioural test — Playwright + real Odoo action (REQUIRED for E2E claims)

When the claim is "X has runtime property P observable through the UI"
(BLOCK, ASYNC, cached, debounced, retried, ...) the test layer MUST be:

1. **Real Odoo action via Playwright MCP** — open the browser, log in,
   navigate to a real action (any: Kanban contact, list orders, form view,
   pivot, dashboard). Do NOT mock the user; the bug you are testing
   typically depends on the real DOM + the real `ActionManager.doAction`
   call chain.
2. **Enumerate ALL candidate requests** — instrument `performance.getEntries()`
   or `window.fetch` to capture EVERY RPC the action fires. The test
   iterates per-request, not per-suspected-request. Reason: long-tail
   requests are where mis-classification hides.
3. **Per-request perturb-test** — for each candidate, open the matching
   `claim-falsification` recipe (Recipe 1 for BLOCK/await, Recipe 2 for
   ASYNC/fire-and-forget). Inject the perturbation, measure the
   observable, classify.
4. **Stack the cohort** — at the end, you have a table `[(url, role,
   evidence)]` for every request in the action. THAT is the test output,
   not a single assertion.

Perturbation menu — **pick one based on what is safe to modify**:

| Perturbation | When safe | Effect |
|---|---|---|
| `time.sleep(N)` inside the handler | Dev/test DB, code path is reachable, easy to revert | Direct latency injection, N seconds added |
| Heavy query (e.g. `search(limit=very_high)` on a large model) | Cannot modify handler; want natural slowness | Forces real-world slow path with no code edit |
| Playwright `route().continue_({delay: N*1000})` | Cannot touch server; want to slow network only | Network-level injection, server unchanged |
| `freezegun` / clock monkeypatch | Testing TTL / scheduling / time-window logic | No latency, time-axis perturbation |

Whichever is chosen, the **observable** (Y) is the SAME: time-to-`ui_ready`
(or whatever the user-perceived completion signal is). Y must be measured
on the real user action, not on the dashboard that reads the classifier
output (circular).

## The loop — one acceptance criterion at a time

### RED — write the failing test

1. **Find the right test layer.** Use `odoo-12-codebase-discovery`:
   - Per-model unit logic → `tests/test_<model>.py` inheriting `TransactionCase`.
   - Cross-model workflow → `SavepointCase` (test installs once, rolls back per method).
   - HTTP controller / portal → `HttpCase`.
   - Cron / queue logic → `TransactionCase` + explicit `cron._method_direct_trigger()` call.

2. **Use existing fixtures.** Grep for sibling test files in the same
   module first; reuse `setUpClass` factories, don't re-invent partner /
   product creation helpers.

3. **Write ONE test method per acceptance criterion.** Method name
   describes the expected behavior, not the function under test:
   `test_partner_with_nakivo_flag_appears_in_export` —
   not `test_get_export_data`.

4. **Run the test → it MUST fail.** `python -m pytest <path>::<test>` or
   the project's standard runner. A passing test in this step is a bug
   in the test, not a feature win.

5. **Verify it fails for the RIGHT reason.** Read the error: is it
   `AssertionError: expected X got Y` (correct — test reaches the
   assertion), or `AttributeError: no method foo` / `KeyError` (also
   acceptable — feature doesn't exist yet)? Anything else
   (`ImportError`, fixture failure, syntax error in test) means the test
   itself is wrong — fix the test, re-run, confirm RED.

### GREEN — minimum code to pass

1. **Smallest change that makes THIS test green.** Resist adding logic
   for the next test you can imagine — that's speculation, not TDD.
2. **Run the new test only**, not the whole suite — a fast loop matters.
3. **Confirm green.** If green, advance. If still red, do not edit the
   test to match the code — that defeats the loop. Adjust the
   implementation.

### REFACTOR — clean up with the test as guard

1. Re-read the new code. Anything obvious to simplify? Extract a helper,
   rename a variable, collapse a branch.
2. **Re-run the test after EACH refactor step.** Tests are the safety
   net; if you stack three refactors and rerun once, you don't know
   which one broke it.
3. **Run sibling tests** in the same module to catch regressions in
   adjacent behavior.

## Odoo 12 specifics — common pitfalls

| Pitfall | Detection | Fix |
|---|---|---|
| Test passes locally but fails in CI | Test depends on database state from a previous run | Use `SavepointCase` (auto-rollback) or `tearDown` cleanup |
| `KeyError: 'ir.model.access'` | New model has no access row | Add `security/ir.model.access.csv` row before re-running |
| Constraint test silently passes | `_constrains` only fires on write, not on `create()` of pre-validated records | Force a `partner.write({...})` after create to trigger |
| Cron test never executes the job | `model.with_context(cron_method=...)` not used | Call `_method_direct_trigger()` on the cron record, not the model method |
| Mock partner `email` rejected | Default email validator blocks placeholder strings | Use `nakivo.test@example.com` style, not `mock` |
| `@api.depends` test never recomputes | Reading a stored compute on a non-flushed record | Add `record.flush()` before reading |
| Test asserts on `Many2one.name` and breaks under translation | Test DB language drift | Compare `record.partner_id.id`, not `.name` |

## Anti-rationalizations

| Rationalization | Counter-argument |
|---|---|
| "Writing the test first is slower" | False for any feature longer than the test itself. The test forces you to define DONE; without it, "done" drifts until reviewer says stop. |
| "Odoo tests are heavy, I'll skip the loop" | `SavepointCase` rolls back per method — modern Odoo test infrastructure is fast. The slowness story is from cargo-cult `TransactionCase` setUp. |
| "It's a constants/config change, no test needed" | If the constant changes behavior, that behavior is testable. If it doesn't change behavior, why are you changing it? |
| "I'll write the test once the code stabilizes" | The "stable" code defines the test's success criteria — the loop is now backwards, and the test will rationalize whatever the code does. Stop and restart from RED. |
| "The reviewer can verify by reading the diff" | Reading verifies syntactic correctness, not behavioral. Without a test, the next refactor silently breaks the behavior with no signal. |
| "Test fixtures are too complex to write from scratch" | Reuse: grep `setUpClass` in the module's existing tests. If no sibling fixture exists, add a one-line factory to a shared `tests/common.py` — investment pays back on the second test. |

## Red flags

- A test was committed without first showing it failed for the
  expected reason.
- The test was edited after first run to match observed output (instead
  of fixing the code).
- Multiple acceptance criteria were collapsed into one `test_*` method.
- The implementation grew beyond what the test required ("might as well
  add Y while I'm here").
- The refactor step was skipped because "the code looked fine".
- A pre-existing test was deleted or weakened to avoid a failure — stop
  and ask the user; tests are not noise.

## Output contract (per cycle) — bắt buộc theo ADR-003

When this skill is active, each cycle reports six lines (4 cũ + 2 dòng mới
bắt buộc theo ADR-003 "test phải real-data + regression sweep"):

```
RED:        tests/<file>.py::<method> — failed at <line> (<error class>)
data_probe: <ORM expression đã chạy qua realdata_test MCP — vd:
            self.env['res.partner'].search([('nakivo_flag','=',True)]).ids = [12,34]>
GREEN:      <files changed, LOC>; test passed in <Ns>
REFACTOR:   <one-line summary of cleanup, or "no refactor needed">
REGRESSION (all sibling tests trong cùng dir module):
            <N sibling tests run, all passed>  (hoặc list failures)
cross_module_smoke: <nếu có @api.depends chéo module — liệt kê module + status;
                   hoặc "n/a — feature isolated">
```

**A cycle without these six lines isn't proven complete — finish it.**

Nếu thiếu `data_probe` → test có thể là mock-only (vi phạm ADR-003).
Nếu thiếu `REGRESSION (all)` → có thể có hidden regression trong cùng module.

## Sibling skills

- `spec-driven-feature` — Phase 3 hands acceptance criteria to this skill.
- `odoo-12-data-verification` — provides ORM expressions used inside test assertions.
- `odoo-12-codebase-discovery` — locates fixtures, base test classes, sibling tests.
- `odoo-12-debug-troubleshoot` — when RED fails for the wrong reason.
- `doubt-driven-review` — overlay before declaring the cycle done.
- `code-review` — final gate after the feature's tasks all pass.
