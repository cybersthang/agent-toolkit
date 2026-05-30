---
title: agent-toolkit — Audit History
generated: 2026-05-26
sessions: 4 audit rounds + 1 external reviewer + ship-blocker discovery + post-v0.21 CI regression + Phase A
current_version: 0.22.0 (TBD pending merge to master)
total_findings: 65+ across all sources
closed_v0_21: 35 (R1: 13, R2: 14, R3: 6, Reg: 2)
closed_v0_22: 2 R4 + Phase A actions (Agent M / N / O)
status: open ship-blockers tracked in `SECTION A`; post-v0.21 work in `SECTION G`; Round 4 + Phase A in `SECTION I`
---

# agent-toolkit — Audit History

4 rounds of internal audit + 1 external reviewer pass + ship-blocker
discovery + post-release CI regression handling + Phase A sprint. This
document is the canonical record of what was found, what was fixed, and
what remains open. It exists so future contributors can answer "did
anyone look at X?" without re-running every round.

## Legend

- **Source**: `R1` = round 1 audit · `R2` = round 2 (locked) · `R3` = round 3 (MCP + installer + precommit) · `Reg` = regression discovered during ship · `Rev` = 3rd-party reviewer
- **Status**: ✅ Fixed · ⚠ Pending commit · 🔴 Open · ⏸ Skip · 🔵 Mitigated

---

## SECTION A — Ship-blockers

| # | Issue | Source | Severity | Status |
|---|-------|--------|----------|--------|
| A1 | CI master fail — pytest-cov dep missing in install step | Reg | BLOCKER | ✅ (commit `0319e9a`) |
| A2 | Author email canonical | Reg | HIGH | ✅ |
| A3 | `.bak.*` not in installer-injected `.gitignore` | R2-F2 | MEDIUM | ✅ (`setup.py:write_gitignore` v0.21) |

---

## SECTION B — Round 1 findings (13/13 fixed)

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| B1 | Hook crash fail-open silently — `is_strict_mode()` default flip | BLOCKER | ✅ |
| H1 | Stop envelope using inline `response` keys, ignoring `transcript_path` | HIGH | ✅ |
| H2 | Stale gap silent auto-expire (no warning emitted) | HIGH | ✅ |
| H3 | High bypass rate not surfaced in session brief | HIGH | ✅ |
| H4 | No 5-layer Searched cross-check in clarification gate | HIGH | ✅ |
| H5 | Dual telemetry (`log_event` vs `emit_fire_event`) → inconsistent metrics | HIGH | ✅ |
| M2 | No `bypass-git-guard:` prompt keyword | MEDIUM | ✅ |
| M3 | TTL mismatch 300 vs 600s (intent_router vs enforcer) | MEDIUM | ✅ |
| M4 | debug_sentry false-positive on weak patterns without traceback context | MEDIUM | ✅ |
| M6 | `.open_gaps.json` write non-atomic | MEDIUM | ✅ |
| M7 | Timezone parsing duplicated 3 hooks (inconsistent formats) | MEDIUM | ✅ |
| M8 | QUICKSTART thiếu bypass tokens + tier adoption sections | MEDIUM | ✅ |
| Bug13 | `last_intent_suggested.json` không unlink khi gate satisfied | HIGH | ✅ |

---

## SECTION C — Round 2 findings (14/14 addressed)

