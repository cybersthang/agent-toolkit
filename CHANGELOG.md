# Changelog

All notable changes to agent-toolkit are documented here. Follows Semver:
breaking changes bump MAJOR; feature additions bump MINOR; bug fixes bump PATCH.

## [0.5.1] — 2026-05-19 — Public-ready cleanup

### Removed (BREAKING for anyone who still used the in-toolkit overlay)

- `presets/odoo-12-nakivo.json` — project-specific overlay removed from
  the public toolkit. If you need that exact stack (custom addon roots,
  internal JIRA endpoints, Vietnamese default response, `Nakivo01` DB),
  recreate it as a **private preset overlay** in your own fork that
  `extends: odoo-12`. See `templates/agent_toolkit/PORTING.md` for the
  recipe.
- `templates/cursor/rules/odoo-12/odoo-12-nakivo-modules.mdc` — same
  reason; project-specific rules belong in the private overlay.

### Added

- `LICENSE` — MIT, at toolkit root.
- `NOTICE` — third-party MIT copyright notices for mattpocock/skills +
  github/spec-kit + andrej-karpathy-skills (required by their licenses).
- `# SPDX-License-Identifier: MIT` headers on `setup.py` and `lib/installer.py`.
- `.gitignore` extended: `.coverage`, `.pytest_cache/`, `.ruff_cache/`,
  `.mypy_cache/`, `htmlcov/`, `*.egg-info/`, `dist/`, `build/`, `.tox/`.

### Fixed

- `templates/cursor/skills/odoo/odoo-code-review/references/odoo-12-rules.md:77`
  — env-var name leaked the literal `NAKIVO_JIRA_*` prefix into a
  template that ships to every Odoo-12 install. Now `{{ENV_PREFIX}}_JIRA_*`
  (rendered at install time).
- All baked project-specific examples in templates replaced with
  `<addon>` / `<module>` / `<your.model>` placeholders so the public
  toolkit no longer ships any project-identifying string.

### Migration

Projects on `odoo-12-nakivo` preset must:
1. Create `<your-fork>/presets/odoo-12-nakivo.json` locally (copy from
   v0.5.0 of this repo if you need the old content), OR
2. Switch to `--preset odoo-12` and supply project-specific values via
   Phase 1 Q&A or `agent-toolkit.config.json` overrides.

The public toolkit no longer ships any organisation-specific defaults.

## [0.5.0] — 2026-05-19

Major: **Odoo skills are now version-aware**. The 12 version-baked skill
folders (`cursor/skills/odoo-12/odoo-12-*` and `cursor/skills/odoo-17/odoo-17-*`)
have been merged into **9 version-agnostic skills** under
`cursor/skills/odoo/`. Each skill's Step 0 reads `__manifest__.py` and
loads a matching `references/odoo-<N>-*.md` file. Future Odoo versions
(21, 22, …) only need one new reference file per skill — no preset edits,
no AGENTS.md edits, no new skill folders.

### Added

- **9 version-aware Odoo skills** under `templates/cursor/skills/odoo/`:
  - `odoo-codebase-discovery` — MCP discovery tools (no version logic).
  - `odoo-data-verification` — realdata_test MCP probes (no version logic).
  - `odoo-deterministic-answers` — canonical_decisions lookup (no version
    logic).
  - `odoo-jira-workflow` — JIRA MCP (no version logic).
  - `odoo-code-patterns` — version detection + `references/odoo-<N>-patterns.md`
    for v12 / v17 / v18 / v19 / v20-stub.
  - `odoo-module-scaffold` — version detection + `references/odoo-<N>-scaffold.md`
    for v12 / v17 / v18 / v19 / v20-stub.
  - `odoo-debug-troubleshoot` — version detection +
    `references/odoo-<N>-pitfalls.md` for v12 / v17 / v18 / v19 /
    v20-stub.
  - `odoo-tdd` — version detection + `references/odoo-<N>-tdd-pitfalls.md`
    for v12 / v17 / v18 / v19 / v20-stub.
  - `odoo-code-review` — unchanged (already version-aware; pre-existing
    pattern that the rest of the refactor follows).

