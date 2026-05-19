---
name: real-data-proof
description: Canonical workflow for "implement → analyze on REAL data → PROVE each result is correct via perturbation". Mandatory when a feature classifies, counts, distributes, or makes a behavioral contract claim about real production-shaped data. Forbids synthetic-only test data; forbids passive assertions ("count > 0"); requires falsification proof per label/claim. Open this skill WHEN the user says "count requests and classify", "prove tag is correct", "test on real data", "verify behavior of X", or after `/implement` finishes a feature that emits labels into a store.
---

# Real-Data Proof — Implement → Analyze → Prove

> **Why this exists**: a classifier can pass unit tests, pass a count probe,
> pass eyeball review, and still mis-tag inputs in production. The fix isn't
> more synthetic tests — it's **using real data + proving each tag is correct
> through perturbation**. This skill bundles the mandatory 4-step workflow
> for that pattern.
>
> **Canonical DEV example** (see `references/block-async-worked-example.md`):
> "count all requests of a user, classify each as BLOCK or ASYNC. To prove
> `init_message` is really BLOCK: inject `sleep()` into it — if the UI is
> forced to wait, it's BLOCK in truth. If sleep doesn't affect UI, ASYNC."
> This skill generalizes that pattern to any classify-and-prove feature.

## When to apply (MANDATORY)

This skill is **not optional** when any of these hold:

- The feature **emits tags / labels into a store** (DB column, JSON field,
  log line, dashboard cell). Examples: BLOCK/ASYNC, severity low/med/high,
  fraud score bucket, routing target, schema version, status code.
- The feature **counts or distributes** over a population (per-user, per-tag,
  per-time-window aggregate that has business meaning).
- The feature claims a **behavioral contract** about code under test
  (atomic, idempotent, cached, BLOCK/ASYNC, deterministic, guarded,
  TTL=N, retries=K, rate-limited).
- `/verify <slug>` is about to run on a spec whose `acceptance_evals` has
  any entry with `grader: data` or `grader: code` (i.e. the eval reads or
  classifies real data).

If `feature_kind: classification` is set in spec frontmatter, this skill
is **auto-invoked** by `verify-feature/SKILL.md` Step 1.8 (mandatory; NOT
deferred to manual judgment).

## When to SKIP

- Pure UI cosmetics (CSS, copy, layout) — no classification, no contract.
- Static config changes (toggle a flag, update a constant) — no data shape change.
- Schema migration that only renames a column — re-running existing
  acceptance_evals after the rename is enough.
- Production-only system with no dev/staging DB — refuse and tell DEV.
  We never sample or perturb prod data.

## The 4 mandatory steps

### Step 1 — Acquire REAL data (no synthetic-only)

Real data means: rows that exist in the dev/test/staging DB **because the
real application produced them**, not because a test fixture seeded them.

Acceptable sources (in order of preference):

1. **Anonymized production dump restored to dev DB** (best — same shape as
   prod). Cite source: dump filename + restore timestamp.
2. **Long-running dev DB used by the team for daily work** — has organic
   data accumulated by real (manual + scripted) usage.
3. **Mirrored staging DB** that integration tests + real users hit.
4. **Synthetic data** — ALLOWED only when steps 1-3 are infeasible (new
   feature, fresh DB) AND the synthesis script intentionally reproduces
   the realistic shape (cardinality, distribution, edge cases). Cite the
   script + the realism rationale.

**Forbidden**: a 3-row fixture that exercises only the happy path. The
agent must cite **why** the chosen source is representative.

#### Step 1.a — Auto-acquire the citation (REQUIRED, no manual paste)

Don't ask DEV to type the data-source line by hand. Discover it from
the live environment via these MCP probes (in this exact order — stop
at the first one that returns a meaningful value):

| # | Probe | What it answers | Citation format emitted |
|---|---|---|---|
| 1 | `mcp__postgres__run_query("SELECT current_database(), pg_size_pretty(pg_database_size(current_database())), inet_server_addr();")` | DB name + size + server host | `Data source: dev DB \`<name>\` (\`<size>\`) on \`<host>\``  |
| 2 | `mcp__postgres__run_query("SELECT min(create_date), max(create_date), count(DISTINCT user_id) FROM res_users WHERE login != 'admin';")` (or the equivalent on the target table identified in Step 2) | Time span + actor diversity proxy | append `· rows-window: <min_date>..<max_date> · distinct actors: <N>` |
| 3 | `Bash: stat -c '%y' .codex/last_restore.timestamp` (if the team writes a marker on `pg_restore` completion) | When the dump was loaded | append `· captured: <ISO>` |
| 4 | `mcp__codebase__read_file_chunk(".agent-toolkit/test_env.json")` (written by `/clarify` Step 5.5 when DEV pasted a URL) | The DEV-confirmed source | append `· DEV-confirmed: <url>` |

**Realism justification** is the only field that legitimately needs a
1-line judgement call by the agent (e.g. "peak+idle hours mix" /
"includes the bug-fix sprint timeframe"). Justify against the SAMPLE,
not against the source's brand name — "anonymized prod dump" alone is
not a realism claim, "prod dump containing the Black-Friday window
incident is" is.

