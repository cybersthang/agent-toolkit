---
description: Report probe coverage for the current branch — which feature-scope files have a registered probe in acceptance-probes.json vs which don't. Run before merge to ensure "tổng thể toàn bộ feature" requirement met.
allowed-tools: Read, Bash, Grep, Glob
argument-hint: "[scope: 'staged' | 'branch' | path glob]"
---

# /probe-coverage — Report which features lack a probe

## Goal

Surface the gap between "features in the diff" and "probes registered
in `acceptance-probes.json`". This is the dev's "tổng thể cho toàn bộ
feature" requirement — without coverage, the per-feature contract
remains hypothetical.

Argument: `$ARGUMENTS` — one of:
  - `staged` (default): files currently staged for commit
  - `branch`: files changed in current branch vs origin/main
  - `<path-glob>`: explicit glob (e.g. `<addon-root>/<module>/**`)

## Step-by-step

1. **Resolve scope**:
   - `staged` → `git diff --cached --name-only`
   - `branch` → `git diff --name-only origin/main...HEAD`
   - `<glob>` → `Glob` directly

2. **Read configs**:
   - `Read .agent-toolkit/coverage_config.json` for feature_globs +
     exempt_globs (fall back to defaults in
     `.codex/precommit_hooks/probe_coverage.py` if missing).
   - `Read .agent-toolkit/acceptance-probes.json` for registered probes.

3. **Bucket each file**:
   - **Out of scope** — doesn't match any `feature_globs`.
   - **Exempt** — matches `exempt_globs`.
   - **Covered** — matches `feature_globs`, not exempt, AND ≥1 probe's
     `applies_when.path_globs` covers it.
   - **Uncovered** — matches feature scope but NO probe.

4. **Render table**:
   ```
   | File | Bucket | Covering probe(s) |
   |------|--------|-------------------|
   | <addon-root>/foo/controllers/main.py | uncovered | — |
   | <addon-root>/foo/models/bar.py       | covered   | foo-bar-validate |
   ```

5. **Summary line**: `N total scoped · X covered · Y uncovered`

6. **Action prompts**:
   - For each uncovered: suggest a probe id (kebab-case of file path)
     and a starter command:
     ```
     /probe-add <id> [description]
     ```
   - Cite the dev's empirical method when relevant: for any controller
     file, recommend `timing_perturb` falsification (inject
     `time.sleep`); for models, recommend `consistency_check_eval`.

## When to run

- Before opening a PR.
- After `/inv-add` or `/probe-add` to verify the new probe actually
  covers the intended path.
- Periodically (`/probe-coverage branch`) to catch drift across many
  commits.

## What NOT to do

- Do NOT auto-register probes from this command. The whole point of
  `/probe-add` is dev-author-aware probe declaration with explicit
  rationale + falsification recipe. Auto-stubs would be empty and
  hurt the signal.
- Do NOT exit non-zero based on uncovered count — this command is
  read-only diagnostic. The pre-commit hook
  `.codex/precommit_hooks/probe_coverage.py` is the enforcement layer.
