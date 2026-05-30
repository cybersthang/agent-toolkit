---
description: Atomic "decide a durable rule" — creates ADR + invariant in one shot with cross-links so they cannot drift. Use instead of running /adr-add then /inv-add separately.
allowed-tools: Read, Edit, Write, Bash, Grep, Glob
argument-hint: "[short-title or rule statement]"
---

# /decide — Atomic ADR + invariant in one command

## Goal

Close the 3-way drift between `.agent-toolkit/decision-log.md` (the WHY),
`.agent-toolkit/invariants.json` (the mechanical enforcement), and
`.codex/canonical_decisions.json` (recurring-question registry). Running
`/adr-add` then `/inv-add` separately is two STOP gates; humans skip the
second half ~30% of the time per `/hook-health` audit, leading to ADRs
that "claim invariants.json#X" while no such invariant exists.

This command bundles both into a single proposal + single user approval
+ atomic write. Cross-links are inserted automatically:
- `ADR-NNN.enforcement` → `invariants.json#<id>`
- `invariant.related_adr` → `ADR-NNN`

Argument: `$ARGUMENTS` — short title (kebab-case) or the rule statement
itself. If empty, prompt the user with a 1-question UNDERSTANDING block.

## Step-by-step

1. **Read both registries** in parallel:
   - `Read .agent-toolkit/decision-log.md` — find highest `ADR-NNN`
     number; new ADR uses `NNN+1` zero-padded to 3 digits.
   - `Read .agent-toolkit/invariants.json` — confirm proposed invariant
     `id` slug is not already taken.

2. **Confirm the decision is durable**, not a one-shot choice:
   - Will this rule apply to future similar situations? → YES → continue.
   - Is this just an implementation detail for one PR? → NO → don't
     run /decide; mention in commit message instead.
   - Does it contradict an existing ADR? → mark old one as
     `Superseded by ADR-NEW`, link both ways, and propose the
     supersession in the same atomic write.

3. **Probe the codebase** for the enforcement pattern:
   - `Grep` for file paths the rule affects → become `applies_to` globs.
   - `Grep` for the code pattern that must stay alive → becomes
     `must_keep_regex` (or `must_keep_call` for "always call X()" rules).
   - **Test the regex** by running `Grep` with the same pattern on the
     `applies_to` globs to confirm it matches in TODAY's codebase. If it
     doesn't match anything, the invariant has nothing to protect — push
     back to the user before writing.

4. **Compose the bundle** in this exact shape, then **STOP** for one
   approval covering both halves:

   **ADR half** (`.agent-toolkit/decision-log.md` append):

   ```
   ## ADR-NNN: <Title in sentence case>
   - **Date**: <today YYYY-MM-DD>
   - **Status**: Accepted
   - **Context**: 1-3 sentences. Quote the user prompt that motivated it.
   - **Decision**: the rule, in declarative form. One sentence.
   - **Enforcement**: `invariants.json#<id>` (this invariant — created
     atomically below)
   - **Consequences**: who/what is affected; trade-offs accepted.
   ```

   **Invariant half** (`.agent-toolkit/invariants.json` append to array):

   ```json
   {
     "id": "<kebab-case>",
     "description": "<one-line>",
     "applies_to": ["<glob>", "..."],
     "rules": {
       "must_keep_regex": ["<regex>", "..."],
       "must_keep_call": ["<name>", "..."]
     },
     "severity": "blocker | warn",
     "rationale": "<one paragraph>. See ADR-NNN.",
     "added": "<today YYYY-MM-DD>",
     "added_by": "agent | <user-email>",
     "related_adr": "ADR-NNN"
   }
   ```

   Include in the proposal:
   - The Grep output showing the pattern currently exists in the codebase.
   - Severity recommendation with reason. Default `warn` unless the user
     explicitly insists on `blocker` (mechanically denies future edits).
   - Migration impact if any (files that would have been blocked
     historically by this rule).

5. **On approval** — write both files **in the same turn**:
   - `Edit` `.agent-toolkit/decision-log.md`: append ADR after the
     marker `<!-- Add new ADRs BELOW this line ... -->`. Preserve
     trailing newline.
   - `Edit` `.agent-toolkit/invariants.json`: append invariant to the
     `invariants` array. Bump top-level `version` by 1. Preserve
     2-space indent.
   - If the chosen severity is `blocker` AND
     `.codex/canonical_decisions.json` has an entry on the same topic
     (search via `Grep` on the topic keyword), update its
     `enforcement` block to mirror the new invariant. This closes the
     3-way drift between all three SOT files.

6. **Smoke-test** the invariant via the hook:

   ```bash
   echo '{"tool_name":"Edit","tool_input":{"file_path":"<sample-from-applies_to>","old_string":"<line containing must_keep_regex match>","new_string":"<line with pattern removed>"},"cwd":"'"$PWD"'"}' \
     | {{PYTHON_BIN}} .claude/hooks/invariant_guard.py
   ```

   Expected: `permissionDecision: deny` for `blocker`, `allow` with
   reminder for `warn`. If smoke-test fails (wrong glob, regex didn't
   compile, etc.), revert BOTH writes — the bundle is atomic.

7. **Report** to the user:
   - The appended ADR (with new number) + the registered invariant.
   - Smoke-test output verbatim.
   - Bypass syntax for one-off override: `bypass-invariant: <id>` in
     the next user prompt (G2 v0.10.0 ephemeral file path).

## Refuse / clarify when

- The "decision" is a personal preference (font size, theme) → not an ADR.
- The rule is project-wide style → linter / formatter, not invariant.
- The pattern can't be expressed as a regex → it's a guideline, not
  enforceable. Save to memory or CLAUDE.md instead.
- `applies_to` would match > 50% of the repo → too broad, split into
  multiple narrower invariants and run /decide once per narrow rule.
- The decision contradicts an `Accepted` ADR without acknowledging it
  → ask the user to confirm supersession explicitly before continuing.

## What NOT to do

- Do NOT write either file before user approval — the atomic guarantee
  depends on the single STOP gate.
- Do NOT mark `severity: blocker` without explicit user approval.
- Do NOT skip the smoke-test in step 6 — it's the only check that the
  new invariant actually enforces what its description claims.
- Do NOT edit existing ADRs in-place — decision log is append-only. To
  change one, append a new ADR marked `Superseded by ADR-X`.
- Do NOT create an invariant that mentions a non-existent ADR (or vice
  versa) — that's exactly the drift this command exists to prevent.

## Why this exists (vs running /adr-add then /inv-add)

Per HE evaluation v0.10.0 G5: two separate STOP gates means humans skip
the second one ~30% of the time, leaving "enforced" ADRs that aren't.
One STOP gate, one approval, one atomic write makes drift impossible.
The `related_adr` ↔ `enforcement` cross-link is now enforceable in CI
because both fields are written by the same tool.
