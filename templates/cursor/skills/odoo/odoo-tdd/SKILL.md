---
name: odoo-tdd
description: Red-Green-Refactor TDD for Odoo — write the failing test FIRST, then minimum code to pass, then refactor. Step 0 detects the addon's Odoo version from `__manifest__.py` and loads `references/odoo-<N>-tdd-pitfalls.md` for version-specific test framework quirks (SavepointCase vs TransactionCase availability, `@api.model_create_multi` test patterns, etc.). Open whenever the user says "viết test trước", "TDD", "tôi muốn test driven", "write test then implement", or when `tasks-breakdown` Phase 3 produced a task with a behavioral acceptance criterion.
---

# Odoo TDD — Red → Green → Refactor (version-aware)

> The Red→Green→Refactor cycle keeps the agent honest: if you cannot
> write a failing test for the change, you do not understand the change
> yet — go back to spec. Tests-after-the-fact let the agent rationalize
> the test around whatever code happened to land.

Pair with `tasks-breakdown` (provides acceptance criteria),
`odoo-data-verification` (live ORM probes), and `odoo-codebase-discovery`
(find test fixtures and base classes).

## 0. Version detection (MANDATORY first step)

Same protocol as `odoo-code-review`:

1. **`__manifest__.py` `version` field** — `codebase.read_manifest`.
2. **Fallback signals** if manifest missing.
3. **Ask user** only if inconclusive.

Load `references/odoo-<detected>-tdd-pitfalls.md`:

| Detected major | Reference |
|---|---|
| 12 | `references/odoo-12-tdd-pitfalls.md` (standalone) |
| 13 | load `references/odoo-13-tdd-pitfalls.md` |
| 14 | load `references/odoo-14-tdd-pitfalls.md` |
| 15 | load `references/odoo-15-tdd-pitfalls.md` |
| 16 | load `references/odoo-16-tdd-pitfalls.md` (+ note: backports some v17 conventions) |
| 17 | `references/odoo-17-tdd-pitfalls.md` |
| 18 | `references/odoo-18-tdd-pitfalls.md` ← 17 |
| 19 | `references/odoo-19-tdd-pitfalls.md` ← 18 ← 17 |
| 20 | `references/odoo-20-tdd-pitfalls.md` ← 19 ← 18 ← 17 (pre-GA stub) |
| 21+ | fall back to 20 stub + flag MEDIUM |

## 1. When to apply

- A `tasks-breakdown` task whose acceptance criterion is behavioral
  (computed field value, constraint, workflow transition, controller
  response).
- A bug fix where you can describe the buggy behavior in one sentence —
  write that sentence as a failing test first.
- A regression-prevention task ("don't let this break again").

## 2. When NOT to apply

- Pure data migration / `noupdate` XML edits — write a smoke probe with
  `odoo-data-verification` instead.
- View/template changes with no behavior — manual smoke is faster.
- Discovery work (reading + understanding existing code).
- **Empirical / behavioural claims** (RPC X blocks UI, endpoint Y is cached,
  cron Z is idempotent, ...) — these are NOT unit tests; the assertion
  layer is wrong. **Escalate to `[[claim-falsification]]`** which runs the
  perturb-test recipe on real user action (Playwright MCP).

## 3. Test layer decision tree (REQUIRED — run BEFORE writing the test)

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
`TransactionCase`. Open `claim-falsification` and follow its recipe.

## 4. Behavioural test — Playwright + real Odoo action (REQUIRED for E2E claims)

When the claim is "X has runtime property P observable through the UI"
(BLOCK, ASYNC, cached, debounced, retried, ...) the test layer MUST be:

1. **Real Odoo action via Playwright MCP** — open the browser, log in,
   navigate to a real action. Do NOT mock the user.
2. **Enumerate ALL candidate requests** — instrument
   `performance.getEntries()` or `window.fetch` to capture EVERY RPC the
   action fires.
3. **Per-request perturb-test** — for each candidate, open the matching
   `claim-falsification` recipe.