If ALL four probes fail (no postgres MCP, no marker file, no
test_env.json) → emit `Data source: <NOT-DISCOVERABLE — agent must
ask DEV>` and STOP the workflow. Don't continue Step 2 against an
unknown population.

Output of Step 1 — a single line in the Real-Data Proof Report,
assembled from the probe outputs above:

```
Data source: <auto-discovered description> · rows: <N from Step 2 count> · captured: <ISO from probe 3 or current time> · realism: <agent 1-line justification>
```

### Step 2 — Analyze on real data (count + distribute, NOT eyeball)

Run the actual feature logic over the real-data population. Produce a
**distribution table**, not a single number.

For a classifier emitting tags T ∈ {L1, L2, …, Lk}:

```
| Tag      | Count | % of total | Sample input_ids |
|----------|-------|-----------|------------------|
| L1       | <n1>  | <p1>%     | <id1>, <id2>, …  |
| L2       | <n2>  | <p2>%     | <id3>, …         |
| <default>| <nd>  | <pd>%     | <id4>, …         |
```

For a count/aggregate feature: emit the per-group counts AND a sanity
range (min, max, median) so an unexpected value is visible.

For a contract claim ("X is atomic"): no distribution; jump straight to
Step 3 (perturb-test on a representative call).

**Why distribution, not single number?** A single count of "1 BLOCK + 9
ASYNC" doesn't tell you whether the 9 ASYNC are real or all defaulted.
The distribution + sample ids let you pick the perturbation candidates
in Step 3.

### Step 3 — Falsify each tag/claim with perturbation (PROOF, not assertion)

For each tag L_i in Step 2's table (or for the contract claim if not a
classifier), apply `[[claim-falsification]]` — pick a recipe from its
15-recipe catalog, design (perturbation D, observable Y, predicted Δ):

