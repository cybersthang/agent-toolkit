---
name: grill
description: The user invokes `/grill` to be interviewed one-question-per-turn until the plan is clear enough to code. Cross-checks the current spec against `.agent-toolkit/decision-log.md` (ADR) + `.agent-toolkit/invariants.json` + the in-code glossary. This is phase 2 of the Vibe-flow (PLAN → **GRILL** → TDD → DEBUG). Open this skill WHEN the user says "grill me", "interview me", "stress-test the plan", "challenge me", "/grill".
---

# Grill — Vibe-flow Phase 2

> Purpose: a spec produced in PLAN always has fuzzy spots. The GRILL phase is
> NOT for the agent to "present the plan for approval" — it is the inverse:
> the user is interviewed one question at a time until every decision is
> settled, and only then does the IMPLEMENT phase open.

## When to apply

- The user types `/grill`.
- The user says "challenge me", "grill me", "I want to be grilled", "stress-test the plan".
- After `/plan`, the user replies "go grill".

## When to SKIP

- No spec yet at `.agent-toolkit/specs/<slug>.md` (run `/plan` first).
- The user says "just implement, skip grill" — respect that, open
  `spec-driven-feature` Phase 3 directly.
- Read-only questions ("how does X work") — not a grill; use
  `<stack>-<version>-codebase-discovery`.

## Interview contract

### Session start — preparation