4. **Stack the cohort** — final output is a table `[(url, role, evidence)]`
   for every request in the action.

Perturbation menu (pick one based on what is safe to modify):

| Perturbation | When safe | Effect |
|---|---|---|
| `time.sleep(N)` inside the handler | Dev/test DB, code path is reachable, easy to revert | Direct latency injection, N seconds added |
| Heavy query | Cannot modify handler; want natural slowness | Forces real-world slow path with no code edit |
| Playwright `route().continue_({delay: N*1000})` | Cannot touch server; want to slow network only | Network-level injection, server unchanged |
| `freezegun` / clock monkeypatch | Testing TTL / scheduling / time-window logic | No latency, time-axis perturbation |

## 5. The loop — one acceptance criterion at a time

### RED — write the failing test

1. **Find the right test layer.** Use `odoo-codebase-discovery`:
   - Per-model unit logic → `tests/test_<model>.py` inheriting `TransactionCase`.
   - Cross-model workflow → `SavepointCase`.
   - HTTP controller / portal → `HttpCase`.
   - Cron / queue logic → `TransactionCase` + explicit `cron._method_direct_trigger()` call (the exact API name differs by version — see reference).

2. **Use existing fixtures.** Grep for sibling test files in the same
   module first; reuse `setUpClass` factories, don't re-invent partner /
   product creation helpers.

3. **Write ONE test method per acceptance criterion.** Method name
   describes the expected behavior, not the function under test —
   `test_<feature_field>_appears_in_<output>` (generic placeholder; use
   your project's actual field name).

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
   net.
3. **Run sibling tests** in the same module to catch regressions in
   adjacent behavior.

## 6. Version-specific pitfalls

After Step 0, load `references/odoo-<detected>-tdd-pitfalls.md` for
quirks like:
- `SavepointCase` availability (renamed `TransactionCase` w/ savepoint in 17+).
- Constraint timing (`@api.constrains` fires on create vs. write).
- Cron direct-trigger API name.
- `@api.depends` flush timing on stored computes.
- Email validator strictness on test fixtures.

## 7. Anti-rationalizations

| Rationalization | Counter-argument |
|---|---|
| "Writing the test first is slower" | False for any feature longer than the test itself. The test forces you to define DONE; without it, "done" drifts until reviewer says stop. |
| "Odoo tests are heavy, I'll skip the loop" | `SavepointCase` / equivalent rolls back per method — modern Odoo test infrastructure is fast. The slowness story is from cargo-cult `TransactionCase` setUp. |
| "It's a constants/config change, no test needed" | If the constant changes behavior, that behavior is testable. If it doesn't change behavior, why are you changing it? |
| "I'll write the test once the code stabilizes" | The "stable" code defines the test's success criteria — the loop is now backwards. Stop and restart from RED. |
| "The reviewer can verify by reading the diff" | Reading verifies syntactic correctness, not behavioral. Without a test, the next refactor silently breaks the behavior with no signal. |
| "Test fixtures are too complex to write from scratch" | Reuse: grep `setUpClass` in the module's existing tests. If no sibling fixture exists, add a one-line factory to a shared `tests/common.py`. |

## 8. Red flags

- A test was committed without first showing it failed for the expected reason.
- The test was edited after first run to match observed output (instead of fixing the code).
- Multiple acceptance criteria were collapsed into one `test_*` method.
- The implementation grew beyond what the test required ("might as well add Y while I'm here").
- The refactor step was skipped because "the code looked fine".
- A pre-existing test was deleted or weakened to avoid a failure — stop and ask the user; tests are not noise.

## 9. Output contract (per cycle) — bắt buộc theo ADR-003

When this skill is active, each cycle reports six lines:

```
RED:        tests/<file>.py::<method> — failed at <line> (<error class>)
data_probe: <ORM expression đã chạy qua realdata_test MCP — generic example:
            self.env['<model>'].search([('<flag_field>','=',True)]).ids = [12,34]>
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
