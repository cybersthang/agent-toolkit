# Changelog

All notable changes to agent-toolkit are documented here. Follows Semver:
breaking changes bump MAJOR; feature additions bump MINOR; bug fixes bump PATCH.

## [0.26.0] — 2026-05-28 — version-bump consolidation + Odoo coverage parity

Aggregate release covering v0.23 → v0.26 features that shipped on `1.0`
branch but never received a `__version__` bump or tag. Plus parity work
to remove asymmetric Odoo coverage flagged by the NAKIVO consumer audit.

**Versioning catch-up**:

- `lib/installer.py:__version__` bumped 0.21.0 → 0.26.0 to match
  branch HEAD (commits `df64d51`, `f266b45`, `a5d5471`, `847d2e5`).
- Tags v0.23.0 / v0.24.0 / v0.25.0 / v0.26.0 published — previously
  only v0.22.0 existed.

**Added (already-shipped features, retroactively versioned)**:

- v0.23 + v0.24: `scope_completeness_gate` Stop hook (R9 manifest pattern)
  · `claim-fix` audit · `agent-resilience-supervisor` tools/.
- v0.25: `parallel_conflict_guard` PreToolUse hook · `parallel-batching`
  skill · `parallel_wave.json` manifest schema for file-disjoint
  sub-agent waves.
- v0.26: `sub-agent-stall-watcher` extension to `tools/agent_supervisor.py`
  + `tools/notify.py` for autonomous run timeout detection (toolkit-side
  only — no consumer-deployable file).

**Added (this release — Odoo coverage parity)**:

- `templates/codex/canonical_decisions.odoo-{13,14,15,16,18,19,20}.json`
  — copies of the odoo-12 17-decision base with `framework_version`
  field swapped + `_per_version_review` note. Closes the audit gap
  where 7/9 Odoo presets fell back to `generic.json` (11 decisions,
  Odoo-agnostic) instead of getting Odoo-specific guidance.
- `presets/odoo-12.json` — added `invariants_overlay` with
  `odoo12-api-multi-required-on-write` (positive guard against copy-paste
  from Odoo 16+ which dropped `@api.multi`).

**Promoted to blocker severity**:

- `no-bare-python-shebang` (warn → blocker)
- `credentials-via-mcp-local-env` (warn → blocker)

Both invariants now DENY edits that strip the required reference,
matching the `feedback_python_venv` + `feedback_credentials` rule
captured by every Odoo consumer's memory pack.

## [0.22.0] — TBD pending merge to master — Odoo edition coverage + 4-axis depth

