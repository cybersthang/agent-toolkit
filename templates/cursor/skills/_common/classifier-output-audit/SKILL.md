---
name: classifier-output-audit
description: Audit a classifier's actual outputs at scale (N tags emitted across M inputs) instead of testing one claim in isolation. Catches mis-tags that escape single-claim falsification because the bug only manifests on inputs the spec didn't anticipate. Generic for any subject that emits one-of-N labels — BLOCK/ASYNC tags, severity levels, fraud scores, intent labels, routing decisions, schema versions. Open this skill WHEN a feature under review is a CLASSIFIER (emits tags into a store) rather than a SINGLE PREDICATE.
---

# Classifier Output Audit — System-Wide Falsification

> **Why this exists** (formalized 2026-05-17, after live miss):
> A grill Q8 perturb-test can prove that ONE claim is right/wrong. It does
> NOT prove that the classifier is right on the OTHER N-1 inputs the spec
> didn't mention. Real bugs hide in the long tail: same code path, different
> input shape, different signal availability.

## When to apply

- The feature under review **emits tags / labels / scores at scale** (writes
  into a DB column, log line, dashboard cell, message attribute).
- The classifier has **multiple code paths** (A handles case X, B handles
  case Y, C is the fallback) — risk of signal drift between paths.
- During Grill — when the user has settled the classification rule and
  Q8 designed a perturb test, before exiting grill add Q9 (this skill).
- During Verify — when `feature_kind: classification` in spec frontmatter,
  Step 2 invokes this skill before designing User-Story probes.
- During Code-Review — when reading code that contains `role = '...'` or
  `tag = '...'` assignments inside a loop / per-row context.

## When to SKIP

- The feature emits exactly one prediction per call (single-shot
  classifier) — `claim-falsification` already covers it.
- Output store is write-only / append-only with no read-back path — cannot
  sample outputs without disturbing the system.
- Classifier is fully deterministic + pure (no env signals) — a unit test
  per branch already proves coverage; skip the runtime audit.
- Production-only system (no dev/staging) — never sample prod outputs in a
  way that side-channels user data.

## Core pattern

```
Given classifier C that maps input I → tag T ∈ {L1, L2, …, Lk}
and output store S = [(I_1, T_1), (I_2, T_2), …, (I_n, T_n)]:

  1. Enumerate the SIGNALS C may read         → S_signals.
  2. Enumerate the CODE PATHS that write T    → S_paths.
  3. Build the path×signal matrix             → flag rows with gaps.
  4. Sample K rows from S (K = max(10, sqrt(n))).
  5. For each sampled row:
       a. Re-derive T_expected from signals (independent of C's output).
       b. Compare T_expected vs T_actual.
       c. If mismatch → candidate for perturb-test.
  6. Group mismatches by (code_path, missing_signal) tuple.
  7. For the largest group → apply `claim-falsification` recipe.
  8. Emit findings: matrix + sample table + verdict per group.
```

## Step-by-step

### Step 1 — Enumerate signals + code paths

Read the classifier source. Identify:

- **All signals available** at classification time. Examples (abstract):
  `runtime_context_snapshot`, `paired_observation`, `temporal_boundary_event`,
  `external_marker_field`, `historical_aggregate`. List the data sources by
  name (not by project-specific labels) — e.g. *snapshot table*, *event
  log*, *adjacent record*, *config*, *header*.
- **All code paths** that write the tag. Use `grep` for the tag field
  literal in the codebase. Each assignment site is a path. Note:
  - Path's input shape (which records does it process?)
  - Signals the path reads (subset of `S_signals`).
  - Order of precedence within the path (first-matching wins, fallback,
    etc).

Output a markdown table:

```
| Path | Triggered when | Signals read | Default if no signal matches |
|---|---|---|---|
| A    | <condition>    | s1, s2       | tag = L_default              |
| B    | <condition>    | s1, s3, s4   | tag = L_default              |
| C    | <fallback>     | (none)       | tag = L_default              |
```

### Step 2 — Detect path/signal asymmetry

Read the matrix. **Flag a path whose signal set is a strict subset of
another path's signal set** (asymmetry). Example: A reads {s1, s2}, B
reads {s1, s2, s3} — A is missing s3. If both paths handle inputs of the
same kind, A will misclassify whenever s3 is the deciding factor.

Heuristic phrasing for the agent:

> "Path A and Path B both decide tag for record kind X, but B reads N
>  more signals than A. Inputs routed to A miss those signals — they fall
>  to the default. Likely false `L_default` for any record where the
>  missing signals are the deciding evidence."

This step alone catches a class of bugs *before* sampling — purely
static.

### Step 3 — Sample K outputs

Pull K rows from S, stratified by tag if possible:

```sql
-- SQL probe template (replace <store_table>, <tag_field>, <input_id>)
SELECT <input_id>, <tag_field>, <other_columns_helpful_for_signal_reconstruction>
FROM <store_table>
WHERE <recent_window>
ORDER BY random()
LIMIT <K>
```

