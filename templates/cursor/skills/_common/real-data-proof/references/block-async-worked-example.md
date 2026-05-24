# Worked Example — BLOCK / ASYNC Classifier on Real Request Data

> Concrete end-to-end walkthrough of the canonical DEV pattern. Use this
> as the template when applying `real-data-proof/SKILL.md` to a behavioral
> classifier. Adapt names + paths to the current project; the workflow
> shape is invariant.

## The DEV's request (verbatim, paraphrased)

> "Count every request a selected user has made. Classify each request as
>  BLOCK or ASYNC. After implementing, use real data to prove each tag is
>  correct. Example: `init_message` is tagged BLOCK — prove it by
>  injecting `sleep()` into the function. If the UI truly has to wait, it
>  IS BLOCK. If you inject sleep into a function tagged ASYNC and the UI
>  is unaffected, it IS ASYNC."

This is shape-canonical: classifier emits N labels into a store, agent
must prove each label is right on real data — not just count, not just
eyeball.

---

## Step 1 — Acquire REAL data

Find the data source — whichever table or log your framework writes
HTTP / RPC traffic to (Odoo `ir_logging` + `<addon>_request_log`,
Django `django.request` + custom audit table, Rails `production.log` +
ActiveRecord audit, etc.). The SQL below assumes a Postgres-shaped
audit table; swap to your stack's equivalent.

```sql
-- Confirm the request log table exists and has organic data
SELECT count(*) AS n_rows,
       min(create_date) AS first_request,
       max(create_date) AS last_request,
       count(DISTINCT user_id) AS distinct_users
FROM <request_log_table>
WHERE create_date > now() - interval '30 days';
```

**Acceptable result**: ≥ thousands of rows, ≥ 10 distinct users, span ≥ days.

**Unacceptable**: 3 rows from a fixture. STOP — restore anonymized prod
dump or run the app manually for a few hours to generate organic data.

**Report line** (goes into the Real-Data Proof Report):

```
Data source: anonymized prod dump 2026-05-15.sql restored 2026-05-18
            · rows: 18 427 requests over 14 days · 23 distinct users
            · realism: same shape as prod; includes peak hours + idle
              hours + admin + ops actor mix
```

---

## Step 2 — Analyze on real data (count + distribute)

Pick a representative user (one with diverse activity):

```sql
-- Pick the user with the most varied function-call footprint
SELECT user_id,
       count(DISTINCT method_name) AS distinct_methods,
       count(*) AS total_requests
FROM <request_log_table>
WHERE create_date > now() - interval '30 days'
GROUP BY user_id
ORDER BY distinct_methods DESC, total_requests DESC
LIMIT 1;
-- Suppose returns user_id = 4711 with 42 methods, 1 230 requests.
```

Apply the classifier to that user's requests; emit a distribution:

```sql
-- Run the classifier (now implemented as a stored function or Python loop)
-- and tabulate by tag.
SELECT request_role_tag AS tag,        -- the column the classifier writes
       count(*) AS n,
       round(count(*) * 100.0 / sum(count(*)) OVER (), 1) AS pct,
       string_agg(DISTINCT method_name, ', ' ORDER BY method_name) AS methods
FROM <request_log_table>
WHERE user_id = 4711
  AND create_date > now() - interval '30 days'
GROUP BY request_role_tag
ORDER BY n DESC;
```

Example output (real shape, not contrived):

```
| Tag    | Count | %     | Methods (sample)                              |
|--------|-------|-------|-----------------------------------------------|
| BLOCK  | 412   | 33.5% | init_message, render_form, get_user_info      |
| ASYNC  | 798   | 64.9% | queue_message, schedule_report, fire_webhook  |
| default| 20    | 1.6%  | unknown_endpoint, _bogus_test_method          |
```

**Sanity reads** before continuing:

- Are there ANY rows in the `default` bucket? → either un-tagged real
  methods (potential bug) or noise (e.g. test endpoints). Note them.