1. **Load the current spec**: Read `.agent-toolkit/specs/<slug>.md`. If
   multiple drafts exist → ask the user which one ("3 specs are in draft:
   X, Y, Z. Grill which?").
2. **Load context**:
   - `.agent-toolkit/decision-log.md` — ADRs already settled; flag any user
     answer that violates an ADR.
   - `.agent-toolkit/invariants.json` — invariants currently enforced; do
     NOT ask a question an invariant already answers.
   - If `CONTEXT.md` exists at root or per-module → read the glossary.
3. **Print one line**: `Grill mode ON — spec: <slug> · ADRs loaded · ready.`

### Grill loop — until the user says "done"

Each agent turn contains exactly **ONE** question. Fixed format:

```
Q<N>: <specific, single-axis question>
  (a) **Recommended** — <option A> · Why: <one line>
  (b) <option B> · When this fits: <one line>
  (c) <option C, or "I'm not sure — you decide">

→ Reply (a)/(b)/(c) or type text. "go" = take Recommended. "done" = exit.
```

### Decision tree — depth-first, never jump

Each answer opens a sub-branch. Exhaust one branch before going back up to
the next branch. Do NOT ask question N+1 if N has not been answered.

### Must-challenge triggers

1. **Conflict with an ADR**: the user just said X but ADR-NNN says the
   opposite. Quote the ADR in the question: `ADR-002 settled "always use
   api.multi" — you're proposing api.model — do you want to supersede
   ADR-002?`
2. **Conflict with an invariant**: same, quote `invariants.json#<id>`.
3. **Ambiguous term per glossary**: if `CONTEXT.md` defines "cancellation" =
   X, but the user is using "cancel" for Y → ask for disambiguation.
4. **Concrete scenario test**: invent a specific edge case and ask "what
   happens if":
   - "Cron is running, server restarts — how is partial state handled?"
   - "User imports 50K rows — batched or single transaction?"
   - "Two users click at the same time — who wins?"
5. **Cross-reference code**: if the user says "module X does Y", search
   the code; if it doesn't match → flag.
6. **🛑 Hardcode proposal**: if the agent is about to propose a hardcode
   (literal string / regex literal / constant tuple / config mapping) →
   run through the "Anti-hardcode ladder" below BEFORE offering it as an
   option.
7. **🛑 Heuristic guess**: if the agent is about to answer / propose using
   patterns like "probably X", "usually X", "my guess is X" → REFUSE;
   replace with a deterministic algorithm per the "Anti-heuristic rule"
   below.
8. **🛑 Falsifiability gate** (REQUIRED for any classification / threshold /
   heuristic / "X is Y based on Z" answer): see the **Falsifiability gate**
   section below.

### 🛑 Falsifiability gate (required for every classification / threshold / rule)

> "A decision that cannot be shown wrong cannot be shown right" — Karl
> Popper. Applies to classifiers, thresholds, heuristics: if there is NO
> experimental way to refute, the answer is not yet good enough.

When the grill touches a decision shaped like:

- "Endpoint X is BLOCK / ASYNC / BG because <signal>".
- "Threshold N seconds to classify a request as slow".
- "Classify A vs B based on condition C".

The agent MUST ask one falsifiability follow-up *in the same branch* before
allowing the user to move to a different branch:

```
Q<N+1>: How can you prove that classification WRONG?
  (a) **Recommended — Perturb-test**: change one input dimension → the
      output must change in the same direction; if not, the classification
      is wrong.
      Concrete example for the case just settled:
        Inject `time.sleep(<latency>)` into the handler of X → measure
        time-to-<endpoint>.
        If X = BLOCK → time-to-UI must increase by ≥ <latency>.
        If X = ASYNC → time-to-UI must stay flat (± jitter).
  (b) **Diff-test**: run the classifier on 2 datasets (prod-like +
      adversarial) → compare results to a hand-derived ground truth.
      Count mis-classifications.
  (c) **No way to prove wrong** → roll back; the previous question is not
      yet settled; split it into a clearer rule (Layer 1+2 instead of
      hardcode).
```

If the user picks (c) → REVERT the previous question; do not apply
Recommended. An answer that cannot be falsified is not an answer.

**Persist the perturb-test design into spec frontmatter** under the
`acceptance_evals` key (use `/eval-define` or `/eval-backfill`). Each
question settled via the falsifiability gate → one machine-runnable eval probe.

**Workflow for question Q8**: the `claim-falsification` skill (same folder)
contains a 15-recipe catalog (claim shape → perturbation → observable →
predicted Δ). The agent MUST:

1. Parse `claim_text` from the answer the user just settled (subject_X, property_P, params).
2. Match a recipe (1-15 in the catalog) or derive a custom one via the core pattern.
3. Instantiate (D, Y, Δ_P, Δ_NOT_P) — do NOT hardcode an endpoint or property.
4. Self-check sanity (see `claim-falsification` step 4).
5. Emit the falsifiability question with options (a) recipe-matched / (b) custom / (c) non-falsifiable.

The recipe catalog covers: BLOCK/ASYNC (#1-#2), caching (#3, #9), idempotency
(#4), determinism (#5), atomicity (#6), permission (#7, #10), laziness (#8),
uniqueness (#11), retry (#12), independence (#13), latency (#14),
module-agnostic (#15) — full details in `[[claim-falsification]]`.

### Evidence bar (ECC code-reviewer pattern) for HIGH-stakes questions

A grill question is *HIGH-stakes* when the outcome will:

- Become an ADR / invariant (affects many files).
- Decide a classification used in production logging / dashboard.
- Lock a contract between two modules / processes.

For HIGH-stakes Q, each option (a)/(b)/(c) must include **3-part evidence**:

```
(a) Recommended — <option>.
    · Citation : `<file>:<line>` OR `ADR-NNN` OR `<URL>` — must NOT be empty.
    · Confidence: 0-100% (must be ≥ 80% to be marked Recommended).
    · Failure scenario: if this option is wrong, the concrete bug is
                        <input → state → outcome>.
```

If the agent does NOT have enough evidence to back 80% confidence on the first
option → do NOT mark it Recommended; replace with "I'm not yet sure — you
decide" + explain what the agent tried to verify.

### 🛑 Anti-hardcode ladder (required per ADR-005)

> "No hardcoding" does NOT mean banned; it means **hardcoding is the last
> resort**, allowed only after proving 3 dynamic layers infeasible.

When the grill touches a decision like "classify X" / "identify Y" /
"filter Z", the agent must walk the ladder in order, stopping at the first
feasible layer:

```
Layer 1 — INTROSPECTION (read runtime state):
  Can it be answered by reading an attribute / method signature / decorator /
  class hierarchy / instance type of the object in question?
  Example: classify RPC role by inspecting response status, content-type, body
  shape, control flow in the handler — NOT by URL match.

Layer 2 — SIGNAL from context (read sibling state in the same request/transaction):
  Can it be answered by observing surrounding signals — request headers,
  transaction state, sibling call, control flow before/after?
  Example: HTTP method, response status code, exception raised, timing
  pattern, call-stack depth.

Layer 3 — DECLARATIVE config (declared, contains no logic):
  Can it be split out into DECLARATIVE config — XML, YAML, ir.config_parameter,
  JSON schema — where the content describes "what", not "how"?

Layer 4 — HARDCODE (last):
  After confirming Layer 1+2+3 are infeasible → may propose hardcode. MUST:
    (a) Quote why dynamic is impossible — with evidence from code.
    (b) State cost-of-update — when a new case is added, where to edit, how
        many files.
    (c) Place the hardcode in EXACTLY ONE place, not scattered across files.
```

**Format inside the grill question**:

```
Q<N>: How is the request classified as ASYNC vs SYNC?
  (a) Recommended — Layer 1 (introspection): check response status (202 vs
      200) + body shape (empty vs JSON). Why: signal available at runtime,
      no endpoint-name dependency.
  (b) Layer 2 (context signal): inspect HTTP method + presence of
      Last-Modified header. When this fits: (a) misses queue.job patterns.
  (c) Layer 4 (hardcode) — list of URL substrings. Cost-of-update: every
      new endpoint requires editing `_FIRE_AND_FORGET_HINTS`. Why if chosen:
      Layer 1+2+3 all fail because <evidence>.
```

Layer 4 must always be in slot (c) or last, NEVER in slot (a) Recommended.
If the agent places hardcode at (a) → ADR-005 violation, the user may reject
the question.

### 🛑 Anti-heuristic rule (required per ADR-005)

> The algorithm must be deterministic: 10 runs with the same input must
> produce the same output. "Heuristic" in the sense of "best-effort guess"
> is BANNED in grill answers and in proposed implementations.

Distinctions:

| Allowed | Banned |
|---|---|
| **Algorithm**: "if A and B → X; if C → Y; else → fail" | **Heuristic**: "usually A → X" |
| **Rule-based pattern match**: exact regex → match/no-match | **Fuzzy match**: similarity score, threshold without justification |
| **State machine**: input transition → determined next state | **Probabilistic**: top-k candidates, pick the one that looks right |
| **Deterministic lookup**: hashmap with clear domain | **Best-effort guess**: "probably X based on experience" |

If the agent must offer a "guess" as an option (e.g. ML classify, fuzzy
search), it is the **last-resort fallback** and must:
- Be clearly marked `[non-deterministic]` in the Q.
- Be offered alongside a deterministic option marked Recommended.
- Require the user to explicitly choose the non-deterministic option before
  it is used.

**Self-check before printing Q**: "If this algorithm runs 10 times with the
same input, does it produce the same output 10/10?" If not → the Q is
wrong; refactor.

### When a decision is settled — update inline

- If the decision is a **new term** in the glossary → append to
  `<workspace>/CONTEXT.md` (create the file if missing).
- If the decision is **hard-to-reverse + surprising + has a real trade-off**
  → suggest the user run `/adr-add`. Do NOT auto-append an ADR.
- If the decision is a **must-keep / must-not-strip rule** → suggest `/inv-add`.
- All other decisions → update `.agent-toolkit/specs/<slug>.md` — move the
  item from "Open Questions" to "Implementation Decisions". Bump
  `last_updated`.

### End of grill

The user types "done" / "exit grill" → print the report:

```
Grill DONE. Spec updated: .agent-toolkit/specs/<slug>.md
  · Settled: <N> decisions
  · Promoted to ADR: <list ADR-NNN if any>
  · Promoted to invariant: <list inv-id if any>
  · Still TBD: <count of unresolved questions>

→ Next (Vibe-flow 5-phase, ADR-002):
   /go <slug>              Enable autonomy 4h → agent has free hand to IMPLEMENT.
                           Custom time: /go <slug> --until +8h | eod | tomorrow
   /spec-driven-feature    Full Tasks/Implement phase (safer, has gates).
   /tdd                    Toggle TDD auto-loop before coding.
```

Set spec frontmatter `status: grilled`.

→ STOP. Do NOT open the implement phase in the same turn. The user must type
`/go` (autonomy) or `/spec-driven-feature` (manual gate) in a follow-up turn.

## Auto-discover during grill

If a question can be answered by reading code → **read code, do NOT ask the
user**. Same rule as `clarification-gate` — the user must only answer
questions the user actually has the answer to, not questions the agent is
too lazy to research.

Wrong ✗: `Q: does model res.partner have an email field?` → one grep answers
this.
Right ✓: `Q: the email validator for partner email — strict (RFC) or lenient
(only requires @)?` — this is a business decision, not in the code.

## Anti-rationalizations

| Temptation | Counter |
|---|---|
| "Ask 5 questions at once for speed" | You lose the decision tree context. One question per turn is not overhead — it is discipline. |
| "The user said 'go', so I apply Recommended to everything" | "go" applies ONLY to the current question, not future ones. The next question still needs a separate reply. |
| "I can guess this question myself" | Then search code and confirm the assumption, do NOT ask. But do NOT skip — print one line "verified via <Read/Grep> ..." before moving on. |
| "After grill I'll just implement" | Wrong. The IMPLEMENT phase needs its own entry-point (spec-driven-feature or the user saying "go implement"). Grill ends → STOP. |

## Red flags — the skill is failing if

- The agent asks 2+ questions in the same turn.
- The agent does NOT quote an ADR/invariant in the question even when the
  user is violating one.
- The agent opens Edit/Write/Bash to mutate code during a grill turn.
- "Recommended" is missing a "Why".
- The spec file is not updated after a question is settled.
- The agent asks a question that grep would answer in under 5 seconds.

## Sibling skills

- `plan-feature` — phase 1, produces the spec used as grill input.
- `clarification-gate` — runs at the prompt level; grill runs at the
  decision level.
- `spec-driven-feature` — Tasks/Implement phase after grill is done.
- `doubt-driven-review` — overlay after implement to verify spec matches reality.
- `/adr-add` — promote a grill decision to an ADR.
- `/inv-add` — promote a must-keep rule to an invariant.
- `claim-falsification` — Q8 falsifiability gate uses its recipe catalog.

## Reference

Inspired by:
- [mattpocock/skills/productivity/grill-me](https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me) (MIT).
- [mattpocock/skills/engineering/grill-with-docs](https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs) (MIT).
- Domain-Driven Design context maps (Eric Evans).
