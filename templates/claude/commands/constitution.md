---
description: Amend the project constitution at `.agent-toolkit/constitution.md` — add/revise/remove a project-wide principle, then propagate the change into ADR + invariants when applicable. Use when a durable principle is being established or contradicted.
allowed-tools: Read, Edit, Write, Bash
argument-hint: "[amendment-title]"
---

# /constitution — Amend the project constitution

## Goal

Keep `.agent-toolkit/constitution.md` accurate over the project's lifetime
without re-litigating principles every session. The constitution is the
ONE file every spec-driven session loads before writing code; amending it
is therefore slow + ceremonial on purpose.

Inspired by [github/spec-kit's `/speckit.constitution`](https://github.com/github/spec-kit/blob/main/templates/commands/constitution.md) (MIT — Copyright (c) 2024 GitHub, Inc.).
Adapted to the agent-toolkit two-tier model (constitution + ADR +
invariants) — semver dropped, sync targets refocused on the toolkit's
own runtime artifacts.

Argument: `$ARGUMENTS` — short amendment title (kebab-case acceptable).
If empty, prompt the user.

## Steps

1. **Read current constitution** — `Read .agent-toolkit/constitution.md`.
   - Surface each top-level section heading (`## I.`, `## II.`, …) so
     the user can pick which one is being amended (or "add new section").
   - Identify the latest `Amendment N:` heading (if any) at the bottom;
     new amendment uses `N+1`.

2. **Classify the amendment**:
   - `add` — a new principle is being introduced.
   - `revise` — an existing principle's wording is clarified WITHOUT
     changing the rule.
   - `supersede` — an existing principle's rule is changed (the old one
     is contradicted); the old text must be quoted + marked as such.
   - `remove` — a principle no longer applies.

3. **Confirm the amendment is durable**, not session-scoped:
   - Will this rule apply to future similar situations across multiple
     specs? → YES → constitution-worthy.
   - Is this a one-off implementation choice? → NO → use `/adr-add`
     (ADR-only) or `/inv-add` (invariant-only) instead.

4. **Cross-check against existing artifacts**:
   - `Read .agent-toolkit/decision-log.md` — does an existing ADR
     already cover this? If yes, the amendment cites that ADR; if no,
     a matching ADR MUST be created in step 6.
   - `Read .agent-toolkit/invariants.json` — is the new principle
     mechanically enforceable (regex / call-site pattern)? If yes, a
     matching invariant SHOULD be created in step 6.
   - `Read .codex/canonical_decisions.json` — does the amendment
     contradict a canonical answer? If yes, the canonical entry MUST
     be updated in lockstep (or the amendment rejected).

5. **Compose the amendment block** in this exact shape (append to the
   end of `constitution.md`, BEFORE the trailing `Last revised:` line):

   ```
   ## Amendment N: <Title in sentence case>
   - **Date**: <today YYYY-MM-DD>
   - **Type**: add | revise | supersede | remove
   - **Section affected**: `## <Roman numeral. Section name>` (or "new section: …")
   - **ADR**: ADR-XXX (cite the WHY; required for `add` / `supersede` / `remove`)
   - **Invariant**: invariants.json#<id> (if mechanically enforced) | none
   - **Old text** (only for `supersede` / `remove`): one-line quote of
     the principle being replaced.
   - **New text** (for `add` / `revise` / `supersede`): the principle
     itself in declarative form, one paragraph max.
   - **Rationale**: 1-2 sentences linking back to the ADR's "Context"
     section — answer "why now?" not "what".

   Sync impact:
   - [ ] decision-log.md  — ADR-XXX added/updated
   - [ ] invariants.json  — invariant <id> added/updated (or N/A)
   - [ ] canonical_decisions.json — entry updated (or N/A)
   - [ ] CLAUDE.md / AGENTS.md — references updated (or N/A)
   ```

6. **Propose to user**, STOP, wait for `accept` / `change X` / `abort`.

7. **On accept** — execute in order:
   1. `Edit` `.agent-toolkit/constitution.md`:
      - Append the Amendment block at the bottom of the file, BEFORE
        the `Last revised: ...` footer line.
      - Update the footer's date to today (`Last revised: YYYY-MM-DD ·
        toolkit ... preset.`).
      - If the amendment is `supersede` or `remove`, also annotate the
        original section in-place with a `> **Superseded by Amendment
        N (YYYY-MM-DD)**` blockquote — do NOT delete the original text
        (the constitution is append-style; history matters).
   2. If ADR row is "to be created", auto-fire `/adr-add` with the
      same title and STOP for user review before continuing.
   3. If Invariant row is non-`none`, auto-fire `/inv-add` for the
      matching pattern and STOP for user review before continuing.
   4. Tick the Sync impact checkboxes after each downstream edit lands.

8. **Report**: show the user the appended amendment + a checklist of
   any sync items still unticked. Suggest a commit message in the form
   `docs(constitution): amend N — <title>`.

## Refuse / clarify when

- The amendment is a personal preference (font size, terminal color,
  shortcut binding) → not constitution-worthy. Save as memory instead.
- The amendment contradicts an `Accepted` constitutional principle
  WITHOUT being a `supersede` → ask the user to confirm supersession
  explicitly and quote the principle being replaced.
- The proposed principle is already covered by an existing ADR + the
  user just wants to remind themselves → suggest `/recall` instead.
- The proposed text contains project-specific module names, DB names,
  or addon paths → reject per the module-agnostic invariant (Section
  III.1 of the default constitution). Rewrite with `<module>` /
  `<addon>` placeholders.

## What NOT to do

- Do NOT rewrite or delete existing constitutional sections in place —
  the constitution is append-style with `Amendment N:` blocks at the
  bottom and inline `> Superseded by` annotations. Future readers must
  be able to see the rule that was in force at any given commit.
- Do NOT skip the ADR cross-link for `add` / `supersede` / `remove`
  amendments — that's how the WHY survives. A constitutional principle
  without a matching ADR is a rule with no rationale, and rules without
  rationale rot fast.
- Do NOT auto-create invariants without user approval, even if the
  amendment is mechanically enforceable. Run `/inv-add` as a separate
  STOP-gated step.
- Do NOT bump any version number — the constitution carries
  `Last revised: <date>` only. Semver-style versioning was intentionally
  dropped from the adoption of spec-kit's pattern (we have ADRs for the
  audit trail; semver would be a parallel and lossy index).
