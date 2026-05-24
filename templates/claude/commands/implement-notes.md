---
description: Generate `<slug>.implement-noted.md` capturing AGENT-side scope deviations + in-transcript trade-offs + open follow-ups + confidence summary.
argument-hint: <slug>
---

# /implement-notes

Emit the implement-noted sidecar artifact for a spec slug. AGENT
walks the current session's transcript, classifies Edits, identifies
trade-offs with cite-required evidence, and writes
`.agent-toolkit/specs/<branch>/<slug>.implement-noted.md` per the
schema in `templates/agent_toolkit/implement-noted.example.md`.

## Usage

```
/implement-notes <slug>
```

Example:
```
/implement-notes user-profile-redesign
/implement-notes v0.6.2-cleanup-uplift
```

If `<slug>` is omitted: AGENT infers from the most recently edited
spec in `.agent-toolkit/specs/**/*.md`.

## When to use

- **Automatic**: end-of-implement skill normally emits this. Manual
  invocation is for **retroactive** generation when AGENT skipped or
  the file got lost.
- **Pre-/verify gate**: if `/verify` blocks because implement-noted
  is missing, run this command to fill the gap.
- **Refresh**: after a follow-up implementation pass, re-run to
  update the file with new SD/T/F items.

## Output

Single file written to `<workspace>/.agent-toolkit/specs/<branch>/<slug>.implement-noted.md`.

Schema (4 sections + frontmatter):
1. Scope deviations
2. In-transcript trade-offs (STRICT cite-required)
3. Open follow-ups
4. Confidence summary

## Skill reference

Full workflow in `templates/cursor/skills/_common/implement-notes/SKILL.md`.

## Bypass

Single-shot: include `implement-notes: skip <reason>` in your
response to skip the advisory warn for one turn. Use for hotfixes /
typo edits / pure docs work where the artifact is overhead.