### Removed

- `templates/cursor/skills/odoo-12/` (8 version-baked skills).
- `templates/cursor/skills/odoo-17/` (4 version-baked skills).
- Skill-name placeholders `{stack}-tdd` / `{stack}-code-patterns` / etc.
  in `intent_map.json` and `intent_router.py` — now literal `odoo-tdd`,
  `odoo-code-patterns`, etc. (the SKILL itself does version detection).

### Changed

- **Preset `skills` field**:
  - `odoo-12.json`: `["_common", "odoo", "odoo-12"]` → `["_common", "odoo"]`.
  - `odoo-17.json`: `["_common", "odoo", "odoo-17"]` → `["_common", "odoo"]`.
- **`templates/AGENTS.md`** intent-routing table — every `{{STACK_FRAMEWORK}}-{{STACK_FRAMEWORK_VERSION}}-X`
  link replaced with literal `odoo-X` (skills auto-detect version).
- **`templates/agent_toolkit/intent_map.json`** — `{stack}-*` /
  `{stack_bare}-*` placeholders replaced with literal `odoo-*`.
- **`templates/claude/hooks/intent_router.py`** fallback patterns —
  same literal replacement.

### How to extend for Odoo 21+

1. Add `references/odoo-21-rules.md` to `odoo-code-review`.
2. Add `references/odoo-21-patterns.md` to `odoo-code-patterns`.
3. Add `references/odoo-21-scaffold.md` to `odoo-module-scaffold`.
4. Add `references/odoo-21-pitfalls.md` to `odoo-debug-troubleshoot`.
5. Add `references/odoo-21-tdd-pitfalls.md` to `odoo-tdd`.
6. (Optional) add `presets/odoo-21.json` extending `odoo-17`.
7. (Optional) add `canonical_decisions.odoo-21.json`.

No skill body changes, no AGENTS.md changes, no intent_router changes
needed.

### Compatibility

- Projects on toolkit ≥ 0.4 can `setup.py update --apply` to pick up the
  new skill layout. Old `.cursor/skills/odoo-12-*` and `odoo-17-*`
  directories will remain on disk — toolkit does not auto-delete them.
  Run manually: `rm -rf .cursor/skills/odoo-12-* .cursor/skills/odoo-17-*`
  after update.
- `agent-toolkit.config.json` unaffected.
- `.codex/canonical_decisions.json` unchanged.
- Memory packs `templates/memory/odoo-12/` and `odoo-17/` unchanged
  (still version-baked — memory is per-project state, not a skill).
- Cursor rules `templates/cursor/rules/odoo-12/` and `odoo-17/` unchanged
  (cursor rules use `globs:` per-file — cannot runtime-detect version).

---

## [0.4.0] — 2026-05-19

Major: Spec Kit alignment. The toolkit's spec-driven workflow is renamed
to match GitHub Spec Kit's slash-command vocabulary
(`/plan` → `/clarify` → `/tasks` → `/analyze` → `/implement` → `/verify`),
spec files move to a branch-scoped layout, and the agent auto-chains
analyze + implement + verify after DEV approves tasks.md.

### Added — Spec Kit workflow

- **`/clarify` slash command + `clarify` skill** (was `/grill` / `grill`)
  — Spec Kit Phase 2. Skill folder renamed
  `_common/grill/` → `_common/clarify/`. Auto-fires `/tasks` on
  completion. Refines `acceptance_evals` inline before tasks emit.
- **`/tasks` slash command + `tasks-breakdown` skill** (new) — Spec Kit
  Phase 3. Emits `tasks.md` next to the spec with Touches / Acceptance /
  Verification / Risk per task. STOPs for DEV review.
- **`/analyze` slash command + `analyze-artifacts` skill** (new) — Spec
  Kit Phase 3.5. 7 cross-artifact checks (story coverage / eval coverage
  / out-of-scope / invariant compat / constitution compat / path
  realism / verification concreteness). Auto-fired as first step of
  `/implement`. HALT verdict stops the auto-chain.
