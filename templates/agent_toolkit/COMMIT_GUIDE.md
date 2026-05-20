# Commit guide — splitting agent-toolkit work into reviewable PRs

Agents don't commit on your behalf; this doc is for the human reviewer.

When a session lands many cross-cutting changes in `agent-toolkit/`, ship
them as **separate logical commits** so reviewers (and `git bisect`) can
follow.

## Recommended split for `0.6.0` autonomy chain

The 11-patch autonomy chain naturally falls into 4 commits:

### Commit 1 — schemas + migration (D1 + D2)
```
templates/agent_toolkit/test_env.schema.json          NEW
templates/agent_toolkit/test_env.example.json         NEW
templates/agent_toolkit/acceptance-probes.schema.json NEW
templates/codex/tools/migrate_probes_v2.py            NEW
templates/cursor/skills/_common/test-env-bootstrap/   NEW
```
Message: `feat(schemas): v2 acceptance-probes + test_env, migration script`

### Commit 2 — evidence_audit config-driven + mcp_call (C1 + A2)
```
templates/agent_toolkit/evidence_audit_config.example.json  NEW
templates/claude/hooks/_audit/pass_contract.py              EDIT
templates/claude/hooks/evidence_audit.py                    EDIT
templates/codex/tools/falsify.py                            EDIT (add mcp_call runner)
templates/codex/tools/mcp_call.py                           NEW
templates/codex/tools/creds_resolver.py                     NEW
```
Message: `feat(evidence): config-driven recognizers + mcp_call falsifier`

### Commit 3 — orchestration hooks (S3 B1+B2+B3+wiring)
```
templates/claude/hooks/auto_run_probes.py     NEW
templates/claude/hooks/auto_test_runner.py    NEW
templates/claude/hooks/daemon_manager.py      NEW
templates/claude/hooks/spec_drift_advisory.py NEW
templates/claude/settings.json                EDIT (wire 4 hooks)
templates/agent_toolkit/intent_map.json       EDIT (+5 entries)
```
Message: `feat(hooks): PostToolUse auto-run-probes, auto-test, daemon-manager + intent_map`

### Commit 4 — autonomy skills + engines (S4 C2+C3+C4+C5)
```
templates/claude/commands/gap-status.md                          NEW
templates/cursor/skills/_common/gap-status/                      NEW
templates/cursor/skills/_common/gap-fix-cycle/                   NEW
templates/cursor/skills/_common/recipe-to-probe-script/          NEW
templates/cursor/skills/_common/spec-vs-evidence-diff/           NEW
templates/codex/tools/gap_status.py                              NEW
templates/codex/tools/gap_fix_cycle.py                           NEW
templates/codex/tools/recipe_to_probe_script.py                  NEW
templates/codex/gap_fix_diagnose/                                NEW
templates/codex/recipe_patterns/                                 NEW
templates/agent_toolkit/gap_fix.example.json                     NEW
tests/test_new_tools.py                                          NEW
CHANGELOG.md                                                     EDIT
```
Message: `feat(autonomy): /gap-status, gap-fix-cycle, recipe-to-probe-script + 17 tests`

## Pre-existing changes (NOT from this session)

```
setup.py             EDIT  ←  defensive filter for nested _*.py files
.gitignore           EDIT  ←  add `presets/*-private.json`
.coverage            BINARY  ←  pytest artifact (don't commit)
```

Recommended: `git restore .coverage` (revert artifact), then either fold
`setup.py + .gitignore` into commit 1 or ship as a separate `chore`
commit if they predate the 0.6.0 work.

## What NOT to do

- Do **not** squash all 22 NEW + 6 EDIT files into a single commit —
  reviewers can't follow the dependency chain.
- Do **not** commit `.coverage` (binary pytest artifact, already in
  `.gitignore` upstream — should be untracked).
- Do **not** commit a private preset overlay (`presets/odoo-12-nakivo.json`)
  to the public toolkit. Re-add `.gitignore` rule for it if not already.

## After commits land

```
git tag v0.6.0
git push origin <branch> --tags
```

Optional: tag with semver release notes drawn from `CHANGELOG.md` `[0.6.0]`
section.
