---
description: Generate `<slug>.implement-noted.{md,html}` capturing AGENT-side scope deviations + in-transcript trade-offs + open follow-ups + confidence summary.
argument-hint: <slug> [--format md|html|both]
---

# /implement-notes

> **Advisory / opt-in step.** The `implement_notes_gate` hook is **WARN by
> default** — it nudges when a done-claim lacks the sidecar but does NOT block.
> This is one of the highest-signal steps in the flow, so running
> `/implement-notes` after every `/implement` is strongly recommended. To make
> the sidecar a *blocking* requirement, set `per_hook.implement_notes_gate` to
> `block` in `.agent-toolkit/enforce_mode.json` (note: the strict profile and
> `AGENT_TOOLKIT_STRICT=1` keep this gate at `warn` by default, so you must
> override this specific hook to `block`).

Emit the implement-noted sidecar artifact for a spec slug. AGENT
walks the current session's transcript, classifies Edits, identifies
trade-offs with cite-required evidence, and writes
`.agent-toolkit/specs/<branch>/<slug>.implement-noted.{md,html}` per
the schema in `templates/agent_toolkit/implement-noted.example.md`
(machine-parseable) AND
`templates/agent_toolkit/implement-noted.example.html` (DEV browser-readable).

## Usage

```
/implement-notes <slug> [--format md|html|both]
```

Example:
```
/implement-notes user-profile-redesign            # default: emit both .md + .html
/implement-notes v0.6.2-cleanup-uplift --format html  # HTML only
/implement-notes v0.6.2-cleanup-uplift --format md    # MD only (legacy)
```

If `<slug>` is omitted: AGENT infers from the most recently edited
spec in `.agent-toolkit/specs/**/*.md`.

### Format default per project

If `--format` is not passed, AGENT reads
`.agent-toolkit/implement_notes.json` field `output_format`. Allowed
values: `md`, `html`, `both`. Project default ships as `both` for new
installs (v0.18+); legacy installs without this field fall back to
`both` to preserve DEV-readable HTML.

## When to use

- **Automatic** (Phase 5.5 of `/implement` auto-chain — v0.18+): after
  `/verify` completes, agent inline-calls this command. DEV does NOT
  need to type it manually if `auto_emit: true` in
  `.agent-toolkit/implement_notes.json` (default `true`).
- **Pre-/verify gate**: if `/verify` blocks because implement-noted
  is missing, run this command to fill the gap.
- **Refresh**: after a follow-up implementation pass, re-run to
  update the file with new SD/T/F items.
- **Retroactive HTML for legacy specs**: existing `.md`-only sidecars
  from pre-v0.18 specs can be augmented by running
  `/implement-notes <slug> --format html` (preserves the `.md`, adds
  the `.html`).

## Output

Up to 2 files written to `<workspace>/.agent-toolkit/specs/<branch>/`:

- `<slug>.implement-noted.md` — machine-parseable, validated by
  `implement_notes_gate.py` Stop hook. Emitted when `--format=md` or
  `both`.
- `<slug>.implement-noted.html` — self-contained HTML (embedded CSS,
  no external deps). DEV opens in browser to review SD/T/F checkboxes
  + confidence summary visually. Emitted when `--format=html` or `both`.

Both files share the **same 4-section schema** + frontmatter — only
rendering differs.

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
