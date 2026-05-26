# Agent-Toolkit — 5-minute Quickstart

For an Odoo dev who just inherited this project, or for installing the
toolkit into a fresh Odoo workspace. **English** version; Vietnamese
guide is at the toolkit repo root (`USAGE.md`).

## TL;DR (90 seconds)

The toolkit is for **Odoo projects** (12 / 17 / future Odoo majors). It
bundles:

- A **Spec Kit-aligned spec-driven workflow** — DEV runs `/plan` +
  `/clarify`, agent auto-chains `/tasks` → `/analyze` → `/implement` →
  `/verify` under autonomy.
- **Odoo MCP servers**: codebase / postgres / realdata_test / JIRA.
- **Mechanical enforcement** that catches "agent reports tests pass,
  but real-data reveals bugs" failures via 5 layers:

  1. **Invariant guard** (PreToolUse): blocks Edits that remove
     declared `must_keep_regex` patterns.
  2. **PASS-claim contract** (Stop): blocks `tests pass / verified /
     done` claims without an MCP real-data call in the same turn.
  3. **Hallucinated-progress checks** (Stop): blocks past-tense action
     claims without matching tool_use, success claims contradicted by
     error tool_results, completion claims while TodoWrite has open
     items, and aggregate over-counts.
  4. **Generic claim audit** (Stop): blocks `X is slow / missing / root
     cause` claims without any tool call in the turn.
  5. **Pre-commit mirror** (git): same enforcement at commit time so
     dev edits in IDE don't bypass.

## Install in a new project

The main install path is `setup.py init` at the toolkit root (NOT the
internal `.codex/tools/agent_toolkit_init.py` — that's a legacy
bootstrap script).

```bash
# Clone toolkit (once per machine)
git clone <toolkit-repo> ~/agent-toolkit

# Install into an Odoo project
python ~/agent-toolkit/setup.py init /path/to/your/odoo/project \
    --preset odoo-12 \                  # or odoo-17 / generic
    --python /path/to/venv/bin/python \
    --yes
```

Output: copies hooks + commands + tests + tools + Spec Kit skills,
seeds `.agent-toolkit/constitution.md` + canonical_decisions registry +
auto-generated `.claude/settings.json` + `.mcp.json`.

## Verify install

```bash
cd /path/to/your/new/project
python -m pytest .codex/tests/hooks/ -v
```

Expected: 120+ tests pass.

Open Claude Code in the project → SessionStart hook shows
`Registry loaded: 0 invariant · 0 probe`. You're live.

## Register your first invariant (2 minutes)

In Claude Code, type:
```
/inv-add no-bare-python
```

Claude will prompt for:
- `description`: "Scripts must use venv Python, not bare `python`"
- `applies_to`: `["scripts/**/*.py", "tools/**/*.py"]`
- `rules.must_keep_regex`: `["sys\\.executable|VENV_PYTHON"]`
- `severity`: `warn`

Claude writes the entry to `.agent-toolkit/invariants.json` + smoke-
tests the hook + reports.

## Register your first probe (3 minutes)

In Claude Code, type:
```
/probe-add load-views-blocking
```

Claude will prompt for (example Odoo 12 controller):
- `description`: "GET /web/dataset/load_views must block UI until response"
- `applies_when.path_globs`: `["<addon>/controllers/web.py"]`
- `evidence.required_tools`: `["mcp__realdata_test__run_smoke_test"]`
- `falsification.runner`:
  ```json
  {
    "target_file": "<addon>/controllers/web.py",
    "target_line_pattern": "def load_views\\(",
    "sleep_seconds": 2,
    "measurement_command": "curl -s -w '%{time_total}' http://localhost:8069/web/dataset/load_views",
    "expected_delta_seconds": 2.0,
    "tolerance": 0.3
  }
  ```

Now any edit to `<addon>/controllers/web.py` requires a probe-satisfying
MCP call before Claude can say "PASS". And dev can run:

```bash
python .codex/tools/falsify.py --probe load-views-blocking
```