- **Behavioral tag** (BLOCK / ASYNC / synchronous / fire-and-forget):
  Recipe 1 or 2 — inject `sleep(N)` (or heavy-query / Playwright route
  delay) into a representative function tagged with that label; observe
  user-perceived UI completion signal via Playwright (NOT the classifier's
  own output column — that's circular).
- **Severity / category label**: Recipe 14 — measure the underlying SLO
  signal under realistic load and check the threshold the label depends on.
- **Identity / routing label**: Recipe 13 (independence) — mutate the
  signal the routing should NOT depend on; verify the label is invariant.
- **Caching claim**: Recipe 3 — two calls with same key, latency ratio.
- **Idempotency claim**: Recipe 4 — two calls same input, side-effect count.
- **Atomic claim**: Recipe 6 — inject exception mid-transaction, count
  partial rows.

**Forbidden as proof:**

- Counting tag instances ("there are 1 BLOCK and 9 ASYNC, ship it") — that
  proves the classifier *emitted* a tag, NOT that the tag is *correct*.
- Reading the classifier's own output store as Y — circular.
- Eyeball review of code ("looks BLOCK-y to me") — not falsifiable.
- A passing unit test with a hardcoded fixture — proves the unit, not the
  real-data behavior.

**Required as proof:** at least 1 perturb-test per distinct tag value.
If the population has 5 BLOCK and 100 ASYNC, run perturb on:
- 1 representative BLOCK row → predicted Δ = +N s wait
- 1 representative ASYNC row → predicted Δ = ≈ 0 s wait

Skipping the ASYNC perturb because "we already proved BLOCK works" is the
classic miss — a buggy classifier defaults ASYNC and *only* mis-tags one
specific case; without perturbing ASYNC, that's invisible.

### Step 4 — Emit Real-Data Proof Report

Fixed-shape report (must appear in the Verify Report):

```markdown
## Real-Data Proof — <feature-slug> · <ISO datetime>

### Data source
- <one-line: source, rows, capture timestamp, realism justification>

### Distribution (Step 2)
<distribution table from Step 2>

### Falsification (Step 3)
| Tag / Claim | Recipe | Sample input | Perturb (D) | Observable (Y) | Δ predicted | Δ measured | Verdict |
|---|---|---|---|---|---|---|---|
| BLOCK       | 1      | req_42       | sleep(5) in init_message | Playwright DOM idle ms | +5000 ± 500 | +5120 ms | ✅ CONSISTENT |
| ASYNC       | 2      | req_99       | sleep(5) in queue_message | Playwright DOM idle ms | ≈ 0 (< 200 ms) | +85 ms | ✅ CONSISTENT |
| <next tag>  | …      | …            | …                       | …                      | …            | …       | …             |

### Verdict
- 🟢 PASS — all tags proven consistent with their classification.
- 🟡 PARTIAL — <m>/<n> tags proven; <list> pending or non-falsifiable.
- 🔴 REFUTED — <list> tags failed perturbation; classifier needs fix before merge.

### Revert checklist
- [x] sleep(5) removed from init_message (`git checkout addons/foo/bar.py`)
- [x] sleep(5) removed from queue_message
- [x] grep PERTURB-TEST: 0 matches in repo
```

## Anti-patterns

| Wrong | Right |
|---|---|
| Test with 3 synthetic rows | Use real data; if must be synthetic, justify realism + cite generation script |
| Count tags → ship | Count + distribute + falsify each tag with perturbation |
| Falsify only BLOCK (the "interesting" one), skip ASYNC | Falsify each distinct tag value; default-leaning bugs hide in the boring one |
| Use the classifier's own output column as observable | Circular — observable must come from the underlying signal (UI mount, raw timing, DB row state) |
| Run perturb-test once, declare done | Minimum 3 baseline + 3 perturb runs per side; take median (jitter dominates single runs) |
| Forget to revert the injected sleep / fault | The 4th step's Revert checklist is MANDATORY; `grep PERTURB-TEST` must return 0 before STOP |
| Apply this on prod DB | REFUSE — never inject perturbations into prod paths. Always dev/staging |
| Hardcode "BLOCK/ASYNC" into this skill body | The skill body must stay generic — recipe catalog handles 15 claim shapes; project picks at runtime |

## Integration

This skill is referenced FROM:

- `verify-feature/SKILL.md` Step 1.8 — when `feature_kind: classification`
  is in spec frontmatter, this skill is **mandatory** (not deferred).
- `code-review/SKILL.md` Dimension 13/14 — when a review flags a
  classifier code change, attach a Real-Data Proof Report; without one
  the review verdict cannot be ✅ PASS for that finding.
- `clarify/SKILL.md` end-of-clarify — when the spec settles a classifier
  decision (Q9), the acceptance_eval row MUST cite this skill in
  `recipe: real-data-proof` so /verify auto-invokes it.
- `claim-falsification` — Step 3 of this skill delegates the per-tag
  perturbation design to that skill's recipe catalog.
- `classifier-output-audit` — orthogonal: that skill samples K rows to
  find *which* tags might be wrong (audit); this skill proves them
  right/wrong with perturbation. Run audit first to identify candidates,
  then real-data-proof to verify.

## Generalizability check

The skill must work for **≥ 3 different feature shapes** before being
considered stable. Minimum regression set:

1. **Behavioral classifier** — BLOCK/ASYNC, sync/async, atomic/non-atomic.
   Step 3 uses Recipe 1/2/6.
2. **Aggregate / count feature** — count_per_user, distribution by status.
   Step 2 emits the distribution + Step 3 falsifies the bucketing rule
   (Recipe 13/14/15).
3. **Contract claim on code** — "X is idempotent", "X retries K times",
   "X caches by Y". Step 1 still needs real callers / real data; Step 3
   uses Recipe 3/4/12.

If a real feature doesn't fit → tag the eval `[non-falsifiable]` in the
spec with a one-line rationale, never silently skip Step 3.

## When NOT enough

This skill proves the classifier is right on the population it has *seen*.
It does NOT prove it's right on inputs the production-shaped dataset never
exercised (rare classes, future input shapes, adversarial inputs). For
that:

- Run `[[classifier-output-audit]]` to enumerate signal × code-path gaps
  statically — catches a class of bugs without sampling.
- Generate stratified samples (≥ K/k per tag) so rare classes get proven too.
- Schedule a re-run periodically (cron job that rebuilds the report); a
  one-time proof at merge can become stale as data shifts.

## Red flags — the skill is failing if

- Data source is synthetic 3-row fixture without justification.
- Distribution table is missing (jumped straight to perturb-test without
  knowing population shape).
- Only the "interesting" tag was falsified; defaults un-perturbed.
- Y is the classifier's own output column (circular).
- Sleep / fault injection NOT reverted; `grep PERTURB-TEST` returns ≥ 1.
- Verdict cell is "looks right" or "should work" — must be CONSISTENT /
  REFUTED / PARTIAL with measured Δ in the row.
- Report applied on prod DB without dev/staging alternative explored.

## Sibling skills

- `claim-falsification` — per-claim recipe catalog (15 recipes); Step 3
  of this skill picks one per tag.
- `classifier-output-audit` — N-claim wrapper that samples a classifier's
  output store; run BEFORE this skill to find candidate mis-tags.
- `verify-feature` — Phase 5 end-to-end gate; this skill's report is
  embedded in the Verify Report when classifier features are present.
- `code-review` — Dimension 13/14 reviewers attach this report when
  approving classifier changes.
- `<stack>-data-verification` — provides MCP probes used in Step 2
  (real-data acquisition + distribution).

## Reference

- Karl Popper falsificationism — "a claim that cannot be shown false
  also cannot be shown true".
- See `references/block-async-worked-example.md` for a complete end-to-end
  walkthrough using the canonical DEV example (request classifier emitting
  BLOCK / ASYNC tags + sleep-injection proof).
- Per-project case studies (real runs) live in
  `.agent-toolkit/decision-log.md`, NOT in this body — the skill body
  stays generic across stacks.
