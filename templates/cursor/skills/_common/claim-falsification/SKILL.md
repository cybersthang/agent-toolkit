---
name: claim-falsification
description: Dynamic pattern to VERIFY any claim in spec/code via "inverse-perturbation" — actively perturb one input dimension, observe the predicted output change. Applies to any claim of shape "X has property P" (BLOCK/ASYNC, cached/not, idempotent, deterministic, lazy, atomic, guarded, ...). Does NOT hardcode property name; selects perturbation + observable based on the claim at runtime.
---

# Claim Falsification — Dynamic Inverse-Perturbation Review

> **Empirical review technique (formalized 2026-05-17)**:
> "If the spec says X = BLOCK, inject sleep into X — the UI must wait. If X = ASYNC, the sleep must not affect UI. Use real data + inverse perturbation to prove."
> This skill abstracts that pattern; it applies to any property P, not just BLOCK/ASYNC.

## When to apply

- During Grill (Phase 2) when a HIGH-stakes decision is being settled (classification, threshold, guarantee).
- During Verify (Phase 5) when the spec already has `acceptance_evals` but its probe is a passive query (count rows) — promote to active falsification.
- During code review when code claims a contract (decorator, type hint, docstring) and the implementation needs proof.
- When the user says "prove it wrong", "perturb test", "inverse test", "falsifiability".
- Before promoting an invariant from `warn` to `blocker`.

## When to SKIP

- The claim has no observable ("code clean", "easy to read") → cosmetic, not falsifiable at runtime.
- A canonical test suite already proves the claim (check `decision-log.md`) → re-run the test instead of rebuilding the perturbation.
- Production DB only (no dev/staging available) → never perturb prod; tell the user.
- Future-tense claims ("will scale", "will handle") — perturbation only verifies the present; future state needs a separate load test.

## Core pattern

```
Given claim:    "thing X has property P"
Find triple:    (perturbation D, observable Y, predicted Δ)
  · D: action that perturbs one input dimension of X.
  · Y: measurable signal, INDEPENDENT of the classifier output.
  · Δ: the predicted change in Y under P:
       - If P holds → Y(perturbed) − Y(baseline) ≈ predicted_Δ_under_P
       - If P doesn't hold → Y(perturbed) − Y(baseline) ≈ predicted_Δ_under_NOT_P
Procedure:
  1. Measure Y(baseline) — N runs, take the median to remove jitter.
  2. Apply D on dev/staging (NEVER prod).
  3. Measure Y(perturbed) — N runs.
  4. Verdict:
     - |Y_p − Y_b − Δ_P| ≤ tolerance → claim CONSISTENT.
     - |Y_p − Y_b − Δ_NOT_P| ≤ tolerance → claim REFUTED.
     - Neither matches → inconclusive; redesign D or Y.
  5. REVERT D (always — never leave perturbation in code).
```

## Recipe catalog — 15 claim shape → perturbation mapping

Each recipe is a **starting point**, not a hardcode. For a new claim that
does not match any of the 15 below, apply the core pattern and document the
custom recipe in the spec acceptance_evals under `recipe: custom · derivation: ...`.

| # | Claim shape | Perturbation D | Observable Y | Predicted Δ if P holds | Anti-Δ if NOT P |
|---|---|---|---|---|---|
| 1 | "X gates Y" (BLOCK / synchronous / awaits) | Inject `sleep(N)` / artificial delay into X | Time-to-Y-ready | +N ± tolerance | ≈ 0 |
| 2 | "X is async / fire-and-forget" | Inject `sleep(N)` into X | Time-to-Y-ready | ≈ 0 | +N |
| 3 | "X is cached for key K" | Call X(K) twice with the same K | Latency of 2nd call | `< max(1/10 × 1st, stack_envelope_floor + 20%)` ⓘ | ≈ 1st (within 30%) |
| 4 | "X is idempotent" | Call X(input) twice | Side-effect count (rows, files, msgs) | unchanged (= 1×) | doubled (2×) |
| 5 | "X is deterministic" | Run X(input) N times | sha256(output) | identical N/N | ≥ 2 distinct |
| 6 | "X is atomic / all-or-nothing" | Inject exception mid-transaction X | DB state for written rows | 0 partial rows | ≥ 1 partial row |
| 7 | "X is guarded by permission P" | Call X with a user lacking P | HTTP status / exception | 403 / AccessError | 200 / success |
| 8 | "X is lazy / not loaded until used" | Import module or load object | Memory or load count for related Z | Z not loaded | Z loaded eagerly |
| 9 | "X has TTL of N seconds" ⚠ | Call X, wait N+ε, call again | Cache hit | miss | hit |
| 10 | "X respects rate limit R/min" | Call X (R+1) times within 1 minute | Response on the (R+1)-th call | 429 / throttle | 200 |
| 11 | "X is unique by field F" | Insert 2 rows with same F | DB rows after 2nd insert | constraint violation | 2 rows |
| 12 | "X retries up to K times before failing" ⚠ | Make X fail K-1 times | Final status | success on the K-th attempt | fail on the 1st attempt |
| 13 | "X is unaffected by Z" (independence) | Mutate Z | Y(X) | unchanged | changes |
| 14 | "X completes in < T ms" | Time X under realistic load | Wall ms | < T | ≥ T |
| 15 | "X is module-agnostic" (no hardcode) | grep code for module names from registry | match count | 0 in logic blocks | ≥ 1 |