…to **empirically prove** the endpoint behaves as claimed (or refute
the claim if timing doesn't shift by 2s).

## Slash commands

**Spec Kit workflow (the main path)**:

| Command | When to use |
|---|---|
| `/plan <feature>` | Phase 1 — turn a feature ask into a structured spec |
| `/clarify <slug>` | Phase 2 — DEV interview to close every Open Question |
| `/tasks <slug>` | Phase 3 — auto-fired by `/clarify`; can re-emit manually |
| `/analyze <slug>` | Phase 3.5 — cross-artifact lint (auto-fired by `/implement`) |
| `/implement <slug>` | Phase 4 — autonomy ON, execute tasks, auto-verify |
| `/verify <slug>` | Phase 5 — real-data probes, emit PASS/GAP/BLOCKER report |

**Toolkit meta** (durable rules + decisions):

| Command | When to use |
|---|---|
| `/inv-add <id>` | Durable rule ("always sort by X", "never bypass auth check") |
| `/inv-list` | Audit what's currently enforced |
| `/probe-add <id>` | Feature has verifiable real-data behavior |
| `/probe-coverage` | Pre-merge: which feature files lack a probe? |
| `/adr-add <title>` | Capture WHY behind a decision |
| `/review <scope>` | Exhaustive 3-skill code review with lock-file precedence |

## Available skills

14 Odoo skills ship with every Odoo preset (all version-aware — Step 0
reads `__manifest__.py` and loads the matching `references/odoo-<N>-*.md`).
Grouped by intent:

**Core workflow** (day-to-day Spec Kit work):

| Skill | One-line |
|---|---|
| `odoo-code-patterns` | Canonical model / wizard / view / OWL patterns per Odoo major. |
| `odoo-code-review` | Exhaustive single-pass review with PROOF + Doubt-pass line per finding. |
| `odoo-codebase-discovery` | MCP-first discovery via `discover_modules` / `read_manifest`. |
| `odoo-debug-troubleshoot` | Per-version pitfall tables — fast quick-fix lookup. |
| `odoo-tdd` | Red-Green-Refactor + perturb-test routing for Odoo modules. |

**Multi-edition** (Community vs Enterprise vs multi-company):

| Skill | One-line |
|---|---|
| `odoo-community-patterns` | Community-only conventions; flag Enterprise-only access. |
| `odoo-enterprise-patterns` | Enterprise modules (Studio, accounting full, marketing automation). |
| `odoo-multi-company` | Multi-company record rules + `company_dependent` fields. |

**Frontend**:

| Skill | One-line |
|---|---|
| `odoo-owl-components` | OWL components — 12 jQuery fallback, 15+ OWL 1.x, 17+ OWL framework. |

**Performance**:

| Skill | One-line |
|---|---|
| `odoo-performance` | N+1, computed-field tuning, prefetch, indexes. 10 cross-version recipes. |

**Operations**:

| Skill | One-line |
|---|---|
| `odoo-jira-workflow` | JIRA MCP tool wiring for ticket workflows. |
| `odoo-module-scaffold` | Bootstrap a new Odoo module with the right skeleton per version. |

**Discovery**:

| Skill | One-line |
|---|---|
| `odoo-data-verification` | Real-DB ORM probes via `realdata_test` MCP. |
| `odoo-deterministic-answers` | `canonical_decisions.json` registry workflow. |

## CLI tools

| Tool | Purpose |
|---|---|
| `.codex/tools/falsify.py --probe <id>` | Run falsification recipe live |
| `.codex/tools/falsify.py --probe <id> --dry-run` | Preview without executing |
| `.codex/tools/agent_toolkit_init.py --target X` | Bootstrap new project |

## ⚠️ Breaking change v0.20 — Strict mode

From v0.20.0, `is_strict_mode()` defaults to **fail-CLOSED** (True).
Previously hooks were fail-open: a Python exception in a hook → exit 0
(silent allow). Now they fail-closed: exception → exit 1 (blocks the
response).

**If you see hooks suddenly blocking after upgrading**, set:

```bash
# Bash/zsh — revert to legacy fail-open behavior
export AGENT_TOOLKIT_NO_STRICT=1

# PowerShell
$env:AGENT_TOOLKIT_NO_STRICT = "1"
```

Or add to `.claude/settings.json`:
```json
{
  "env": { "AGENT_TOOLKIT_NO_STRICT": "1" }
}
```

The old `AGENT_TOOLKIT_STRICT=1` opt-in is retired. The new opt-out is
`AGENT_TOOLKIT_NO_STRICT=1`.

---

## Bypass & Skip Tokens

One-shot keywords to pre-authorize a single agent operation without
disabling enforcement globally. All tokens are single-use and expire
after 600s.

| Keyword in prompt | Effect | Token file |
|---|---|---|
| `bypass-invariant: <id>` | Allow ONE Edit that removes an invariant pattern | `.agent-toolkit/.bypass_next_edit.json` |
| `skip-clarification: <reason ≥ 8 chars>` | Allow ONE response without UNDERSTANDING/ASSUMPTIONS/QUESTIONS markers | `.agent-toolkit/.skip_clarification_next.json` |
| `bypass-gap-gate: <reason ≥ 8 chars>` | Allow ONE "done" claim while gaps remain open | `.open_gaps.json` `pending_bypass` field |
| `bypass-git-guard: <reason ≥ 8 chars>` | Allow ONE agent-driven `git commit/push/add` | `.agent-toolkit/.skip_git_guard_next.json` |

**Example usage**:
```
bypass-git-guard: deploy hotfix to production — emergency bypass
```
Agent receives the prompt → intent_router writes the bypass token →
git_guardrails allows the next matching git command → token consumed.

---

## Tier Adoption — 3-week rollout plan

For teams inheriting this toolkit mid-project:

**Week 1 — Observe only** (set all hooks to `warn`):
```json
// .agent-toolkit/enforce_mode.json
{
  "default": "warn",
  "per_hook": {}
}
```
Check SessionStart hook-health stats. Identify which categories trigger
most blocks. Tune `disabled_progress_checks` for project vocabulary.

**Week 2 — Selective block** (flip highest-signal hooks):
```json
{
  "default": "warn",
  "per_hook": {
    "evidence_audit": "block",
    "invariant_guard": "block"
  }
}
```
These two have lowest false-positive rate. Leave `debug_sentry` and
`gap_completeness_gate` on `warn` until the project vocab is tuned.

**Week 3 — Full block** (remove enforce_mode.json or set default block):
```json
{
  "default": "block"
}
```
At this point the bypass/skip tokens are your safety valve for
legitimate one-off exceptions.

---

## When the toolkit blocks you (cheat sheet)

| Block message starts with | Fix in 30 seconds |
|---|---|
| `[invariant-guard] Edit vi phạm...` | Restore the missing pattern OR add `bypass-invariant: <id>` to next user prompt |
| `[evidence-audit] PASS/DONE/VERIFIED claim detected` | Run the required MCP tool OR add `probe-skip: <id|all> <reason>` to response |
| `[evidence-audit] Hallucinated-progress` | Remove past-tense claim OR add `progress-skip: <category|all> <reason>` |
| Generic claim audit (slow/missing/root cause) | Tag claim `[assumption]` OR run Read/Grep first |
| Pre-commit fails | `git commit --no-verify` (single-commit bypass; audit logged) |

## Kill-switch (emergency)

If hooks are broken and you can't bypass per-call:

```bash
# Disable ALL hook enforcement for this terminal session
export AGENT_TOOLKIT_DISABLE=1
```

Re-enable: `unset AGENT_TOOLKIT_DISABLE` (or `Remove-Item Env:AGENT_TOOLKIT_DISABLE` on PowerShell).

## Telemetry

Every hook decision logs to `.codex/logs/hook_events.jsonl`. After 200
events, `session_brief` shows:

```
Hook health (last 200 events): 12 block (6%), 4 bypass · top: action_ghost=8, generic_claim=4
```

Use this to tune regex thresholds OR identify "always-bypassed"
categories worth disabling per project via
`.agent-toolkit/acceptance-probes.json` → `_defaults.disabled_progress_checks`.

## Where to dig deeper

- `.agent-toolkit/README.md` — full architecture
- `.agent-toolkit/PORTING.md` — porting to non-Odoo stacks
- `.agent-toolkit/decision-log.md` — ADRs explaining each design choice
- `.codex/tests/hooks/` — 93+ test cases as executable spec

## Common mistakes

1. **Registering empty probes.** A probe with `must_keep_regex: []`
   surfaces in SessionStart but enforces nothing. Always include real
   regex/tools/falsification.
2. **Hardcoding module names in invariants.** Use globs
   (`addons/**/models/**.py`), not specific modules — see ADR-005.
3. **Bypassing without reason.** `probe-skip: all` without rationale
   defeats the audit trail. Always include `<reason>`.
4. **Not running `/probe-coverage` before merge.** The pre-commit gate
   catches it but takes longer than the in-session command.

## Cost vs value

In-session friction: ~3-5% of responses blocked initially, drops to
<1% after 1 week of tuning invariants/probes/disabled_progress_checks
for your project's vocabulary. Trade-off: catches ~80% of "I claimed
done but actually didn't run real verification" failures that would
otherwise reach PR review.

Not worth installing if: your team relies on heavy human PR review and
agent autonomous workflow is minimal. Worth installing if: agents
write code that lands on `main` with limited human review.