Q2 / Phase A release. Closes the M19 deferral from v0.21 (per-Odoo-version
preset deep differentiation), broadens skill coverage to Community +
Enterprise editions + OWL frontend + performance, and resolves 12 TODO
markers left over from the v0.21 ship rush (Agent M's work).

Full audit trail at [docs/AUDIT_HISTORY.md](docs/AUDIT_HISTORY.md)
SECTION I (Round 4 + Phase A).

**Added — 5 new Odoo skills** (auto-included by every Odoo preset; bring
total Odoo skill count from 9 → **14**):

- `templates/cursor/skills/odoo/odoo-community-patterns/` — Community
  edition conventions; flag Enterprise-only modules/fields with citations
  so the agent doesn't recommend Studio / marketing-automation patterns
  on a Community DB. Version-aware (12 / 17 references).
- `templates/cursor/skills/odoo/odoo-enterprise-patterns/` — Enterprise
  edition conventions (Studio, accounting full, marketing automation,
  documents). Cross-references invariants so Community installs flag
  hard-coded Enterprise field access.
- `templates/cursor/skills/odoo/odoo-multi-company/` — multi-company /
  multi-currency record rules + `company_dependent` fields + cross-company
  data leak audits. Version-aware.
- `templates/cursor/skills/odoo/odoo-owl-components/` — OWL frontend
  component patterns. Three-tier cascade: Odoo 12 jQuery fallback, 15+
  OWL 1.x, 17+ OWL framework.
- `templates/cursor/skills/odoo/odoo-performance/` — N+1 detection,
  slow computed fields, prefetch context, `read_group(lazy=False)`,
  index API, QWeb `t-cache`. **10 cross-version performance recipes**
  shipped (`references/odoo-12-perf.md`, `odoo-17-perf.md`,
  `odoo-18-perf.md`).

**Added — 4-axis Odoo depth (Q2)**:

- Citations to upstream Odoo docs in every version-specific reference
  file (`references/odoo-<N>-*.md`).
- Preset diff deepening — `presets/odoo-13.json` through
  `presets/odoo-20.json` no longer schema-identical with 12/17; each
  captures version-specific `addon_roots`, framework version, OWL flag,
  and edition default.
- 10 cross-version performance recipes (see above).
- 3 new skills delivered as part of Axis-2 (multi-edition coverage):
  `odoo-community-patterns`, `odoo-enterprise-patterns`,
  `odoo-multi-company`.

**Added — 5 default invariants** shipped with the toolkit preset
(populated into `templates/agent_toolkit/invariants.json`):

- `no-bare-python` — scripts must use venv Python, not bare `python`.
- `no-enterprise-fields-in-community` — Enterprise-only field/module
  access flagged when running against a Community preset.
- `multi-company-recordset-guard` — record rules must honour
  `company_id` constraint on multi-company models.
- `owl-component-no-jquery` — flag jQuery use in OWL component code
  (15+ presets).
- `performance-no-search-in-loop` — `for x in records: self.env[...].search(...)`
  is N+1; surface for review.

**Resolved — 12 outstanding TODO markers** (Agent M / Phase A):

- Stale `XXX:`, `TODO:`, and `FIXME:` markers introduced across the
  v0.21 ship rush — see Round 4 finding R4-1 in
  [docs/AUDIT_HISTORY.md](docs/AUDIT_HISTORY.md).

**Changed**:

- `README.md` — Odoo skill count claim updated 9 → 14; "What's new"
  section added; per-category Odoo skill table.
- `templates/agent_toolkit/QUICKSTART.odoo.md` — new "Available skills"
  section grouping 14 skills by category.
- `docs/AUDIT_HISTORY.md` — new SECTION I (Round 4 + Phase A) appended.

**Deferred to v0.23**:

- **R4-2** — full Odoo 19 / 20 preset population (currently inherits
  from odoo-17 with OWL version delta only).
- **R4-4** — Enterprise-edition real-data MCP probes (depends on a
  shipped Enterprise sandbox; private overlay territory).
- **R4-5** — performance recipe falsification harness (every recipe
  should ship with a `claim-falsification` perturbation; current set
  has prose recipes only).

## [0.21.0] — 2026-05-25 — security hardening + CI fix + rebuild bundle

Closes 8 audit findings (Round 3 security + cross-cutting) and the
post-v0.20 GitHub-Actions-all-cells-red regression. Public-readiness
release: `make rebuild` from a fresh clone produces a reproducible
green state across Linux/macOS/Windows × Python 3.8/3.10/3.12.

Full audit history (3 rounds + reviewer + ship-blockers) is now
documented at [docs/AUDIT_HISTORY.md](docs/AUDIT_HISTORY.md).

**Added**:
- `Makefile` — one-command targets: `make install`, `make test`,
  `make coverage`, `make smoke`, `make dry-run`, `make rebuild`,
  `make clean`. `make rebuild` mirrors the full CI sequence.
- `REBUILD.md` — maintainer guide for clone → verify → push → tag →
  release. Documents the GitHub-mirror workflow including how to push
  the canonical GitLab `master` to a GitHub `main` default branch.
- `.gitlab-ci.yml` — GitLab CI mirror of `.github/workflows/test.yml`.
  3 stages: `test` (matrix Py3.8/3.10/3.12), `lint` (ruff), `coverage`
  (dedicated Py3.8 job enforcing `--cov-fail-under=70`).
- `docs/AUDIT_HISTORY.md` — canonical record of every audit finding +
  its disposition. Imported and sanitized from internal `audit_findings_consolidated.md`.
- `.github/workflows/test.yml` `coverage` job — Linux + Python 3.8 only,
  the one deterministic place coverage gate runs.

**Security fixes** (Round 3):
- **H9** — `is_production_like(database)` now uses "prod-marker wins"
  semantics. Previous logic short-circuited on a staging/test/clone
  marker so a DB named `prod_clone_for_load_test` slipped through as
  non-prod. `templates/codex/mcp_servers/realdata_test_server.py:115-127`.
- **H10** — `allow_production_like` override no longer reads from MCP
  `arguments` dict (agent-controllable). Moved to env var only, so a
  human operator must export it in the terminal.
- **H11** — `run_orm_eval_once` dropped `shell=True`. The previous
  invocation built a single shell command string from agent-controlled
  `expression` input, which opened the blacklist-bypass door. Now uses
  argv list + `subprocess.input=` stdin for the read-only ORM script.
- **M17** — `credential_guard.py` no longer blanket-skips `.env` files
  by extension. Now uses `git check-ignore --quiet` so tracked `.env`
  files (accidental commits — frequent leak source per GitGuardian
  2024) still get scanned.
- **M18** — `_looks_placeholder` tightened from substring match to
  whole-value / boundary match. Previously `sk-ant-realkey-fixme-later-xyz`
  bypassed the scan because it contained "fixme".

**CI / build fixes**:
- **F7 (blocker)** — Root cause: `pytest-cov` 7.x changed the
  subprocess-coverage activation env var (`COV_CORE_SOURCE` →
  `COVERAGE_PROCESS_START`). `test_e2e.py` spawns `setup.py` via
  `subprocess.run`; pytest-cov 5.x captured that subprocess coverage,
  7.x silently dropped it → `setup.py` measured at 17% on Python
  3.10/3.12 vs 85% on 3.8. With the default `--cov-fail-under=70`
  this tripped CI on every matrix cell even with 587 PASS.
  **Root-cause fix (no version pin)**: (1) `.coveragerc` now uses
  `parallel = True` + `concurrency = multiprocessing` so each subprocess
  writes its own data file, (2) `Makefile coverage` target + CI workflows
  export `COVERAGE_PROCESS_START=<repo>/.coveragerc` to activate
  pytest-cov 7.x's `.pth` subprocess-tracking shim, (3) coverage gate
  moved to a dedicated `coverage` job on Linux + **Python 3.12**,
  (4) `--cov-fail-under` removed from `pytest.ini` default addopts
  (coverage still reported via `--cov-report=term-missing`).
  Verified PASS across the full matrix without any pytest-cov pin:
  Py3.8 + cov5.x = 87.30%, Py3.10 + cov7.x = 87.73%, Py3.12 + cov6.x = 88.15%.
- **F1** — `.coveragerc` `source = setup.py` (literal path, unresolvable)
  → `source = setup` (module name). Coverage now correctly tracks
  `setup.py` via `tests/test_setup.py` import. Local total: 13.40% → 87%.
- **F3** — Added `.gitlab-ci.yml` mirror so GitLab MRs get a native
  pipeline + coverage badge.
- **A3** — `setup.py:write_gitignore` now injects `.bak.*` + `*.bak.*`
  into consumer projects so the `.bak.<timestamp>` backups created by
  `setup.py update` stop accumulating in working trees.
- **L1** — `setup.py update` is now atomic. Two-pass: write to
  `<file>.tmp` + `os.replace` + per-file `.bak.<timestamp>` backup. A
  mid-run failure no longer leaves a half-installed project.
- **L2** — `recipe_to_probe_script.py` generated scripts now document
  the env-var precedence (`HOTPOT_BASE_URL` > `TOOLKIT_TEST_URL` >
  localhost fallback) and emit a `[probe] WARN` to stderr when falling
  back to localhost, suppressible via `TOOLKIT_TEST_ALLOW_LOCALHOST=1`.

**Trigger / branch coverage**:
- `.github/workflows/test.yml` and `.gitlab-ci.yml` now trigger on
  release-line branches (regex `[0-9]+.[0-9]+`, e.g. `1.0`) in
  addition to `main` / `master`. Closes W7 (dev branches silently
  skipping CI).

**Docs**:
- README CI badge added (placeholder GitHub org — update via
  `sed -i "s|GITHUB_OWNER_PLACEHOLDER|<YOUR_ORG>|g" README.md` after
  pushing the mirror).
- `docs/AUDIT_HISTORY.md` indexes 60+ findings across 3 internal
  rounds + reviewer + ship-blocker discovery + post-release CI regression.

**Deferred to v0.22**:
- **M19** — preset 13-20 differentiation (currently reuse 12/17
  patterns; Odoo 16+ OWL framework dirs not captured).
- **B3 (deep)** — Stop chain + PostToolUse timing architecture rewrite
  (mitigated via `run_main_safe` wrapper, full redesign deferred).
- **E4 / F2 / F5** — SQLite telemetry persistence + per-fire timing
  benchmark.

## [0.19.0] — 2026-05-24 — gap-completeness-gate Stop hook (chặn drip-feed)

Closes the **drip-feed anti-pattern** captured in memory
`feedback_exhaustive_analysis` (DEV complaint 2026-05-08, recurring
2026-05-24): each "is it done?" check round surfaces new gaps that
should have been caught the first time.

Spec: [specs/v0.19.0-gap-completeness-gate.md](specs/v0.19.0-gap-completeness-gate.md)
— 7 US + 7 AE.

**Added**:
- `templates/claude/hooks/gap_completeness_gate.py` (Stop hook, ~280 LOC,
  default mode `block`):
  - Tracks open gaps via `.agent-toolkit/.open_gaps.json` state file
  - Captures NEW gap emissions (`G<N> — desc` patterns) from response
    text + appends to state
  - BLOCKs Stop on done-claim while ≥1 gap `status: open`
  - 3 resolution tiers in response text:
      1. Fix gap → re-emit, gap auto-clears
      2. `gap-defer: G<N> <reason ≥ 8 chars>` — punt to next sprint
      3. `gap-cant-fix: G<N> <reason>` — escalate to DEV (stderr surface)
  - Whole-gate single-shot bypass: `bypass-gap-gate: <reason>` in prior
    prompt (captured by `intent_router.py`, consumed by hook)
  - Stale TTL 24h — gaps older than that auto-flip to `status: stale`
  - Skips when `.autonomy_active.json` fresh (auto-chain mid-fix safe)
- `templates/claude/hooks/_patterns.py` — 5 new regex:
  `GAP_LIST_EMIT_RE`, `GAP_DEFER_RE`, `GAP_CANT_FIX_RE`,
  `BYPASS_GAP_GATE_RE`, `DONE_CLAIM_GAP_RE`
- `tests/test_gap_completeness_gate.py` — 12 tests across 7 US classes +
  kill-switch. All PASS locally.

**Changed**:
- `templates/claude/hooks/intent_router.py` — `_capture_bypass_gap_gate()`
  helper writes `pending_bypass` field into `.open_gaps.json` when prompt
  matches `bypass-gap-gate: <reason ≥ 8 chars>`.
- `templates/claude/settings.json` — wire `gap_completeness_gate.py` into
  Stop chain at position 4 (after `clarification_gate_enforcer`, before
  `verify_lint`). Stop chain length 10 → 11.
- `tests/test_stop_chain_interactions.py::test_stop_chain_length` —
  update expected count 10 → 11.

**Why it matters**: precedent for the fix pattern = `feedback_no_ai_commit`
memory → `git_guardrails.py` hook. Memory + skill (`gap-fix-cycle`) +
autonomy (`/verify` keeps autonomy ON for fix) form **advice tier**;
without a Stop hook BLOCK, agents drift back to drip-feeding. This hook
is the **mechanical enforcement tier**.


## [0.18.0] — 2026-05-24 — Auto-emit HTML implement-doc sidecar after `/implement`

Closes the "Implement-doc 6/10" weakness from session scoring (5/30 spec
slugs have a sidecar = ~17% adoption). DEV asked HTML for browser review.

Spec: [specs/v0.18.0-implement-doc-uplift.md](specs/v0.18.0-implement-doc-uplift.md)
— 5 US + 6 AE.

**Added**:
- `templates/agent_toolkit/implement-noted.example.html` — self-contained
  HTML template (embedded CSS, badge/checkbox/collapsible visual). 8
  placeholders mapped 1:1 to data extracted in skill Steps 1-5.
- `templates/agent_toolkit/implement_notes.json` — default project config
  shipped at install: `auto_emit: true`, `output_format: both`,
  `enforce: warn`.

**Changed**:
- `templates/claude/commands/implement.md` — new Step 10b: inline-call
  `/implement-notes <slug>` after `/verify` completes, before step 11
  báo cáo. Reads project `output_format` from config. Failure to emit
  is WARN-not-block (DEV can retroactively run `/implement-notes`).
- `templates/claude/commands/implement-notes.md` — accepts
  `--format md|html|both` (default `both`). Output section documents
  2-file emit + schema parity.
- `templates/cursor/skills/_common/implement-notes/SKILL.md` — new Step 6
  detailing HTML render via `str.replace` substitution on the template +
  `html.escape()` safety + per-item block format.
- `templates/claude/hooks/implement_notes_gate.py` — `_expected_formats()`
  reads `.agent-toolkit/implement_notes.json` `output_format` (default
  `md` for legacy installs without config). Hook checks `.md` / `.html` /
  both per setting.
- 4 new tests in `tests/test_implement_notes_gate.py::TestOutputFormatHtmlBoth`
  (html-only, both, both-satisfied, legacy default).

**Resolves**: AGENT-side disclosure surface is now DEV-readable in
browser (collapsible file lists + visual badges) instead of raw Markdown.

---

## [0.13.x] — 2026-05-24 — "làm hết đi" sprint (Odoo-decouple + adopt + public-readiness)

Multi-track sprint covering 3 user requests across one session:
(1) "làm hết đi" — execute 18-item punch-list de-coupling Odoo from toolkit
core; (2) HTML implement-doc for the sprint; (3) public-readiness check
(license + bilingual + star-magnet README).

Spec: ad-hoc composite — no single spec, but 4 forward-looking specs
drafted as P3-LARGE follow-ups (`v0.14.0`/`v0.15.0`/`v0.16.0`/`v0.17.0`).

**Added — framework-overlay machinery** (proves "stack-agnostic core" claim):
- `setup.py` — 2 helpers `_discover_overlay_stems()` + `_classify_overlay()`
  installer logic to pick `<stem>.<framework>.json` per preset's
  `stack.framework`, fall back to `.generic.json`. Marker: `generic`
  variant must exist for stem to qualify as overlay (excludes
  `test_env.schema.json` / `test_env.example.json`).
- `templates/agent_toolkit/coverage_config.{odoo,generic}.json` — split
  the Odoo-flavored feature_globs (addons/controllers/models/wizards/jobs)
  from a stack-neutral generic variant (empty globs, rely on
  `probe_coverage.py` DEFAULT_FEATURE_GLOBS).
- `templates/agent_toolkit/verification.{odoo,generic}.json` — Odoo probe
  list (`odoo_manifest_validate` + addon_globs) vs generic Python lint.
- `templates/agent_toolkit/debug.{odoo,generic}.json` — Odoo exception
  namespaces (`odoo.exceptions.*`, `werkzeug.exceptions.*`) vs generic.
- `templates/agent_toolkit/intent_map.{odoo,generic}.json` — Odoo skill
  routes vs generic (drops `odoo-code-review`, `odoo-tdd`, etc).

**Added — new hooks / commands**:
- `templates/claude/hooks/git_guardrails.py` (PreToolUse Bash) — DENY
  `git commit|push|add|--no-verify|--no-gpg-sign|--force|reset --hard|
  clean -f|branch -D|checkout .|restore .`. Default mode `block`
  (overrides toolkit-wide `warn` per `feedback_no_ai_commit`). Single-use
  bypass: `.agent-toolkit/.skip_git_guard_next.json` TTL 600s consume-on-read.
  Inspired by `mattpocock/skills/misc/git-guardrails-claude-code`
  (MIT — Matt Pocock). Ported bash→Python to match `_common.py` plumbing.
- `templates/claude/commands/constitution.md` — `/constitution` slash command
  for amending the project constitution. Append-only Amendment N: blocks,
  cross-links to `/adr-add` + `/inv-add` on `add`/`supersede`/`remove`.
  Inspired by `github/spec-kit`'s `/speckit.constitution` (MIT).
  Spec-kit's semver + extensions.yml hooks intentionally dropped — toolkit
  already has ADR audit trail.
- `tests/test_git_guardrails.py` — 26 tests across 4 classes (allow paths /
  deny paths / bypass token / enforce mode). All PASS.

**Added — runtime alerts**:
- `templates/claude/hooks/session_brief.py` — 2 new banners:
  (a) kill-switch banner when `AGENT_TOOLKIT_DISABLE=1` (was silent exit,
      now emits warning so DEV knows enforcement is off);
  (b) hook-crash banner showing count of `.hook_crash_log.json` entries in
      last 1h (fail-open kept workflow green but surfaces the silent loss).
- `templates/codex/tools/hook_health.py` — bypass-rate alert: any hook with
  ≥ 20% bypass over ≥ 5 fires gets flagged for ADR review.

**Added — specs (drafted, not implemented)**:
- `specs/v0.14.0-adopt-pattern-scaffold.md` — `/adopt-pattern <url>` scaffold
  to cut adoption friction from 5-7 touchpoints to one slash command.
- `specs/v0.15.0-django-preset-dogfood.md` — Django REST preset as the
  second concrete stack to prove framework-overlay machinery.
- `specs/v0.16.0-topological-hook-order.md` — replace hardcoded hook
  index in tests with constraint-based topological declaration.
- `specs/v0.17.0-posttool-parallel-fire.md` — PostToolUse parallel-fire
  for independent hooks; target 40% latency reduction.

**Added — public-readiness**:
- `NOTICE` — entry #3 (now 4 total): `affaan-m/everything-claude-code` (ECC)
  attribution block with MIT text + 3 adoption points (`verification_loop`,
  `/eval-define`, `/bug-to-test`). Closes gap where ECC patterns were
  adopted but not credited in NOTICE.
- `README.md` — hero rewrite: 6-badge cluster, ≤12-word tagline, fenced
  install in fold, "Why agent-toolkit?" 6-bullet, comparison table
  (vs spec-kit/mattpocock/ECC/Aider), production status block, bilingual
  notice moved to footer (line 744). Research-driven via 8 top-starred
  AI-dev-tooling repos (spec-kit, OpenHands, Cline, Aider, BMAD,
  claude-task-master, claude-flow, LangGraph).
- `templates/agent_toolkit/QUICKSTART.md` — `🇻🇳 Quickstart 5-phút` VN
  section (~120 LOC) mirroring EN content.
- `templates/agent_toolkit/QUICKSTART.odoo.md` — preserved Odoo-specific
  quickstart from the pre-rewrite content.
- `specs/v0.13.x-lam-het-di-sprint.implement-noted.html` — sidecar
  technical-doc for the sprint, 483-LOC self-contained HTML with
  collapsible file checklists, 10 SD / 6 T / 8 F items per
  `implement-noted.example.md` schema.

**Renamed**:
- `templates/codex/canonical_decisions.json` → `canonical_decisions.odoo-12.json`
  for naming consistency with `.generic.json` + `.odoo-17.json` siblings.
- `templates/agent_toolkit/coverage_config.json` → `.odoo.json` (overlay).
- `templates/agent_toolkit/verification.json` → `.odoo.json` (overlay).
- `templates/agent_toolkit/debug.json` → `.odoo.json` (overlay).
- `templates/agent_toolkit/intent_map.json` → `.odoo.json` (overlay).

**Changed — installer**:
- `setup.py` — canonical_decisions fallback changed from unsuffixed
  default (= Odoo 12 default) to `.generic.json`. BREAKING for any
  project that relied on the implicit Odoo 12 default; preset must now
  be explicit. `setup.py` LOC: 845 → 907 (⚠ over 800 budget; pre-requisite
  for `v0.16.0` topological refactor).

**Changed — hooks** (Odoo strip):
- `templates/claude/hooks/debug_sentry.py` — strip `r"odoo\.exceptions\.*"`
  + `r"werkzeug\.exceptions\.*"` from hardcoded `DEFAULT_PATTERNS` +
  `STRONG_PATTERNS`. Framework-specific patterns now live in
  `.agent-toolkit/debug.json` overlay only.
- `templates/claude/hooks/daemon_manager.py` — env keys tuple
  `("PYTHON_BIN","ODOO_CONF","DB")` → read from `test_env.json`'s
  `daemon_env_keys` field; default tuple now stack-neutral
  `("PYTHON_BIN","DB")`.
- `templates/claude/hooks/auto_test_runner.py` — `_doc` rewording: Odoo
  is now framed as the default ship pattern, not the only one.
- `templates/claude/hooks/reuse_probe.py` — strip `.odoo_data` from
  hardcoded `skip_dirs` set; add `.agent-toolkit/reuse_probe.json`
  `extra_skip_dirs` config override.
- `templates/claude/settings.json` — wire `git_guardrails.py` into
  PreToolUse as new matcher group (matcher `Bash`), positioned after
  the existing `Edit|Write|MultiEdit|NotebookEdit` group so
  `invariant_guard.py` stays at `PreToolUse[0]` for chain-order tests.

**Changed — license metadata**:
- `LICENSE` — Copyright holder email switched from work email
  (`thang.vo@nakivo.com`) to personal (`ducthangict.dhtn@gmail.com`).
- `README.md` Author/maintenance section — same switch; work email moved
  to Contributors/acknowledgements with field-test context.
- `CONTRIBUTING.md` — neutral GitLab/GitHub framing (was "GitHub Discussion").

**Fixed**:
- `tests/test_stop_chain_interactions.py::test_stop_chain_length` — count
  9 → 10 (matches actual `settings.json` Stop chain post-v0.13.0).
- `tests/test_git_guardrails.py` — `PY` fallback `sys.executable` instead
  of hardcoded `/home/voducthang/NAKIVO/venv/bin/python`.
- `tests/test_debug_sentry_split.py::test_odoo_exception_qualified_matches`
  — rewritten to assert NEW structure (`odoo.exceptions` pattern lives in
  `debug.odoo.json` overlay, NOT in hook's hardcoded defaults).
- `templates/CLAUDE.md` — hook table + slash command list updated for new
  `git_guardrails` + `/constitution`; upstream attribution table grew
  4 → 5 rows.

**Tests**: full suite GREEN final run (`pytest tests/ --no-cov -q` →
`[100%]`, 0 failures, ~580 tests).

**Migration**: `setup.py update` re-runs framework-overlay picker. Projects
already installed: existing `.agent-toolkit/{coverage_config,verification,
debug,intent_map}.json` are preserved (`SKIP_EXISTS` rule) — no auto-merge.
Projects re-installing get the correct overlay per their preset.


---

*Older versions (pre-v0.13.0) -> [CHANGELOG_ARCHIVE.md](CHANGELOG_ARCHIVE.md)*