When a new claim does not match these 15 → apply the core pattern and design a
custom (D, Y, Δ). Document the custom recipe in the spec acceptance_evals
under `recipe: custom · derivation: ...`.

**⚠ Feasibility caveats** for recipes with real-world constraints:

- **Recipe 9 (TTL)**: feasible only when `N` ≤ tolerable wait time (≤ 60 s realistic).
  TTL > 5 minutes → do NOT apply this recipe; instead use:
  - Time-travel (override the clock via `freezegun` / monkeypatch `time.time`).
  - Cache state introspection (`cache.get_stats()` if the store exposes one).
  - Tag the claim `[non-falsifiable-in-realtime]` and use eyeball review.
- **Recipe 12 (retry)**: requires fault injection — feasible only when:
  - The service has a test mode / chaos-mode flag, OR
  - The dependency can be mocked in isolation (DB connection, HTTP client), OR
  - The network namespace can be restricted (Linux `tc`, `iptables`).
  If none → tag `[non-falsifiable-without-fault-injection]`, fall back to
  recipe 14 (latency SLO) which measures tail latency instead of retry count.

ⓘ **Recipe 3 — `stack_envelope_floor` table** (irreducible overhead the cache cannot remove). **[approximate — calibrate per project]**: numbers below are community rules-of-thumb, NOT canonical. Recommend running a one-time `latency_floor_measure` baseline on the actual project before applying the threshold; save the result in `.agent-toolkit/perf_baseline.json`.

| Stack | stack_envelope_floor [approx] |
|---|---|
| HTTP/JSON-RPC (Odoo, Django REST, Rails Action) | ~80-150 ms (TLS handshake + JSON serialize + auth + middleware) |
| gRPC / Protobuf | ~5-15 ms |
| In-process function call (pure Python) | ~0.01-0.1 ms |
| Redis lookup (network) | ~0.5-2 ms |
| PostgreSQL connection-pool query | ~1-5 ms |

## Step-by-step decision algorithm

```
Input  : claim_text from spec or grill Q
Output : 1 perturb-test design, machine-runnable

1. PARSE claim — extract:
   · subject_X     (endpoint / function / model / decorator / field / RPC)
   · property_P    (BLOCK | cached | idempotent | atomic | guarded | ...)
   · param_set     (threshold N, key K, user U, ...)

2. MATCH recipe:
   for r in CATALOG:
     if r.claim_shape matches (P, X.kind):
       return r
   else:
     return CUSTOM (apply core pattern; document derivation)

3. INSTANTIATE (D, Y, Δ) with the project's concrete context:
   · D       — concrete perturbation (path to file, line, code block).
   · Y       — concrete observable (MCP probe / Playwright assertion / DB query).
   · Δ_P     — predicted delta if the claim holds.
   · Δ_NOT_P — predicted delta if the claim is refuted.
   · tolerance — jitter band (1.5 s for timing, 10% for count, exact for enum).
   · N_runs  — number of baseline + perturb repetitions (default 3 each).

4. SANITY — before showing to the user, self-check:
   · Can D run on dev DB? (does it break the `prod_db_write` invariant?)
   · Is Y deterministic under N_runs? (if not → unreliable; increase N or change Y)
   · Are Δ_P and Δ_NOT_P distinct by more than 3× tolerance? (if not →
     confusable; redesign)

5. EMIT into spec acceptance_evals (via `/eval-define` or `/eval-backfill`):
   - id: claim-<slug>
     story: "<spec story #>"
     recipe: <number>            # 1-15 from catalog, or "custom"
     perturbation:
       file: "<path>"
       inject: "<code snippet>"
       revert_strategy: "git checkout <file>"
     observable:
       tool: "<MCP tool>"
       args: {...}
     prediction:
       if_claim_holds: {delta: <value>, tolerance: <value>}
       if_claim_refuted: {delta: <value>}
     n_runs: 3
     smoke: pending
```

