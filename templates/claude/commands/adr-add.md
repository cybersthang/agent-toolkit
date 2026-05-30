---
description: Append a new Architecture Decision Record to .agent-toolkit/decision-log.md. Use when the user makes a durable choice (technical, design, or process) that future agents need to honor.
allowed-tools: Read, Edit, Write, Bash
argument-hint: "[short-title]"
---

# /adr-add — Append a new ADR to the decision log

## Goal

Record WHY a decision was made, in a format the agent re-reads on every
session via the `session_brief` SessionStart hook. Decisions whose
mechanical enforcement is feasible get a matching `/inv-add` afterwards.

Argument: `$ARGUMENTS` — short title (kebab-case acceptable). If empty,
prompt the user.

## Steps

1. **Read existing decisions** — `Read .agent-toolkit/decision-log.md`.
   Find the highest existing `ADR-NNN` number; new ADR uses `NNN+1`
   padded to 3 digits.

2. **Confirm the decision is durable**, not a one-shot choice:
   - Will this rule apply to future similar situations? → YES → ADR.
   - Is this just an implementation detail for one PR? → NO → don't
     log; mention in commit message instead.
   - Does it contradict an existing ADR? → mark old one as
     `Superseded by ADR-NEW`, link both ways.

3. **Compose the entry** in this exact shape:

   ```
   ## ADR-NNN: <Title in sentence case>
   - **Date**: <today YYYY-MM-DD>
   - **Status**: Proposed | Accepted
   - **Context**: 1-3 sentences explaining the trigger / problem being
     solved. Include the user prompt that motivated the decision when
     possible (quote 1 line).
   - **Decision**: the rule, in declarative form. ONE sentence ideally.
   - **Enforcement**: invariants.json#<id> | code review | manual | none
   - **Consequences**: who/what is affected; trade-offs accepted; what
     becomes harder.
   ```

4. **Propose to user**, STOP, wait for `accept` / `change X` / `abort`.

5. **On accept** — `Edit` `.agent-toolkit/decision-log.md`:
   - Append the entry at the end of the file (after the comment marker
     "<!-- Add new ADRs BELOW this line ... -->").
   - Preserve trailing newline.

6. **If enforcement is "invariants.json#<id>"**, immediately run
   `/inv-add` to create the matching invariant. Don't leave the ADR
   "enforced" by a non-existent invariant — that's a lie.

7. **Report**: show the user the appended ADR + next-step suggestion
   (run `/inv-add` if applicable, else add a code-review checklist
   item if manual enforcement).

## Refuse / clarify when

- The "decision" is a personal preference (font size, terminal color)
  → not an ADR.
- The decision contradicts an `Accepted` ADR without acknowledging it
  → ask the user to confirm supersession explicitly.
- Status `Proposed` for >7 days without follow-up → during `/inv-list`
  or `/inv-add`, surface the stale proposal.

## What NOT to do

- Do NOT rewrite or edit existing ADRs in-place (decision log is
  append-only). To change an ADR, append a new one marked `Superseded by`.
- Do NOT skip the WHY ("Context") section — that's the entire point.
- Do NOT auto-create invariants without user approval, even if
  enforcement field says invariants.json#X. Run `/inv-add` as a
  separate STOP-gated step.