- Is the BLOCK/ASYNC ratio plausible vs. the spec? E.g. spec says "most
  user-driven HTTP routes should be BLOCK" — a 5 / 95 split is a red flag.
- Are any methods listed under BOTH tags across different rows? That means
  the classifier is non-deterministic — STOP, fix before perturb.

---

## Step 3 — Falsify each tag with sleep-injection

Pick one representative sample per tag value. We need ≥ 1 BLOCK and ≥ 1
ASYNC proof. If `default` had non-zero count, ≥ 1 default proof too.

### 3a — Prove BLOCK: `init_message`

**Claim**: `init_message` is BLOCK → injecting `sleep(N)` into its body
should add N seconds to the user-perceived UI completion time on the
endpoint that calls it.

**Perturbation (D)** — edit the function file, mark with a sentinel so we
can grep-revert later:

```python
def init_message(self, *args, **kwargs):
    import time; time.sleep(5)  # PERTURB-TEST real-data-proof remove
    ...existing body...
```

**Observable (Y)** — Playwright on the real UI route that triggers
`init_message`. Measure `domcontentloaded` or a UI-ready beacon. NEVER
read `request_role_tag` itself (circular).

**Baseline + perturb** — 3 runs each, take median:

```bash
# baseline (no sleep): record DOM-ready ms × 3
# patch in sleep(5)
# perturbed runs: record DOM-ready ms × 3
# revert
```

Example real numbers:

| Run | Baseline (ms) | Perturbed (ms) |
|-----|---------------|----------------|
| 1   | 480           | 5 510          |
| 2   | 510           | 5 480          |
| 3   | 470           | 5 520          |
| **median** | **480**    | **5 510**      |

Measured Δ = 5 510 − 480 = **+5 030 ms**.
Predicted Δ_BLOCK = +5 000 ± 500 ms. **CONSISTENT ✅**

If measured Δ ≈ 0 (UI unchanged): the classifier is WRONG — `init_message`
is in fact ASYNC despite the tag. BLOCKER: fix the classifier or the call
site before merge.

### 3b — Prove ASYNC: `queue_message`

**Claim**: `queue_message` is ASYNC → sleep(5) inside it should NOT add
~5 s to the user-perceived UI time, because the user-visible action
doesn't await the message-queue write.

**Perturbation (D)**:

```python
def queue_message(self, *args, **kwargs):
    import time; time.sleep(5)  # PERTURB-TEST real-data-proof remove
    ...existing body...
```

**Observable (Y)** — same: Playwright `domcontentloaded` on the UI route
that fires `queue_message`. Also assert the message eventually appears
in the queue store (so we know the function ran).

**Baseline + perturb** — 3 runs each:

| Run | Baseline (ms) | Perturbed (ms) | Message in queue? |
|-----|---------------|----------------|--------------------|
| 1   | 320           | 355            | yes, ~5 s later    |
| 2   | 290           | 410            | yes, ~5 s later    |
| 3   | 310           | 380            | yes, ~5 s later    |
| **median** | **310** | **380**        | always yes         |

Measured Δ = 380 − 310 = **+70 ms** (within jitter, ≪ 5 s).
Predicted Δ_ASYNC ≈ 0 (< 200 ms tolerance). **CONSISTENT ✅**

If measured Δ had been ≈ 5 000 ms: classifier WRONG — `queue_message` is
in fact BLOCK. BLOCKER.

### 3c — Investigate `default` tag bucket (1.6 %)

Sample one row:

```sql
SELECT method_name, endpoint, payload
FROM <request_log_table>
WHERE user_id = 4711 AND request_role_tag = 'default'
LIMIT 1;
-- Returns: method_name = 'unknown_endpoint'
```

For each method in the `default` bucket: either (a) it's a known method
the classifier missed — file as BLOCKER finding (mis-tag), or (b) it's
truly an unknown / test method — file as LOW (telemetry noise, not user
impact).