For each tag value, include ≥ K/k samples (so rare classes aren't ignored).

### Step 4 — Re-derive T_expected per sample

For EACH sampled row, the agent must reconstruct `T_expected` using **all
S_signals** — NOT just the signals C happened to use in the path that
handled this row. The point is: would the FULL signal set classify it
differently?

Tools per signal kind:

| Signal kind                     | Probe tool                          |
|---------------------------------|-------------------------------------|
| Same-table column               | included in Step 3 SQL              |
| Adjacent record (FK, JOIN)      | follow-up SQL query                 |
| Persisted JSON sub-field        | `additional_info::json ->> 'key'`   |
| Endpoint-time computed field    | HTTP probe to the read endpoint     |
| Browser-side measurement        | Playwright `browser_evaluate`       |
| Empirical timing                | `claim-falsification` recipe 1/2/14 |

Produce a sample table:

```
| sample_id | T_actual | T_expected | Match? | Deciding signal (if mismatch) |
|---|---|---|---|---|
| 1         | L_A      | L_A        | ✓      | —                             |
| 2         | L_default| L_B        | ✗      | s3 (missing on path A)        |
| …         |          |            |        |                               |
```

### Step 5 — Group mismatches, escalate to perturb-test

Group rows where `Match? = ✗` by `(handled_by_path, deciding_signal)`.
The largest group is the strongest candidate for a real bug.

For that group:

1. Pick one representative row.
2. Construct a claim of shape:
   *"For inputs of kind K handled by path A, the classifier emits L_default
   but the deciding signal s3 says L_B."*
3. Invoke `[[claim-falsification]]` — match a recipe (typically recipe 1/2
   for behavioural tags; recipe 13 for "independence" claims; recipe 15
   for hardcode/module-agnostic).
4. Run the perturb-test. Verdict CONSISTENT/REFUTED.

### Step 6 — Emit findings (fixed shape)

```
## Classifier Audit Report — <classifier_name> · <ISO datetime>

### Path × Signal matrix
| Path | Signals read | Gap vs richest path |
|---|---|---|
| …    | …            | … (or "—")          |

### Sample audit (K = <n>)
| sample_id | T_actual | T_expected | Match? | Deciding signal |
|---|---|---|---|---|
| …         | …        | …          | …      | …               |

### Mismatch groups
1. (path=A, deciding_signal=s3): <count> mis-tags out of <K>.
   Perturb-test verdict: <CONSISTENT/REFUTED/PENDING>.
2. …

### Proposed fix
- Add s3 to path A's input set, OR
- Re-route inputs of kind K to path B, OR
- Mark inputs of kind K as `unknown` instead of forcing L_default.

### Verdict
- 🟢 Classifier accuracy ≥ <threshold>: ready.
- 🟡 Asymmetry detected but no mismatches in sample: refactor advisable.
- 🔴 Mis-tag rate > 5% on sample: BLOCKER, fix before release.
```

## Anti-patterns

| Wrong | Right |
|---|---|
| Sample only the recent / hot tag — misses cold-class regressions. | Stratify sample by tag (≥ K/k per class). |
| Re-derive `T_expected` using only the signals path A reads. | Use FULL signal set; that's how you find what path A is missing. |
| Skip the path×signal matrix; jump straight to sampling. | Matrix often shows the bug statically; sampling confirms blast radius. |
| Hardcode tag values, paths, or signal names into the skill. | Skill body must say `L_default`, `s1`, `path A`. Concrete names come from the project at runtime. |
| Treat one perturb-test pass as proof for the whole classifier. | One perturb proves ONE claim; this skill is the system-level wrapper. |
| Use the classifier's own read endpoint as Y (e.g. dashboard cell). | That is circular — measure Y from the underlying signal, NOT from the classifier output. |

## Generalizability check

This skill must work for **≥ 3 classifier shapes from different domains**
before merge into the toolkit. Minimum regression set:

1. **Behavioural tag** (e.g. "Y gates X" / "Y is fire-and-forget") —
   matrix lists timing signals; perturb-test uses recipe 1/2.
2. **Categorical label** (e.g. severity = low/med/high) — matrix lists
   numeric thresholds + override signals; perturb-test uses recipe 14.
3. **Identity / routing** (e.g. "record belongs to bucket B") — matrix
   lists membership signals; perturb-test uses recipe 13 (independence).

If a real classifier doesn't fit any of these → refactor the matrix
template (add a row for the new shape) instead of force-fitting.

## Integration

This skill is referenced FROM:

- `grill/SKILL.md` Q9 — after Q8 designs a single-claim perturb, Q9 asks
  "does this decision become a classifier emitting tags? if yes, run
  classifier-output-audit before exiting grill".
- `verify-feature/SKILL.md` Step 2 — when the spec frontmatter has
  `feature_kind: classification`, invoke this skill BEFORE the User Story
  probes so the audit findings feed the Verify Report.
- `code-review` — when the reviewer sees `role = '…'` / `tag = '…'`
  assignments inside per-row loops, this skill is the recommended deep-dive.
- `claim-falsification` — Step 5 of this skill delegates each mismatch
  group to a falsification recipe.

## Sibling skills

- `claim-falsification` — per-claim falsifiability (this skill is the
  N-claim wrapper).
- `grill` — Phase 2 design-time gate (Q8 single-claim, Q9 audit-shape).
- `verify-feature` — Phase 5 end-to-end gate; consumes this skill's
  findings in its Verify Report.
- `doubt-driven-review` — verbal review; this skill is the machine-runnable
  counterpart for classifiers specifically.

## Reference

- The pattern formalizes the empirical exercise of "sample the dashboard,
  cross-check each tag against the underlying signal, perturb where
  evidence disagrees". The bug pattern this catches: identical semantic
  decision computed via multiple code paths with asymmetric signal sets;
  the path with fewer signals silently emits the default for inputs whose
  deciding signal it cannot see.
- Per-project case studies (real run on real data) go to
  `.agent-toolkit/decision-log.md`, NOT into this body — the body stays
  generic.