| # | Finding | Severity | Status | Path |
|---|---------|----------|--------|------|
| B2 | Telemetry log files write non-atomic | BLOCKER | ✅ | `_common.py` atomic_write_json |
| B3 | Stop chain 110s + PostToolUse 418s timing | BLOCKER | 🔵 Mitigated | `run_main_safe` wrapper (deep architecture defer v0.22) |
| B4 | `intent_router` 5 state writes non-atomic | BLOCKER | ✅ | `intent_router.py` atomic |
| H6 | 15 hooks missing `emit_fire_event` → 50% telemetry blind | HIGH | ✅ | universal via `run_main_safe` |
| H7 | `evidence_audit._bump_recursion_state` race | HIGH | ✅ | atomic + recursion guard |
| H8 | 11 hooks completely untested | HIGH | ✅ | 10 new test files + 1 rename |
| M9 | `daemon_manager.py:341` PID write race | MEDIUM | ✅ | JSON + atomic |
| M10 | `implement_orchestrator.py:256` cache non-atomic | MEDIUM | ✅ | |
| M11 | `auto_test_runner` + `auto_run_probes` write race | MEDIUM | ✅ | |
| M12 | `intent_router` skill suppression permanent | MEDIUM | ✅ | deferred_skills cache + inject |
| M13 | No `bypass-debug-sentry:` keyword (UX asymmetry) | MEDIUM | ✅ | |
| M14 | `debug_sentry.SKIP_MARKERS` thiếu disclaimers | MEDIUM | ✅ | added `[low-confidence]`, `[unverified]`, `[guess]`, `[TBD]` |
| M15 | `GAP_LIST_EMIT_RE` over-broad | MEDIUM | ✅ | line-start anchor |
| M16 | `complexity_sentinel` + `spec_drift_advisory` no opt-out | MEDIUM | ✅ | enabled-flag |

---

## SECTION D — Round 3 findings (MCP servers + installer + precommit)

### Count: 0 BLOCKER · 3 HIGH · 3 MEDIUM · 2 LOW

### D.HIGH (3) — all closed v0.21

#### H9 — `is_production_like()` false-negative on edge-case DB names — ✅ FIXED

- **Path**: `templates/codex/mcp_servers/realdata_test_server.py:115-127`
- **Trigger (pre-fix)**: Substring match with staging markers checked FIRST → any "staging"/"test"/"clone" → return `False` (NOT prod) even when name contains "prod".
- **Fix**: prod-marker-wins — any prod marker is decisive even if a staging-style marker is also present.

#### H10 — `allow_production_like` flag agent-controllable — ✅ FIXED

- **Path**: `realdata_test_server.py` (around line 355)
- **Trigger (pre-fix)**: Flag came from MCP `arguments` → agent could set `true` itself.
- **Fix**: Moved to env-var-only override that requires a human operator to export in the terminal.

#### H11 — `shell=True` with cmd_str from agent-controlled `expression` argument — ✅ FIXED

- **Path**: `realdata_test_server.py:460-471` (function `run_orm_eval_once`)
- **Trigger (pre-fix)**: `subprocess.run(cmd_str, shell=True, ...)` with cmd built from agent's `expression`. Blacklist had gaps (unicode escape, attribute reconstruction).
- **Fix**: Drop `shell=True`; build a real argv list and feed the read-only ORM script over stdin via subprocess `input=`.

### D.MEDIUM (3) — 2 closed v0.21, 1 deferred

#### M17 — `credential_guard.py` blanket-skip ALL `.env` files — ✅ FIXED

- **Path**: `templates/codex/precommit_hooks/credential_guard.py:102-113`
- **Trigger (pre-fix)**: `rel_path.endswith(".env")` → early return → tracked `app/.env` accidental commits bypassed scanning.
- **Fix**: Use `git check-ignore --quiet <path>` to skip only files git actually ignores; tracked `.env` files now get scanned.

#### M18 — `_looks_placeholder` over-permissive substring match — ✅ FIXED

- **Path**: `credential_guard.py:73-89`
- **Trigger (pre-fix)**: Substring match anywhere → `sk-ant-realkey-fixme-later-xyz` bypassed scan because it contained "fixme".
- **Fix**: Tightened to whole-value / boundary semantics (exact match, short-value starts/ends with marker, or bracket-placeholder).

#### M19 — Odoo presets 13-20 schema-identical with 12 — ⏸ Deferred v0.22