## Anti-patterns

| Wrong | Right |
|---|---|
| Hardcode "BLOCK / ASYNC" into the skill | Generic "P holds" / "NOT P" — the recipe table has 15 examples + derivation rule for custom cases |
| Hardcode endpoint / model name in the recipe body | Recipe body uses `<endpoint>` / `<model>` placeholders, instantiated from claim_text at parse time |
| Measure Y by querying the field the classifier writes (e.g. `rpc_role`) | DO NOT — that is circular. Y must be INDEPENDENT of the classifier (e.g. measure time-to-UI-mount via Playwright DOM, not via the dashboard read endpoint) |
| Inject D into a file outside `addons_path` (or equivalent for non-Odoo) | Before injecting, verify the file path is loaded by the running process (`grep` config / `ps` cmdline) |
| Run baseline + perturbation only once each | Minimum 3 runs per side, take the median — single-run jitter dominates |
| Forget to revert D | The pattern REQUIRES revert after Δ_measure; the agent self-verifies `grep PERTURB-TEST` is empty before STOP |
| Measure Y on prod DB | REFUSE; ask the user for dev/staging DB |

## Generalizability check

This skill must work for **≥ 3 claim shapes from different recipes** before merge.
The minimum regression set:

1. **Recipe 1 or 2** — BLOCK/ASYNC: perturb handler → observe UI mount.
2. **Recipe 3** — caching: 2 calls with same key → observe latency ratio.
3. **Recipe 4 or 5** — idempotency / determinism: repeat operation → observe side-effect count or output hash.

If any claim cannot match the pattern → refactor the recipe catalog (add a row)
OR tag the claim `[non-falsifiable]` in the spec — never force-fit into the
wrong recipe.

## Example template (recipe-agnostic)

Each spec `acceptance_eval` entry that applies a recipe must have this shape:

```yaml
- id: <kebab-slug>
  recipe: <1-15 | custom>
  claim: "<subject_X> has property <P>"
  perturbation:
    file: "<addons-path-relative>"
    inject: "<minimal code change>"
    revert_strategy: "<git checkout file | manual diff>"
  observable:
    tool: "<MCP tool | Playwright | Bash>"
    measure: "<specific signal>"
  prediction:
    if_claim_holds:   {<delta_name>: <value>, tolerance: <value>}
    if_claim_refuted: {<delta_name>: <value>}
  smoke: <pending | verified>
  smoke_result:                    # populated after run
    executed_at: "<ISO datetime>"
    baseline: <value>
    perturbed: <value>
    observed_delta: <value>
    verdict: "<CONSISTENT | REFUTED | PARTIAL: <reason>>"
```

**Project-specific case studies** (real runs on real data) live in
`.agent-toolkit/decision-log.md` (per-project ADRs) or in `[[reference_*]]`
memory — NEVER copy concrete numbers or endpoint names into the skill body.
The skill body must remain usable across any stack (Odoo / Django / Flask /
FastAPI / Spring / Rails).

## Integration

This skill is referenced FROM:

- `grill/SKILL.md` Q8 — the Falsifiability gate calls this skill to pick a recipe.
- `/eval-define` + `/eval-backfill` — pull perturb-test templates from the recipe catalog.
- `code-review` — when a code review flags a property claim (decorator, type hint), apply the matching recipe.
- `doubt-driven-review` — overlay after implementation; if a claim is doubted, run a perturb test to confirm.

## Sibling skills

- `grill` — phase 2; question Q8 (Falsifiability gate) triggers this skill.
- `doubt-driven-review` — verbal review; this skill is the machine-runnable counterpart.
- `verify-feature` — phase 5; runs the `acceptance_evals` that this skill emits.
- `<stack>-data-verification` — provides MCP probes for use as Y in recipes 3, 9, 11, 14.

## Reference

- Karl Popper falsificationism (1959) — "a claim that cannot be shown false also cannot be shown true".
- Property-based testing (Hypothesis, QuickCheck): perturb input → invariant must hold.
- ECC `eval-harness` + `agent-eval` — eval-driven development pattern.
- Per-project case studies live in ADRs (e.g. `ADR-006` for the current project). The skill body deliberately does NOT embed concrete numbers, to preserve generality.
