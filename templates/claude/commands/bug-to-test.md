---
description: ECC ai-regression-testing pattern — turn every discovered bug into a permanent regression test + an invariant so any future Edit that strips that test is blocked. Rule: "write tests for bugs that were found, not for code that works".
allowed-tools: Read, Edit, Write, Grep, Glob, Bash
argument-hint: "<bug-slug-or-ticket-id>"
---

# /bug-to-test — Convert a discovered bug into a permanent regression test

## Upstream provenance

- **Repo**: https://github.com/affaan-m/everything-claude-code · author [@affaan-m](https://github.com/affaan-m)
- **Upstream skill**: `skills/ai-regression-testing/SKILL.md` — https://github.com/affaan-m/everything-claude-code/blob/main/skills/ai-regression-testing/SKILL.md
- **Adopted**: 2026-05-17 — adapted for the local stack (TransactionCase + invariant_guard integration). The upstream rule "write tests for bugs that were found, not for code that works" is retained verbatim.
- Full mapping: see memory `reference_ecc_upstream`.

## Goal

Close the gap "AGENT fixed the bug but nothing keeps the test → the bug
returns in a later refactor". Inspired by ECC `ai-regression-testing` skill:

> "write tests for bugs that were found, not for code that works"

Workflow turns a bug reproducer → fixed test + an invariant
`must_keep_call` → the `invariant_guard` PreToolUse hook BLOCKS any Edit
that strips that test.

Argument: `$ARGUMENTS` = a bug slug (kebab-case) or a ticket id. If empty
→ ask the user.

## Procedure

1. **Capture bug context** from the current conversation or ticket:
   - Symptom (input → expected → actual).
   - Module / model / method affected.
   - Commit or PR that fixed it (if any).

2. **ADR-first** — if the bug deserves an ADR (architectural root cause, not
   just off-by-one):
   - Run `/adr-add` to record the WHY in `.agent-toolkit/decision-log.md`.
   - Note the ADR id for use in steps 5 + 6.

3. **Locate the test home** — pick a test file:
   - Preferred: `<addon>/tests/test_regression_<slug>.py` in the same addon
     as the bug.
   - If cross-addon: `<project>/tests/test_regression_<slug>.py`.
   - Make sure `**/tests/__init__.py` imports the new test file (some
     frameworks require explicit import).

4. **Write the regression test** — must:
   - Inherit `<test-base>.TransactionCase | SavepointCase | HttpCase` for
     the target framework (NO mock-only — violates ADR-003 if applicable).
   - One class, 1+ method `test_<slug>_<assertion>`.
   - The test must FAIL if the bug returns (assert on actual data, not
     `assertTrue(True)`).
   - Docstring with 3 lines — Symptom / Root cause / Fix ref (commit/ADR).

   Template (Odoo example — adapt for other stacks):

   ```python
   # -*- coding: utf-8 -*-
   from odoo.tests.common import TransactionCase
   from odoo.tests import tagged


   @tagged("regression", "post_install", "-at_install")
   class TestRegression<CamelSlug>(TransactionCase):
       """Regression test for bug <slug>.

       Symptom : <input → wrong actual>
       Root    : <one-line root cause>
       Fix     : commit <sha> / ADR-NNN
       """

       def test_<slug>_<assertion>(self):
           # Setup: create the minimal record needed to reproduce
           rec = self.env["<model>"].create({...})
           # Act: call the method that used to reproduce the bug
           result = rec.<method>()
           # Assert: correct condition (BUG FIXED). If the fix is reverted → fail.
           self.assertEqual(result, <expected>,
                            "regression: bug <slug> resurfaced, fix reverted?")
   ```

5. **Register an invariant** — call `/inv-add` (or inline) with:

   ```json
   {
     "id": "regression-<slug>",
     "description": "Regression test for <slug> must exist and run",
     "applies_to": [
       "<addon>/tests/test_regression_<slug>.py",
       "<addon>/tests/__init__.py"
     ],
     "rules": {
       "must_keep_call": ["test_<slug>_<assertion>"],
       "must_keep_regex": ["class TestRegression<CamelSlug>"]
     },
     "severity": "blocker",
     "rationale": "Bug <slug> hit prod users once. This test is a contract — deleting/renaming requires an explicit ADR supersede. Ref ADR-NNN.",
     "added": "{{TODAY_ISO_DATE}}",
     "added_by": "agent",
     "related_adr": "ADR-NNN"
   }
   ```

   After `/inv-add` runs, the `invariant_guard` (PreToolUse) hook will BLOCK
   any Edit/Write/MultiEdit that strips `class TestRegression<CamelSlug>` or
   the method `test_<slug>_<assertion>`.

6. **Confirm test FAILS before the fix, PASSES after the fix** (Red→Green proof):
   - If the bug is already fixed: run `mcp__<stack>-<v>__run_python_tests`
     on the new test → expect PASS. If FAIL → the test doesn't cover the
     right case; fix it.
   - If the bug is not yet fixed: run the test → expect FAIL with a
     specific assertion error. Save the FAIL output in the docstring as
     proof.

7. **Update decision-log + verify report** if an ADR is linked:
   - Append to ADR-NNN: "Regression test attached: <path>".
   - If the bug was found during a /verify session → mark the Blocker as
     having a test guard.

8. **Print a summary for the user** (8-12 lines):

   ```
   ✓ Regression test created
   - File:        <addon>/tests/test_regression_<slug>.py
   - Test method: TestRegression<CamelSlug>::test_<slug>_<assertion>
   - Linked ADR:  ADR-NNN
   - Invariant:   regression-<slug> (blocker) — future Edits that strip this test will be BLOCKED
   - Smoke:       run_python_tests → <PASS|FAIL>

   Next:
   - Commit the test + invariant together with the fix patch.
   - If the test FAILS: the bug is not fixed yet → /implement to implement, then /verify.
   ```

## Refuse / clarify when

- The bug "looks like a bug" but cannot be reproduced — refuse, demand a
  concrete repro (input → actual) first.
- The bug is CSS/style/typo with no deterministic assertion — suggest a
  lint rule / pre-commit instead of a test.
- The slug duplicates an existing regression test — propose a rename
  (`<slug>-v2`) or add a test case to the existing class.
- The test home does not exist and the addon has no `tests/` dir — confirm
  with the user before creating (maybe the addon intentionally has no tests).

## Must NOT

- Do NOT mark `severity: warn` for a regression — must be `blocker`. Reason:
  ECC rule "a bug that hit users once is a hard contract".
- Do NOT use mocks instead of real ORM in the test — violates ADR-003.
- Do NOT skip the `/inv-add` step — without the invariant, the test can be
  silently deleted in a future refactor.
- Do NOT write a test without reproducing the bug. The test must FAIL on
  the buggy code tree. If it cannot be reproduced → warn that this might
  not actually be a bug.