- **Path**: `presets/odoo-13.json` through `presets/odoo-20.json`
- **Trigger**: All 8 presets share top-level keys; only `framework_version` documentation differs.
- **Defer rationale**: Odoo 13 changed `addon_roots` structure (Enterprise unbundled), Odoo 16 added OWL framework dirs. Capturing per-version differences requires research outside this repo. Tracked for v0.22.
- **Mitigation in v0.21**: Preset description string clarifies "Reuses odoo-12 patterns" / "Reuses odoo-17 patterns" so users know what to expect.

### D.LOW (2) — 1 closed v0.21, 1 closed v0.21

#### L1 — `setup.py update` not atomic — ✅ FIXED

- **Path**: `setup.py:383-412`
- **Fix**: Two-pass atomic apply — write to `<file>.tmp` + `os.replace` + per-file `.bak.<timestamp>` backup. Mid-run failure no longer leaves a half-installed project.

#### L2 — `recipe_to_probe_script.py` hardcoded `localhost:8069` fallback — ✅ FIXED (documented)

- **Path**: `templates/codex/tools/recipe_to_probe_script.py:133-141`
- **Fix**: Document env-var precedence in generated script (`TOOLKIT_TEST_URL` > localhost); emit `[probe] WARN` to stderr when falling back to localhost unless `TOOLKIT_TEST_ALLOW_LOCALHOST=1` is set.

---

## SECTION E — 3rd-party reviewer recommendations

### E.1 Accepted (verified valid)

| # | Recommendation | Severity | Effort | Status |
|---|----------------|----------|--------|--------|
| E1 | GitLab Releases with release notes | HIGH | 1h | 🔴 Open (R2 release task) |
| E2 | CI badge top README | HIGH | 30min | ⚠ Pending (after CI green) |
| E3 | Demo GIF terminal asciinema | HIGH | 3-4h | 🔴 Open (R3 polish) |
| E4 | SQLite telemetry persistence | HIGH | 8-10h | 🔴 Open (v0.22) |
| E5 | Reduce autonomy default 4h → 30-60min | HIGH | 15min | 🔴 Open (v0.22) |
| E6 | Better DENY messages with doc links | MEDIUM | 5-8h | 🔴 Open (v0.22) |
| E7 | Troubleshooting + FAQ doc | MEDIUM | 3-4h | 🔵 Partial — `docs/troubleshooting.md` exists |
| E8 | Performance patterns skill (N+1, slow computed fields) | MEDIUM | 4-6h | ✅ (`templates/cursor/skills/odoo/odoo-performance/`) |
| E9 | Multi-company / multi-currency patterns | MEDIUM | 5-8h | ✅ (`templates/cursor/skills/odoo/odoo-multi-company/`) |

### E.2 Skip (wrong premise or unsuitable scope)

| # | Reason |
|---|--------|
| E10 | Reviewer cited fabricated metrics ("47 violations Q1"); SessionStart shows 0 invariants registered — invariants belong in private overlay, not public template |
| E11 | Landing site — time sink for personal/portfolio tool |
| E14 | `--minimal` install flag — the 4 directories are architectural separation, document why instead of cut |
| E15 | Migration assistant skill — over-promise; real Odoo migration = 100s of hours |
| E16 | `Adopters.md` — premature with single maintainer |

---

## SECTION F — Cross-cutting findings