- **`/implement` slash command** (was `/go`) — Spec Kit Phase 4. Now
  auto-chains: `/analyze` → autonomy ON → execute tasks → `/verify` →
  report. DEV only needs `/plan` + `/clarify` + `/implement`.
- **`constitution.md`** (new) — toolkit principles + project-wide hard
  rules + stack constants in one slow-changing file. Aggregation point
  inspired by Spec Kit's `memory/constitution.md`.
- **Branch-scoped spec layout**: `.agent-toolkit/specs/<branch>/<slug>.md`
  replaces the flat `.agent-toolkit/specs/<slug>.md`. Branch derived
  from `git rev-parse --abbrev-ref HEAD`, fallback `_default`.
  Hooks (`verify_nudge`, `verify_lint`, `lint_verify_report.py`,
  `_patterns.py` slug regex) use `rglob`/optional-segment patterns so
  both layouts are supported in transition.

### Removed

- `_common/spec-driven-feature/` skill — its content split into
  `plan-feature` (Phase 1) + `clarify` (Phase 2) + `tasks-breakdown`
  (Phase 3); the duplicate skill folder is gone.
- `templates/claude/commands/grill.md` — replaced by `clarify.md`.
- `templates/claude/commands/go.md` — replaced by `implement.md`.

### Changed

- **`templates/AGENTS.md`** — intent-routing table updated for Spec Kit
  command names + Spec-driven workflow diagram added at the top.
- **`templates/agent_toolkit/intent_map.json`** — regex patterns + skill
  names migrated to Spec Kit naming. Old verify-against-real-data entry
  consolidated into Phase 5.
- **`templates/claude/hooks/intent_router.py`** — fallback intent map +
  per-skill expected-output blurbs migrated. New entries for
  `plan-feature`, `clarify`, `tasks-breakdown`, `analyze-artifacts`,
  `verify-feature`.
- **`plan-feature` skill** — branch-scoped path emit; description
  refreshed for Spec Kit Phase 1 naming. Auto-emits `acceptance_evals`
  skeleton with `TBD` fields refined later by `/clarify`.
- **`verify-feature` skill** — locate spec via `rglob` instead of fixed
  path; reference `/implement` instead of `/go`.

### Compatibility

- Specs created under the legacy flat layout (`.agent-toolkit/specs/<slug>.md`)
  are still discoverable: every hook + slash command falls back via
  `rglob` / optional-segment regex. New specs land in branch-scoped dirs.
- Projects on toolkit ≥ 0.3 can `setup.py update --apply` to pick up the
  new slash commands + skills. `setup.py update` is dry-run-by-default,
  so review the diff first. `agent-toolkit.config.json` is unaffected.
- `spec-driven-feature` removal is breaking for any custom skill or doc
  that linked to it; the closest replacement is `plan-feature`.

---

## [0.3.0] — 2026-05-18

Major: PASS-claim contract + hallucinated-progress detection + acceptance
probes registry + auto-pipeline + Playwright integration. Closes the
"agent reports PASS but real-data has bugs" gap by combining mechanical
enforcement (Stop hook + pre-commit) with empirical falsification CLI.

### Added — PASS-claim & probe contracts

- **`acceptance-probes.json` registry** in `templates/agent_toolkit/`.
  Per-feature contracts declaring `applies_when` activation rule +
  `evidence.required_tools` MCP requirements + `falsification.runner`
  empirical recipe. Schema versioned (v2).
- **`evidence_audit.py` split into `_audit/` sub-package** (7 modules:
  `strip`, `transcript`, `claim_audit`, `pass_contract`,
  `progress_checks`, `reasons`, `telemetry`). Entry script slimmed to
  ~200 line.
- **PASS-claim contract** (fail-CLOSED): claims like `tests pass`,
  `verified`, `done`, `hoàn thành` blocked unless turn includes ≥1 call
  to `mcp__realdata_test__*` / `mcp__postgres__*` (or matching
  per-feature probe MCP tool).
