---
name: doubt-driven-review
description: Adversarial verification overlay for any review/audit/answer. Forces a CLAIM → EXTRACT → DOUBT → RECONCILE → STOP pass so findings, recommendations and "facts" are stress-tested before they reach the user. Open this skill whenever you are about to ship a non-trivial finding, a refactor recommendation, a "this is the root cause" claim, or any answer the user will act on.
---

# Doubt-Driven Review — Adversarial Self-Check

> The default failure mode is overconfidence: the agent (or audit sub-agent)
> writes a plausible-sounding claim that does not actually trace back to the
> code. This skill is the antidote: every claim is treated as a hypothesis
> until it is independently verified against the source.

Pair this skill with `code-review` (severity rubric + proof contract) and
the stack-specific data-verification skill (live-MCP checks — see "Intent →
Skill routing" in `AGENTS.md`). On its own it is a methodology, not a
checklist.

## When to apply

- About to send a BLOCKER/MEDIUM finding.
- About to recommend deletion, refactor, schema change, or migration.
- About to state a "root cause" for a bug.
- About to answer a question that the user will act on without re-reading the code.
- Re-reading an output produced by an audit sub-agent before showing it to the user.

## When NOT to apply

- Pure file-listing / discovery / read-only inspection requests.
- Trivial code edits the user has spelled out line-by-line.
- Conversational replies that don't make a verifiable claim.

## Five-step loop — apply per finding, not once per session

### 1. CLAIM
Write the claim in one sentence. If you cannot, the finding does not exist
yet — abort and re-read the code.

> Example: "The cron job in `worker.py:42` silently dies on the first DB
> outage because the `while True` body is not wrapped in `try/except`."

### 2. EXTRACT
List, in `path:line` form, the **exact evidence lines** that, if absent or
different, would invalidate the claim. No prose, just refs.

> - `worker.py:42` — `while True:` loop body
> - `worker.py:48-52` — DB call with no surrounding try
> - `worker.py:60` — exit path

The extract list must be small (1–6 refs). If you need 10+ refs to support
one claim, you are conflating multiple findings — split them.

### 3. DOUBT
Generate at least three plausible reasons the claim is wrong. Write them
explicitly; do not skip "I'm sure already".

Mandatory probes:
- **Hidden handler.** Is there a decorator, base class, or `signal.signal`
  wrapper that catches the exception elsewhere? Grep before claiming
  "uncaught".
- **Version drift.** Does this file actually run, or is it shadowed by an
  override in another addon / branch / patch? Verify the active import path.
- **Spec mismatch.** Re-read the user's request: is the claim answering
  *their* question, or is it a tangent the agent found interesting?
- **Stale audit-agent quote.** If a sub-agent wrote the original finding,
  re-read the cited lines yourself — agents paraphrase.

### 4. RECONCILE
For each doubt, either:

- **Refute the doubt with a fresh code read** (cite `path:line`), or
- **Demote the finding** (BLOCKER → MEDIUM → LOW → drop) when the doubt
  survives, or
- **Mark Unknown** and emit a one-line question to the user instead of a
  finding. "Unknown" is an acceptable result — "I checked but couldn't
  prove it" beats a false positive every time.

### 5. STOP
After RECONCILE, the finding is either (a) verified with proof line, (b)
demoted with rationale, or (c) replaced by a user question. Do not loop
back to polish. The temptation to keep adding hedges is the same impulse
that produced the original overconfident claim.

## Output contract

When this skill is active, every finding in the report carries a
`Doubt-pass:` line in addition to the standard `Proof:` line:

```
### [SEVERITY] #<id>: <title>
- File: <path>:<line>
- Proof: <one-sentence trigger → failure trace>
- Doubt-pass: <one-sentence summary of the strongest doubt + how it was refuted, OR "demoted from X because <doubt survived>", OR "unknown — user question filed below">
- Fix idea: <one-two sentences>
```

A finding without `Doubt-pass:` did not run through this skill — strip it
or run the loop.

## Rationalizations table (counter-argue each one)

| Rationalization | Counter-argument |
|---|---|
| "I just read the code, I don't need to doubt it again" | Reading does not equal verifying. The point of the loop is to make the *negative* case explicit — what evidence would disprove this? If you can't articulate it, you haven't actually verified. |
| "Three doubts is overkill for an obvious bug" | The visible bugs are not the problem. The doubt loop is calibrated for the *non-obvious* finding that "looks right" — applying it only to hard cases is selection bias. Always run it; cheap on easy cases, life-saving on hard ones. |
| "The audit sub-agent already verified it" | Sub-agents overstate. They produce plausible English that maps to citation-shaped strings, not code. Re-read the cited lines in this conversation. |
| "Marking Unknown looks weak — I should just commit to BLOCKER or LOW" | Unknown is a feature, not a weakness. It converts an unverified guess into a question the user can answer in one line, which is faster and more useful than a wrong claim the user has to refute. |
| "Doubt loop will slow the review down" | Drip-feeding mediums across three sessions is slower. One slow, calibrated pass beats three confident-but-wrong passes. See `feedback_exhaustive_analysis`. |

## Red flags — the skill is failing if any are true

- A finding has no `Doubt-pass:` line.
- The DOUBT step produced fewer than three plausible refutations.
- RECONCILE refuted every doubt with the same source line as the original
  proof (circular — needs an *independent* read).
- "Unknown" never appears in a long report (statistically improbable — you
  are converting unknowns into false certainties).
- A sub-agent's wording was copied into the final finding verbatim without
  the agent re-reading the cited code.
- The original CLAIM was edited mid-loop to dodge a surviving doubt. (If
  the claim changes, the loop restarts.)

## Worked micro-example

```
CLAIM: `models/timer.py:118` mixes ms and ns in the drift formula:
       drift = elapsed_ms - elapsed_ns (units mismatched, silently wrong).
EXTRACT:
  - models/timer.py:118 (subtraction site)
  - models/timer.py:34  (elapsed_ms assignment, units in name)
  - models/timer.py:96  (elapsed_ns assignment, units in name)
DOUBT:
  - 1. Is elapsed_ns actually nanoseconds, or is the name lying?
  - 2. Is one of them converted somewhere between line 34/96 and 118?
  - 3. Is drift only used as a sign indicator, in which case the unit
       mix is irrelevant?
RECONCILE:
  - 1. Refuted: time.monotonic_ns() at line 96 is documented ns.
  - 2. Refuted: grep "elapsed_" in file returns 4 hits, none convert.
  - 3. Survived: drift is later compared to a *threshold in ms* at
       line 142 — bug is real, magnitude is enormous (1e6× error).
STOP. Finding stands as BLOCKER. Doubt-pass: "Doubt 3 survived;
threshold comparison at :142 confirms the unit mix is load-bearing,
not cosmetic."
```

## Sibling skills

- `code-review` — owns severity rubric + proof contract this skill extends.
- `<stack>-code-review` — framework overlay on `code-review` (e.g. `odoo-code-review`).
- `<stack>-<version>-data-verification` — live-MCP verification used during RECONCILE (e.g. `odoo-12-data-verification`).
- `<stack>-<version>-deterministic-answers` — canonical decisions cited during EXTRACT for "how do we do X" claims.