| # | Issue | Source | Severity | Status |
|---|-------|--------|----------|--------|
| F1 | Test coverage measurement reported 13.40% — `setup.py` "never imported" warning dragged total below the gate | Reg | HIGH | ✅ Fixed v0.21 — `.coveragerc source = setup` (module name, not literal path) → coverage now 87%+ on Python 3.8. **Caveat (R1 transparency):** the reported % covers `setup.py` + `lib/` only, NOT `templates/claude/hooks/` (~11k LOC enforcement core). Those hooks are ruff-lint-checked and behavior-tested via subprocess (`tests/test_hooks.py` + per-hook suites) but not line-coverage-measured because they run as subprocesses — so the % is not evidence of hook test depth. |
| F2 | Hook crash log + fire log retention bounded by ring buffer (1000 events) — no SQLite | R2 | HIGH | 🔴 Open (v0.22, overlaps with E4) |
| F3 | No `.gitlab-ci.yml` mirror | Reg | MEDIUM | ✅ Added v0.21 |
| F4 | `_capture_bypass_*` regex requires single-word reason (UX issue across 5 sibling tokens) | R2-F3 | LOW | 🔴 Open |
| F5 | Universal `run_main_safe` timing telemetry → per-fire file write; needs benchmark for high-fire-rate hooks | R2-F4 | MEDIUM | 🔴 Open (v0.22, overlaps with E4) |
| F6 | MCP server layer originally outside the trust boundary used by hooks — D3 (H9/H10/H11) addressed; doc still needed | R3 | HIGH | 🔵 Partial (security fixed; documentation TBD) |
| F7 | **Pytest-cov 7.x subprocess-tracking regression** — pytest-cov 7.x changed the subprocess-coverage activation mechanism from `COV_CORE_SOURCE` (pytest-cov.pth) to `COVERAGE_PROCESS_START` (a1_coverage.pth). Tests like `test_e2e.py` that spawn `setup.py` via subprocess.run lost coverage attribution → `setup.py` measured at 17% on Python 3.10/3.12 (where pip pulled in 7.x) vs 85% on Python 3.8 (where the venv still had 5.x). With default `pytest.ini --cov-fail-under=70` this tripped CI on every matrix cell. | Reg (post-v0.21) | BLOCKER | ✅ Fixed v0.21 with a **root-cause fix that works on both 5.x and 7.x** (no version pin required). Three-part fix: (1) `.coveragerc` adds `parallel = True` + `concurrency = multiprocessing` so each subprocess writes its own data file; (2) `Makefile coverage` target + CI workflows export `COVERAGE_PROCESS_START=<repo>/.coveragerc` to activate the 7.x `.pth` shim; (3) coverage gate moved to a dedicated `coverage` job on Linux + Python **3.12**. Verified: Py3.8 + cov5.x = 87.30%, Py3.10 + cov7.x = 87.73%, Py3.12 + cov6.x = 88.15%. |

---

## SECTION G — Open work for v0.22+

```
v0.21.0 (this release) — closes
  A1, A2, A3, F1, F3, F7
  H9, H10, H11, M17, M18, L1, L2
  E8 (performance skill), E9 (multi-company skill)
  R1 (13/13), R2 (14/14)

v0.21.1 — patch (if needed)
  E2: CI badge in README (after CI green)
  M19 documentation: README "preset 13-20 reuse 12 patterns" note

v0.22 — production hardening (~25h)
  E4: SQLite telemetry persistence (covers F2 + F5)
  E5: Reduce autonomy default 4h → 1h
  E6: Better DENY messages with doc links
  M19: Per-Odoo-version preset deep differentiation
  F4: Multi-word bypass-reason regex
  F6: MCP trust-boundary documentation

v0.23 — content & credibility (parallel, ~15h)
  E1: GitLab/GitHub Releases automation
  E3: Demo asciinema/GIF
  Case-study post (needs F2/E4 SQLite data)
```

---

## SECTION H — Lock contract

**Rule (carried from round 2 lock file)**:
1. Any audit / review after the lock date must cite count exactly:
   - R1: 13 findings (all fixed)
   - R2: 14 findings (13 fixed, B3 mitigated only — deep architecture defer v0.22)
   - R3: 8 findings (7 fixed, M19 defer v0.22)
   - R4: 5 findings (2 resolved v0.22, 3 deferred v0.23 — see SECTION I)
2. Only add a new finding if proof is reproducible (Read/Grep/Bash output citing `path:line`).
3. No drip-feed — close the current audit method's full scope before opening a new one.
4. Reviewer recommendations must be fact-checked before accept (~33% of reviewer items had stale facts or wrong premise).

---

## SECTION I — Round 4 + Phase A (v0.22 cycle)

Round 4 audit focused on Odoo edition coverage gaps surfaced by DEV
review of the v0.21 ship: "the toolkit ships Odoo 12-20 presets but only
9 skills, none of which cover Community vs Enterprise edition split or
performance / multi-company patterns". Phase A (Agents M + N + O) is the
resolution sprint for the 5 R4 findings.