- **Hallucinated-progress checks** (5 categories A-E):
  `action_ghost`, `tool_result_fabrication`, `phantom_citation`,
  `todo_inconsistency`, `overcount`. Cross-checks claim text against
  the turn's actual `tool_use` / `tool_result` record.
- **`required_result_fingerprint`** (sha256) on probe.evidence:
  catches dummy MCP calls (e.g. `eval_orm_expression("1+1")`) that
  satisfy tool-name match but not query-result fingerprint.
- **`[meta-review]` / `[meta]` marker** exempts PASS contract +
  generic claim audit (but NOT progress checks) for meta-analysis
  responses about the toolkit itself.
- **Telemetry log** at `.codex/logs/hook_events.jsonl` (rotates at
  1 MB, keeps 3 rotations). Surfaced in `session_brief` SessionStart
  brief as `Hook health (last N events)`.
- **Kill-switch** via `AGENT_TOOLKIT_DISABLE=1` env var — all hooks
  short-circuit to allow.

### Added — auto-pipeline + slash commands

- **`probe_autostub.py`** PostToolUse hook — WARN when Edit/Write
  lands on feature-scope file but no probe covers it. Forces agent
  back to grill phase to capture PROBE_READINESS.
- **`auto_falsify.py`** pre-commit — for each staged file, invoke
  `falsify.py --probe <id>` for matching probes; block commit on
  REFUTED.
- **`probe_coverage.py`** pre-commit — block commit if feature-scope
  file has no registered probe.
- **`feature_probe_suggest.py`** pre-commit (info-only) — suggests
  `/probe-add` for new HTTP routes / controller methods / cron
  handlers in staged diff.
- **`falsify.py`** CLI runner (`.codex/tools/`) — empirical
  falsification for 4 types: `timing_perturb`, `side_effect_inject`,
  `log_assertion`, **`playwright`** (spawn `npx playwright test`,
  parse JSON reporter). Sandboxed shell exec (binary whitelist +
  quote-aware metachar scan).
- **`agent_toolkit_init.py`** bootstrap CLI — one-command setup for
  new projects.
- **New slash commands**: `/probe-add`, `/probe-coverage`, `/review`,
  `/run-probes`.
- **`clarification-gate` skill** extended with `PROBE_READINESS` block
  — for feature-scope tasks, agent must capture probe params during
  grill before implementation.
- **`intent_router.py` externalized** to `.agent-toolkit/intent_map.json`
  (with embedded fallback). Stack-agnostic via `{stack}/{stack_bare}`
  template placeholders.

### Added — pre-commit + safety

- **`.pre-commit-config.yaml.tmpl`** top-level template (installed as
  `.pre-commit-config.yaml`) wires 5 pre-commit hooks: invariant_guard,
  credential_guard (with Shannon entropy check), probe_coverage,
  probe_suggest, auto_falsify.
- **Atomic file mutation** in `falsify.py`: `os.replace` for inject
  + restore. Backup file separate from tmp; crash mid-injection
  cannot leave partial state.
- **`coverage_config.json`** at `templates/agent_toolkit/` — defines
  `feature_globs` for probe-coverage gate + `exempt_globs` for tests/
  migrations/etc.

### Added — Optional Playwright integration

- **`falsification.type: "playwright"`** runner: spawn `npx playwright
  test <spec>`, parse JSON reporter, PROVEN if all passed / REFUTED on
  any fail.
- **MS Playwright MCP** server referenced in `PORTING.md` (install
  separately if agent should drive browser interactively during grill).

### Added — Documentation & tests

- **`PORTING.md`** — full porting guide for non-Odoo stacks (Django,
  Rails, etc.). Comparison matrix vs CI / PR template / human review.
- **`QUICKSTART.md`** — 5-minute install + first-probe walkthrough
  (English).
- **Hook test suite**: 120 unit tests in `templates/codex/tests/hooks/`
  covering claim audit, PASS contract, progress checks, autostub,
  falsifier, fingerprint, sandbox, FP-resistance, Playwright dispatch.

