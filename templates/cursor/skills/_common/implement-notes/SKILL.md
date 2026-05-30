---
name: implement-notes
description: Emit per-spec sidecar artifact `<slug>.implement-noted.md` capturing AGENT-side scope deviations, in-transcript trade-offs (cite required), open follow-ups, and confidence summary at end of /implement. Invoke automatically as Phase 5.5 between implementation and /verify, or via /implement-notes slash command for retroactive generation. Schema: 4 sections per templates/agent_toolkit/implement-noted.example.md.
---

# Skill — implement-notes

Emit `<slug>.implement-noted.md` after `/implement <slug>` completes.
Captures AGENT-side disclosure layer: scope deviations + in-transcript
trade-offs + open follow-ups + confidence summary.

See `templates/agent_toolkit/implement-noted.example.md` for the
schema reference.

## When to invoke

- **Automatic** (preferred): at end of `/implement <slug>` skill, as
  Phase 5.5 — between mechanical implementation and `/verify`.
- **Manual retroactive**: `/implement-notes <slug>` slash command —
  AGENT walks transcript + emits file.
- **Hook reminder**: `implement_notes_gate.py` Stop hook warns if a
  turn claims "implement done" but the file is missing.

## Output contract

A single markdown file at
`<workspace>/.agent-toolkit/specs/<branch>/<slug>.implement-noted.md`
matching the schema in `templates/agent_toolkit/implement-noted.example.md`.

Frontmatter MUST include:
- `spec: <slug>`
- `implement_run_at: YYYY-MM-DD`
- `implement_agent: <model id>`
- `total_scope_deviations: N`
- `total_tradeoffs_with_evidence: K`
- `total_followups: P`
- `overall_confidence: high | medium | low`

Body MUST contain 4 section headers in order:
- `## 1. Scope deviations`
- `## 2. In-transcript trade-offs`
- `## 3. Open follow-ups`
- `## 4. Confidence summary`

## 5-step workflow

### Step 1 — Re-read spec frontmatter

Load `<workspace>/.agent-toolkit/specs/**/<slug>.md`. Extract:
- `acceptance_evals: [...]` ids.
- `feature_kind` (orchestration / classification / regression / maintenance).
- `module` field.
- DEV's literal asks (if captured in spec body).

### Step 2 — Walk transcript for the implement session

For the current `/implement <slug>` turn block (or the last N
implement-related turns), enumerate:
- Every `Edit` / `Write` / `MultiEdit` / `NotebookEdit` tool call.
- The file paths affected.
- Any AGENT-stated rationale ("I'm picking X because Y").
- Any explicit `consider` / `alternative` / `trade-off` mention.

### Step 3 — Classify each action

For each Edit/Write captured in Step 2:

| Classification | Belongs in |
|---|---|
| File path matches an `acceptance_eval.probe.args.target` exactly | NOT a deviation — skip |
| Edit clearly maps to a spec eval id (1-1 traceable) | NOT a deviation — skip |
| Edit changes file outside spec scope (e.g. ad-hoc cleanup) | **SD-N scope deviation** |
| Edit diverges from DEV's literal request | **SD-N scope deviation** (sub-flag: diverged-from-request) |
| Transcript shows explicit option weighing | **T-N trade-off** (with cite) |

### Step 4 — Identify open follow-ups

Scan transcript for AGENT-emitted markers like:
- "TODO" / "FIXME" / "future work" / "out-of-scope"
- "noticed but defer"
- "Should also..."

Convert to `F-N` items with priority + owner.

### Step 5 — Compute confidence + emit MD file

Self-rate each `SD-N` and `T-N`:
- **High**: backed by spec eval + test green + standard pattern.
- **Medium**: defensible but alternative exists.
- **Low**: AGENT had limited info; DEV should verify.

Aggregate into Section 4 summary. List low-confidence items
explicitly under "Items DEV should verify next".