### Round 4 findings (5 total)

| # | Finding | Severity | Status | Resolution |
|---|---------|----------|--------|------------|
| R4-1 | 12 TODO / XXX / FIXME markers leftover from v0.21 ship rush across hooks, skills, MCP servers | MEDIUM | ✅ RESOLVED v0.22 (Agent M) | All 12 markers walked; either fixed inline or converted to tracked findings in this section. |
| R4-2 | Odoo 19 / 20 presets schema-identical with odoo-17 (M19 partial leftover) | MEDIUM | ⏸ DEFERRED v0.23 | Odoo 20 GA late 2026 — not enough upstream signal to differentiate yet. Stub-extend pattern retained. |
| R4-3 | No Community vs Enterprise edition split in skills — agent recommends Enterprise patterns on Community DBs | HIGH | ✅ RESOLVED v0.22 (Agent N) | 3 new edition-aware skills shipped: `odoo-community-patterns`, `odoo-enterprise-patterns`, `odoo-multi-company`. |
| R4-4 | No Enterprise-edition real-data MCP probes — coverage gap for accounting full, Studio, marketing automation | HIGH | ⏸ DEFERRED v0.23 | Requires a shipped Enterprise sandbox; private-overlay territory per E10 rationale. |
| R4-5 | Performance recipes ship as prose only — no `claim-falsification` perturbation per recipe | MEDIUM | ⏸ DEFERRED v0.23 | 10 recipes shipped (`odoo-performance`); falsification harness for each is Axis-3 work tracked separately. |

### Phase A actions (Agent M + N + O)

**Agent M — TODO cleanup** (resolves R4-1):

- Walked 12 outstanding TODO / XXX / FIXME markers identified by grep
  across `templates/claude/hooks/`, `templates/codex/mcp_servers/`,
  `templates/cursor/skills/`. Each marker either: (a) fixed inline,
  (b) converted to a tracked R4 finding above, or (c) downgraded to
  a `# NOTE:` comment with rationale.
- Atomic state writes audited — confirmed all 5 hook state files
  (`.open_gaps.json`, `last_intent_suggested.json`, `.autonomy_active.json`,
  `.skip_*.json`, telemetry log files) use `os.replace` two-pass.

**Agent N — 5 new Odoo skills** (resolves R4-3, partially R4-5):

- Shipped `odoo-community-patterns`, `odoo-enterprise-patterns`,
  `odoo-multi-company`, `odoo-owl-components`, `odoo-performance`
  under `templates/cursor/skills/odoo/`.
- 10 performance recipes across `odoo-12-perf.md`, `odoo-17-perf.md`,
  `odoo-18-perf.md` (3 reference files; each recipe is one `##` section).
- Preset diff deepening — Odoo 13 / 14 / 15 / 16 / 18 / 19 / 20
  presets now carry explicit `addon_roots` / `framework_version` /
  `owl` / `edition` keys (was schema-identical with 12/17).

**Agent O — default invariants seed**:

- Populated `templates/agent_toolkit/invariants.json` with 5 default
  invariants: `no-bare-python`, `no-enterprise-fields-in-community`,
  `multi-company-recordset-guard`, `owl-component-no-jquery`,
  `performance-no-search-in-loop`. Was previously empty `[]` list.

### Status roll-up

```
v0.22.0 (this cycle) — closes
  R4-1 (Agent M — TODO cleanup)
  R4-3 (Agent N — 5 new skills, edition coverage)
  M19 (Agent N — preset diff deepening, residual from R3)
  E8, E9 (already closed v0.21 — confirmed shipped)

v0.23.0 — Q3 candidate
  R4-2: deeper Odoo 19/20 preset population (needs upstream GA signal)
  R4-4: Enterprise sandbox + real-data MCP probes
  R4-5: per-recipe falsification harness for odoo-performance
  E4, E5, E6 (carried from v0.21 deferral)
```