### Fixed

- **BOM-tolerant load** (`utf-8-sig`) for `invariants.json`,
  `acceptance-probes.json`, `decision-log.md` reads — PowerShell
  `Out-File -Encoding utf8` BOM no longer silently disables hooks.
- **`_split_current_turn`** in `evidence_audit` skips intermediate
  tool_result echo messages — earlier turn tool_use blocks now
  participate in cross-checks.
- **`phantom_citation`** parses markdown link URLs; resolves citations
  by basename + on-disk existence + Read/Grep history.

### Compatibility

- Any project on toolkit ≥ v0.2 can `setup.py update` to get v0.3
  without breaking existing customization (registries preserved via
  SKIP_EXISTS on `agent_toolkit/`).
- New PostToolUse hook entry (`probe_autostub`) added to settings.json
  template — applies on next install/update.

---

## [0.2.0] — 2026-05-15

Audit-driven Tier 2 + Tier 3 + Tier 4 hardening pass.

### Added

- **`--apply` flag for `update`** (safe-by-default). Without it, `update`
  runs a dry-run with unified diff so changes can be reviewed before any
  disk write.
- **`--no-backup`, `--diff/--no-diff`, `--force`, `--force-dirty` flags**
  for `update` — full control over the apply behavior.
- **`--version` top-level flag** — prints `agent-toolkit <semver>`.
- **Auto-backup of overwritten files** as `<file>.bak.<YYYYMMDD-HHMMSS>`
  when `update --apply` (default; opt out with `--no-backup`).
- **Two-pass atomic apply**: templates are rendered into memory first;
  any render error aborts BEFORE any disk write. Each file is then
  written via `tmp + os.replace` so an interrupted write never leaves
  a half-written destination.
- **Preset inheritance** via `"extends": "<parent>"` field.
- **Additive overrides**: `addon_roots_append`, `mcp_servers_append`,
  `mcp_servers_remove`, `rules_append`, `skills_append`,
  `memory_packs_append` — extend parent preset without copy-pasting.
- **Preset schema validation** — typos like `addon_root` (singular) fail
  fast with a `did you mean` suggestion instead of silently breaking.
- **Git-aware safety**: `update --apply` refuses to overwrite a dirty
  working tree; pass `--force-dirty` to override.
- **MEMORY.md auto-regeneration** — after `seed_memory`, the index file
  is scanned and any *.md present in the memory dir but missing from
  MEMORY.md gets an entry added (parsed from frontmatter).
- **UTF-8 stdout reconfigure** at process start so the `✓` status glyph
  prints on Windows `cp1252` consoles without crashing.
- **Pytest suite**: 38 unit tests covering render_text, preset loading,
  validate_preset, resolve_preset inheritance (including cycle detection
  and `mcp_servers_remove`), encode_claude_project_path,
  git_dirty_status, _parse_frontmatter, regenerate_memory_index,
  _looks_templated, _content_will_change.
- **`.github/workflows/test.yml`** — CI matrix for Linux/macOS/Windows
  × Python 3.8/3.10/3.12.
- **`.pre-commit-hooks.yaml`** — projects using the toolkit can plug
  `setup.py update --apply --no-diff` into pre-commit to keep generated
  agent infra in sync.

### Changed

- **`update` default behavior is now dry-run + diff** (was: force-overwrite
  everything with no preview). This is a deliberate breaking change for
  safety; the previous behavior is `update --apply --no-backup --force`.
- **`load_preset` drops the hand-rolled YAML parser** (~50 dead lines).
  JSON-only by default. To use YAML, install pyyaml separately.
- **`_looks_templated` scans the full file** (was: first 8KB only). Fixes
  silent placeholder leak for templates larger than 8KB.

### Removed

- `README1.md` — stale fragment that just said `DEPRECATED → see README.md`.

## [0.1.0] — pre-2026-05-15

Initial release. Multi-harness (Cursor + Claude Code + Codex) agent infra
generator with stack-agnostic preset system.
