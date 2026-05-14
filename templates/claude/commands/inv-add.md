---
description: Add a durable invariant rule to .agent-toolkit/invariants.json. Use when the user states a rule that future edits must respect ("luôn sort theo type", "không bao giờ bỏ try/except quanh DB call").
allowed-tools: Read, Edit, Write, Bash, Grep, Glob
argument-hint: "[id-slug] [short description]"
---

# /inv-add — Register a new invariant

## Goal

Translate a user-stated durable rule into an entry in
`.agent-toolkit/invariants.json` so the `invariant_guard` PreToolUse
hook will mechanically block future edits that violate it.

Argument: `$ARGUMENTS` (optional — if empty, prompt the user).

## Step-by-step

1. **Read existing invariants** — `Read .agent-toolkit/invariants.json`.
   Confirm no entry with the same `id` slug already exists.

2. **Read the latest ADR** — `Read .agent-toolkit/decision-log.md`. If
   the rule has not yet been captured as an ADR, RUN `/adr-add` FIRST
   to record the WHY. Invariant must reference its ADR.

3. **Probe the codebase** to identify the pattern that must stay alive:
   - `Grep` for the file paths the rule affects → become `applies_to`
     glob list.
   - `Grep` for the actual code pattern (e.g. `order='type'`,
     `sorted(.*type)`) the user wants preserved → becomes
     `must_keep_regex`.
   - For "always call X()" rules, prefer `must_keep_call: ["X"]` over
     a regex (cleaner).
   - Test the regex by running `Grep` with the same pattern on the
     `applies_to` globs to confirm it actually matches today.

4. **Propose the entry to the user** in this exact shape, then STOP for
   approval:

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
     "rationale": "<one paragraph including ADR ref>",
     "added": "<today YYYY-MM-DD>",
     "added_by": "agent | <user-email>",
     "related_adr": "ADR-NNN"
   }
   ```

   Include in the proposal:
   - The Grep output showing the pattern currently exists.
   - Files that would have been blocked if this rule was active
     historically (search git log if useful: `git log -p -S '<regex>'`).
   - Severity recommendation with reason. Default to `warn` for new
     rules unless the user explicitly insists on `blocker`.

5. **On approval** — `Edit` `.agent-toolkit/invariants.json`:
   - Append the new entry to the `invariants` array.
   - Bump `version` by 1.
   - Preserve formatting (2-space indent, trailing newline).

6. **Smoke-test** the hook by simulating an edit that would violate
   the rule. Run:
   ```bash
   echo '{"tool_name":"Edit","tool_input":{"file_path":"<sample>","old_string":"<has pattern>","new_string":"<pattern removed>"},"cwd":"'"$PWD"'"}' \
     | {{PYTHON_BIN}} .claude/hooks/invariant_guard.py
   ```
   Confirm it emits `permissionDecision: deny` for `blocker` (or `allow`
   with reminder for `warn`).

7. **Report**: show the user the registered invariant + the smoke-test
   output + how to bypass (`bypass-invariant: <id>` in a future prompt).

## Refuse / clarify when

- The rule is project-wide style preference (use linter / formatter
  instead, not an invariant — invariants are for SEMANTIC rules).
- The pattern can't be expressed as a regex (e.g. "always think before
  editing" — that's a guideline, not enforceable).
- `applies_to` would match >50% of the repo (too broad — split into
  multiple narrower invariants).
- The user hasn't yet captured the WHY in an ADR. Block until they do.

## What NOT to do

- Do NOT mark `severity: blocker` without explicit user approval.
- Do NOT add invariants that are just "remember to do X" — those
  belong in memory or CLAUDE.md, not in this hook (the hook only
  catches REMOVALS of existing patterns).
- Do NOT edit `invariants.json` without showing the proposed entry
  first.