Don't skip this — `default` bucket is where bugs hide.

---

## Step 4 — Emit Real-Data Proof Report

Final report shape — embedded in the Verify Report:

```markdown
## Real-Data Proof — request-block-async-classifier · 2026-05-19 14:30 +07:00

### Data source
- anonymized prod dump 2026-05-15.sql restored 2026-05-18
  · 18 427 requests · 23 users · 14-day window · realism: peak+idle+ops mix.

### Distribution (user_id=4711, 30-day window)
| Tag    | Count | %     | Sample methods                                |
|--------|-------|-------|-----------------------------------------------|
| BLOCK  | 412   | 33.5% | init_message, render_form, get_user_info      |
| ASYNC  | 798   | 64.9% | queue_message, schedule_report, fire_webhook  |
| default| 20    | 1.6%  | unknown_endpoint                              |

### Falsification (sleep(5) injection, Playwright DOM-ready Y, 3+3 runs)
| Tag    | Sample method     | Δ predicted     | Δ measured | Verdict       |
|--------|-------------------|-----------------|------------|---------------|
| BLOCK  | init_message      | +5 000 ± 500 ms | +5 030 ms  | ✅ CONSISTENT |
| ASYNC  | queue_message     | ≈ 0 (< 200 ms)  | +70 ms     | ✅ CONSISTENT |
| default| unknown_endpoint  | (investigation) | mis-tag of `set_pref` confirmed | 🔴 REFUTED |

### Verdict
- 🟡 PARTIAL — 2/3 tags PASS; `default` bucket contains 1 confirmed mis-tag
  (`set_pref` should be ASYNC). BLOCKER for merge: fix classifier rule
  before /verify approves the spec.

### Revert checklist
- [x] sleep(5) removed from init_message (verified: `git diff` clean)
- [x] sleep(5) removed from queue_message (verified)
- [x] `grep -r 'PERTURB-TEST real-data-proof'` returns 0 matches
```

---

## Adapting this template to other classifier features

The shape is invariant — only the labels and the perturbations change:

| Feature shape           | What changes per step                                              |
|-------------------------|-------------------------------------------------------------------|
| Severity = low/med/high | Step 3 uses `claim-falsification` Recipe 14 (load-vs-SLO), not Recipe 1/2 |
| Status = ok/warn/error  | Step 3 injects a failure → expects label flip per threshold       |
| Routing target = A/B/C  | Step 3 uses Recipe 13 (independence) — mutate non-deciding signal, label invariant |
| Caching claim           | Step 3 uses Recipe 3 — two calls same key, latency ratio          |
| Idempotency claim       | Step 3 uses Recipe 4 — two calls same input, side-effect count    |
| Atomic claim            | Step 3 uses Recipe 6 — inject mid-tx exception, count partial rows |

For any of these: Step 1 (real data) and Step 2 (distribution) and Step 4
(report shape) are **unchanged**. Only Step 3's perturbation recipe rotates.

---

## What NOT to do

- ❌ "We have unit tests, no need for this" — unit tests prove the rule;
  this skill proves the rule applies to **real shapes** the unit fixture
  never saw.
- ❌ "BLOCK was already proven last week" — re-run on the latest data.
  Classifier behavior drifts as code changes, even when the rule hasn't.
- ❌ "Only perturb the ambiguous tag" — buggy defaults hide in the
  boring (un-perturbed) buckets. Every distinct tag value gets ≥ 1 proof.
- ❌ "Sleep didn't move the dial, must be measurement error" — increase
  N (sleep 30 s if needed). If still no movement on a BLOCK claim → the
  tag is wrong, not the measurement.
- ❌ "We'll revert the sleep after stand-up tomorrow" — revert
  **immediately**. The 4th-step grep MUST be clean before STOP. Forgotten
  perturbations land in prod.