Write `<slug>.implement-noted.md` via `Write` tool to canonical path.
Update frontmatter counts. Mark `overall_confidence` as the lowest
individual confidence.

### Step 6 — Emit HTML companion (v0.18+)

Read project config `<workspace>/.agent-toolkit/implement_notes.json`:

```json
{
  "auto_emit": true,
  "output_format": "both"   // "md" | "html" | "both" — default "both"
}
```

If `output_format` is `"html"` or `"both"` (default for new installs),
ALSO emit `<slug>.implement-noted.html` at the same parent path.

**Render mechanism** — `str.replace` substitution on
`templates/agent_toolkit/implement-noted.example.html`. NO Jinja, NO
external template engine (matches toolkit's stdlib-only contract). The
template ships with 8 placeholders that map 1:1 to data extracted in
Steps 1-5:

| Placeholder | Source | Format |
|---|---|---|
| `{{SLUG}}` | spec slug | literal string |
| `{{IMPLEMENT_RUN_AT}}` | today ISO date | `YYYY-MM-DD` |
| `{{IMPLEMENT_AGENT}}` | model id from session | `claude-opus-4-7` etc. |
| `{{IMPLEMENT_SESSION_ID}}` | session id or short ref | string |
| `{{TOTAL_SD}}` / `{{TOTAL_T}}` / `{{TOTAL_F}}` | counts from Steps 3-4 | integer |
| `{{OVERALL_CONFIDENCE}}` | lowest individual confidence | `high` / `medium` / `low` (used as CSS badge class) |
| `{{SD_ITEMS}}` | rendered SD-N blocks | HTML `<div class="item sd">…</div>` per item |
| `{{T_ITEMS}}` | rendered T-N blocks | HTML `<div class="item t">…</div>` per item |
| `{{F_ITEMS}}` | rendered F-N blocks | HTML `<div class="item f">…</div>` per item |
| `{{CONFIDENCE_SUMMARY}}` | table of H/M/L counts | HTML `<table>` |
| `{{ITEMS_TO_VERIFY}}` | bulleted list of low-confidence ids | HTML `<ul>` |

**Per-item HTML render** — for each `SD-N`, `T-N`, `F-N` from Steps 3-4,
emit a block like:

```html
<div class="item sd">
  <div class="item-title">
    <span class="item-id">SD-1</span>
    <Title> (<span class="badge outside">outside-spec</span>)
  </div>
  <dl>
    <dt>Lý do</dt><dd><reason></dd>
    <dt>Alternatives</dt><dd><alt-list-or-none></dd>
    <dt>File(s) affected</dt><dd><code>path:line</code></dd>
    <dt>Spec linkage</dt><dd><eval-id-or-"none"></dd>
    <dt>Confidence</dt><dd><span class="badge {{conf}}">{{conf}}</span></dd>
    <dt>DEV urgency</dt><dd><span class="badge {{urg}}">{{urg}}</span></dd>
  </dl>
</div>
```

The HTML template's `<style>` block already defines `.item.sd`, `.item.t`,
`.item.f`, `.badge.high|medium|low|outside|diverged` — just emit
matching class names, CSS handles colors.

**HTML safety** — every user/transcript string passed into HTML MUST be
escaped with `html.escape()` (stdlib) before substitution. Otherwise
file paths with `<` `>` `&` break the document.

**File write** — single `Write` tool call to
`<workspace>/.agent-toolkit/specs/<branch>/<slug>.implement-noted.html`.
Same parent path as the `.md` companion. Both files share the SAME
data — only rendering differs.

**Skip case** — if `output_format: "md"` (explicit DEV opt-out), skip
Step 6 entirely. If config file missing, default to `"both"` (emit
HTML).

---

## Phase 5.1-5.4 — AGENT auto-audit chain (v0.7.2+)

After Step 5 emits implement-noted, AGENT auto-runs 4 audit phases
BEFORE `/verify`. DEV touch points unchanged (Plan + Verify only).
Each phase is mechanical; AGENT executes via subprocess tools.

### Phase 5.1 — Validate implement-noted content

```
python .codex/tools/implement_noted_validator.py \
    <spec_parent>/<slug>.implement-noted.md \
    --workspace <root> --json
```

Checks:
- SD-N file paths exist + line ranges within file bounds.
- SD-N Spec linkage = real eval id from spec OR literal "none".
- T-N has non-empty Transcript evidence cite.
- F-N priority ∈ {high, medium, low}.
- Frontmatter `total_*` counts match actual section item counts.

Exit 0 = clean. Exit 1 = issues → AGENT fix in iter 2 (rewrite
implement-noted with correct values).

### Phase 5.2 — Detect missing SD entries

```
python .codex/tools/missing_sd_detector.py <slug> \
    --workspace <root> --json
```

Compares snapshot's modified-file list (`snapshot_diff_filelist`)
against the union of:
- spec.affected_modules prefixes
- implement-noted SD-N file references
- `scope-creep-allowed: <file>` bypass markers

Missing-SD candidates surface as workspace-relative paths. AGENT
resolves by ONE of:
- Add SD-N entry in implement-noted with valid Spec linkage.
- Add `scope-creep-allowed: <file> <reason>` to response.
- Move file path to spec frontmatter `affected_modules` if it
  truly belongs to feature scope.

### Phase 5.3 — Annotate diff hunks

```
python .codex/tools/diff_hunk_annotator.py <slug> \
    --workspace <root> --write
python .codex/tools/diff_annotation_validator.py \
    <spec_parent>/<slug>.diff-annotations.md \
    --workspace <root>
```

Generates `<slug>.diff-annotations.md` with 1 row per unified-diff
hunk. AGENT tags each hunk with eval id, SD-N reference, or bypass
marker `untagged-hunk-allowed: <reason>`. Validator rejects untagged
hunks.

This is the SEMANTIC scope check: even files inside affected_modules
may contain code changes UNRELATED to acceptance_evals. Mandatory
annotation forces explicit linkage.

### Phase 5.4 — File-level scope check

Performed automatically by Stop hook `verify_lint_scope.py` when
AGENT emits the Verify Report. Reads `spec.affected_modules`,
compares against snapshot diff. Out-of-scope files → block (when
`.agent-toolkit/scope_audit.json` `enforce: block`) or warn
(`enforce: warn`).

If clean → AGENT proceeds to `/verify`. If issues persist after
iter 2 → AGENT emits diagnostic + stops, surfaces in verify_report.

## Anti-patterns (what NOT to do)

1. **Hallucinate trade-offs**: do NOT list trade-offs that have no
   transcript evidence. If no alternatives were weighed, write
   "None" in section 2.
2. **Omit decisions to look cleaner**: completeness > brevity. If
   uncertain whether to include an item, include it with medium
   confidence and let DEV decide.
3. **Skip the confidence summary**: this is the most actionable
   section for DEV review.
4. **Hardcode project name** in the file: artifact must be portable
   if spec migrates.

## Interaction with other artifacts

- **spec.md** (intent contract): implement-noted references its
  acceptance_eval ids; never modifies spec.
- **verify_report.md** (mechanical evidence): emitted AFTER
  implement-noted, during `/verify`. verify_report cites
  acceptance_eval verdicts; implement-noted cites scope deviations.
- **decision-log.md** (durable cross-feature ADR): if an item in
  implement-noted appears in 2+ features, promote via `/adr-add`.
- **invariants.json**: F-N items flagged "Invariant candidate: yes"
  → register via `/inv-add`.

## Bypass

Single-shot bypass: include `implement-notes: skip <reason>` in the
response that claims "implement done". The Stop hook will log the
bypass + skip the warn for that turn.

## Public-project safety

This skill makes NO assumption about stack / module / project name.
The schema is generic. Templates ship empty path placeholders. DEV /
AGENT fill in concrete paths at runtime.
