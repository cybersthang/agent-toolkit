---
name: independent-review
description: Spawn a FRESH-CONTEXT reviewer sub-agent at the done-boundary to catch blockers the same-context review misses. Open this skill when the independent_review_gate nudges/blocks a done-claim, or when DEV runs /review-independent. The reviewer sees ONLY a code-assembled context packet (diff + spec + acceptance_evals + invariants) — never the implementer's reasoning — and is prompted to REFUTE each diff hunk. Confirmed BLOCKERs feed .open_gaps.json so the gap gate forces fixes; loop converges on 0-BLOCKER with hard caps so it never runs forever. Pairs with tools/independent_review.py + independent_review_gate.py.
---

# Independent Review — fresh-context sub-agent at the done-boundary

> **Fresh-context, NOT absolute-independent (ID-14).** A code-assembled packet
> bounds the reviewer's input; it cannot stop you from pasting extra context.
> So: pass ONLY the packet path. The gate verifies packet-sha consumed +
> packet-size tolerance — but honesty: independence is defense-in-depth.

## When this fires
1. **Auto (gate-driven, no DEV command):** `independent_review_gate` (Stop)
   detects done-boundary by STATE (spec `status: verified` + tasks done +
   feature-scope diff; ID-16) and blocks/nudges the done-claim until a valid
   review artifact matches the current review-sha. You then run this skill.
2. **Manual:** DEV runs `/review-independent <scope>` (early / re-review / PR).

## Procedure
1. **Build the packet (code-assembled, ID-2/ID-14):**
   `python3 tools/independent_review.py emit-context <spec-slug>` → prints
   `packet_sha` + `packet_path`. Do NOT hand-curate the packet.
2. **Spawn the reviewer (Task tool), ONE sub-agent (MVP reviewer_count=1):**
   - Prompt = ONLY: "Read `<packet_path>`. Review ONLY from this packet.
     **Default-skeptic — try to REFUTE each diff hunk; do NOT assume the
     implementer was right (ID-15).** Emit findings in the schema below.
     The packet_sha is `<packet_sha>` — echo it in your first line. As your
     FINAL line emit exactly `REVIEW-VERDICT: <packet_sha> PASS` (if 0 confirmed
     BLOCKERs) or `REVIEW-VERDICT: <packet_sha> FAIL` (if ≥1)."
   - Do NOT include your implementation reasoning. The packet_sha echo is how
     the gate proves the sub-agent consumed the packet (ID-12); the
     `REVIEW-VERDICT` line is how the gate reads the verdict from the REVIEWER
     (F4.2) instead of trusting a main-agent-written artifact.
   - Reviewer may Read at most `max_reads_per_round` (config) extra files; over
     cap → conclude with note `context-limited` (ID-19).
3. **Finding schema** (reviewer returns):
   ```
   - severity: BLOCKER | MEDIUM | LOW
     file: path:line
     claim: <what is wrong>
     Proof: <trigger → observable failure, cite path:line>
     Doubt-pass: <strongest doubt + how refuted, or "unknown">
   ```
4. **Verify each BLOCKER before it forces a fix (ID-21 — anti-hallucination):**
   a BLOCKER must be reproducible/provable by file:line + concrete mechanism.
   Cannot prove → **downgrade to MEDIUM** (report, do NOT force a fix). This
   stops a hallucinated BLOCKER from causing a fix that introduces a real bug.
5. **Feed confirmed BLOCKERs (ID-6) →** append to `.agent-toolkit/.open_gaps.json`
   (status open) so `gap_completeness_gate` forces fix-or-defer. Write verdict +
   round + blocker_fingerprints to `.agent-toolkit/.independent_review.json`
   keyed by review_sha. **(F4.2: this artifact is the main agent's record — the
   gate now ALSO reads the reviewer's own `REVIEW-VERDICT` line; if the artifact
   says `pass` but the reviewer transcript says `FAIL`, the gate treats it as a
   forged verdict and blocks. Do NOT write `pass` over a reviewer FAIL.)**
6. **Fix → re-review (incremental, ID-5):** fix BLOCKERs; re-run emit-context
   (new review-sha) and re-review ONLY the fix-diff + re-test prior BLOCKERs.

## Convergence — never loops forever (ID-4/ID-20/ID-27)
- **Converge on 0-BLOCKER** (MEDIUM/LOW are reported, not blocking).
- **non_progress_streak (default 3):** N consecutive rounds where a finding
  re-appears (same fingerprint) OR a new BLOCKER lands INSIDE the just-fixed
  diff (= regression) → escalate.
- **absolute_round_ceiling (default 5):** hard cap even when each round surfaces
  a genuinely NEW blocker in a different area (legit deeper issue, NOT counted
  as non-progress) → escalate at the ceiling regardless.
- **Escalate = DEV decides** via `gap-cant-fix: <reason>` (existing tier). The
  loop ALWAYS terminates: 0-BLOCKER (pass) or escalated.

## Token discipline (ID-5/ID-19)
diff-only packet · sha-cache (review-sha unchanged → `cached`, skip spawn) ·
incremental re-review · single reviewer (model `inherit` MVP; multi-lens +
cheaper-model = Phase 2) · skip-trivial (diff ≤ skip_trivial_loc / no
feature-scope file → gate verdict `skipped`).
