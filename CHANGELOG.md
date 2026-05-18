# Changelog

All notable changes to agent-toolkit are documented here. Follows Semver:
breaking changes bump MAJOR; feature additions bump MINOR; bug fixes bump PATCH.

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

- Cursor_NAKIVO and any project on toolkit ≥ v0.2 can `setup.py update`
  to get v0.3 without breaking existing customization
  (registries preserved via SKIP_EXISTS on `agent_toolkit/`).
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
