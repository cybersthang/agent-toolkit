# Porting `agent-toolkit` to another project

This document is the **stack-agnostic install + adapt guide**. The
toolkit is currently bundled with an Odoo 12 stack overlay but the
core enforcement layers (invariants, acceptance probes, evidence-audit
hooks) are decoupled from any specific framework.

> **Tip**: for project-specific defaults (addon roots, internal JIRA
> URLs, custom DB name, Vietnamese response language, etc.), don't fork
> the whole toolkit — drop a **private preset overlay** that `extends`
> a public preset. A copy-paste seed lives at
> [`presets/_example_private_overlay.json.template`](../../presets/_example_private_overlay.json.template).
> Strip the `.template` suffix in your fork; the public toolkit loader
> ignores `.template` files so you can ship the seed safely.

## What's portable as-is

| Component | Path | Stack-agnostic? |
|---|---|---|
| `invariant_guard.py` | `.claude/hooks/` | ✅ regex/glob-only, no Odoo refs |
| `evidence_audit.py` + `_audit/` package | `.claude/hooks/` | ✅ transcript-shape agnostic |
| `session_brief.py` | `.claude/hooks/` | ✅ generic SessionStart brief |
| `intent_router.py` | `.claude/hooks/` | ✅ reads `intent_map.json` at runtime |
| `invariants.json` schema | `.agent-toolkit/` | ✅ |
| `acceptance-probes.json` schema | `.agent-toolkit/` | ✅ |
| `coverage_config.json` | `.agent-toolkit/` | ✅ — adjust feature_globs per stack |
| `decision-log.md` | `.agent-toolkit/` | ✅ ADR convention |
| `/inv-add`, `/inv-list`, `/adr-add`, `/probe-add`, `/probe-coverage`, `/review` | `.claude/commands/` | ✅ workflow-only |
| Pre-commit hooks (`probe_coverage`, `probe_suggest`, `invariant_guard_precommit`, `credential_guard`) | `.codex/precommit_hooks/` | ✅ filesystem-only |
| Falsifier CLI (`falsify.py`) | `.codex/tools/` | ✅ reads probe schema; works for any stack with curl-able endpoint |
| Hook tests (82 cases) | `.codex/tests/hooks/` | ✅ `sys.executable` + tempfile workspace |

## What needs adapting per project

| Item | Where | What to change |
|---|---|---|
| Stack name in routing | `.agent-toolkit/intent_map.json` | `stack` / `stack_bare` fields. Skill name placeholders `{stack}` / `{stack_bare}` resolve automatically. |
| Real-data MCP tool prefixes | `.agent-toolkit/acceptance-probes.json` `_defaults.required_tool_prefixes` | `["mcp__realdata_test__", "mcp__postgres__"]` → your project's MCP server prefixes |
| Skill files | `.cursor/skills/` | Drop in your stack's skill set (e.g. `django-5-data-verification`) |
| Python venv path | Pre-commit + tests | Set `{{ENV_PREFIX}}_PYTHON_BIN` env var to your project's interpreter |
| Per-feature probes | `.agent-toolkit/acceptance-probes.json` | `probes: []` → register your own via `/probe-add` |
| Project invariants | `.agent-toolkit/invariants.json` | `invariants: []` → register via `/inv-add` |
| ADRs | `.agent-toolkit/decision-log.md` | Empty out the existing ADR-001..005 if not relevant; keep the schema header |

## 1-pager install steps (new project)

```
# 1. Copy toolkit files (preserves directory structure)
cp -r <source>/.claude/hooks/      <target>/.claude/
cp -r <source>/.claude/commands/   <target>/.claude/
cp -r <source>/.agent-toolkit/     <target>/
cp -r <source>/.codex/tests/hooks/ <target>/.codex/tests/
cp <source>/.codex/precommit_hooks/* <target>/.codex/precommit_hooks/
cp <source>/.pre-commit-config.yaml <target>/

# 2. Configure .claude/settings.json to point at hooks (path absolute)
#    See sample in <source>/.claude/settings.json.

# 3. Set env var for Python interpreter
export {{ENV_PREFIX}}_PYTHON_BIN=/path/to/your/venv/bin/python
# (Windows PowerShell: $env:{{ENV_PREFIX}}_PYTHON_BIN = "...")

# 4. Adapt intent_map.json for your stack
#    Edit .agent-toolkit/intent_map.json:
#      - "stack": "django-5"  (or "rails-7", etc.)
#      - "stack_bare": "django"
#    Skill placeholders {stack}/{stack_bare} resolve at hook load.

# 5. Empty out invariants + probes
#    .agent-toolkit/invariants.json: "invariants": []
#    .agent-toolkit/acceptance-probes.json: "probes": []
#    .agent-toolkit/decision-log.md: clear ADR-001..NNN section

# 6. Update _defaults for your stack
#    Edit .agent-toolkit/acceptance-probes.json `_defaults`:
#      "required_tool_prefixes": ["mcp__<your_test_server>__"]

# 7. (Optional) install pre-commit
pip install pre-commit
pre-commit install

# 8. Verify hook smoke test runs
${{ENV_PREFIX}}_PYTHON_BIN -m unittest discover -s .codex/tests/hooks -p "test_*.py"
```

## Stack-specific overlays you'd write

For a non-Odoo project, you'd create skill files matching the
`{stack}-*` placeholders that `intent_map.json` references:

- `.cursor/skills/<stack>-code-review/SKILL.md` — stack-specific
  review dimensions (e.g. Django: signals, middleware order, ORM N+1)
- `.cursor/skills/<stack>-data-verification/SKILL.md` — how to query
  real data through your project's MCP server
- `.cursor/skills/<stack>-debug-troubleshoot/SKILL.md` — common
  failure modes for your stack
- `.cursor/skills/<stack>-tdd/SKILL.md` — Red-Green-Refactor adapted
  to your test framework
- `.cursor/skills/<stack>-codebase-discovery/SKILL.md` — MCP-driven
  exploration for your repo
- `.cursor/skills/<stack>-module-scaffold/SKILL.md` — scaffolding
  conventions
- `.cursor/skills/<stack>-jira-workflow/SKILL.md` — ticket→PR→merge
  flow (or other tracker)

Without these overlays, the intent_router still suggests
`code-review` + `doubt-driven-review` + the Spec Kit chain
(`plan-feature` → `clarify` → `tasks-breakdown` → `analyze-artifacts` →
`verify-feature`) — stack-agnostic core skills.

## Smoke-test after porting

```
${{ENV_PREFIX}}_PYTHON_BIN -m unittest discover -s .codex/tests/hooks -p "test_*.py" -v
```

Expected: ≥38 tests, all OK. If anything fails, the issue is most
likely:
- Pre-commit hook entry references a different path than your project.
- `acceptance-probes.json` `_defaults` mention an MCP prefix not present.
- Python interpreter path mismatch — check `sys.executable` in tests.

## Known portability gaps

1. **Slash command docs are bilingual VN/EN.** If your team works in
   another language, translate the prose; the workflow steps are
   stack-agnostic.
2. **MCP server prefixes in code-review skill examples** hardcode
   `mcp__postgres__query_readonly` and `mcp__realdata_test__*`. Swap
   to your MCP names in the SKILL.md examples — not enforced by hook.
3. **Pre-commit script `entry: python .codex/precommit_hooks/...`**
   resolves `python` via PATH. If your project requires venv binding,
   change to `entry: ${VENV_PATH}/python ...` or set up via
   `pre-commit-hooks`.

## When to install — comparison vs alternatives

agent-toolkit is **not free**. Below table compares to alternatives so
you can decide if your project fits.

| Property | agent-toolkit | Plain CI step (run user's pytest) | PR template + manual checklist | Code review only |
|---|---|---|---|---|
| Catches "agent claimed pass but didn't verify" | ✅ at Stop hook (in-session) | ⚠ only at PR time | ❌ relies on dev discipline | ❌ relies on reviewer attention |
| Catches "agent edits violate durable rule" | ✅ at PreToolUse | ✅ if rule is a lint check | ❌ | ❌ |
| Catches "agent invents file:line citations" | ✅ at Stop | ❌ | ❌ | ⚠ if reviewer cross-checks |
| Catches `time.sleep` blocking claim falsified | ✅ via `falsify.py` CLI | ⚠ if dev writes timing test | ❌ | ❌ |
| Cost — install | 1-3 hour for new project (PORTING.md) | 30 min (CI YAML) | 5 min | 0 |
| Cost — per-feature setup | `/probe-add` per controller (~5 min) | 0 incremental | 0 | 0 |
| Cost — false positive (in-session) | ~3-5% before tuning, <1% after | N/A | N/A | Reviewer judgment |
| Ramp-up for new team member | 2-3 hour read + 1 week to internalize bypass markers | None | None | None |
| Failure mode if hooks break | Fail-open (per-hook), kill-switch via env var | CI red → can override | None | None |

**Recommended for:**
- Projects where autonomous agents land code on `main` without human review.
- Multi-day agent task runs where mid-stream hallucination has compounding cost.
- Teams that observed pattern "agent reports pass → dev re-tests → finds bugs"
  and want mechanical prevention.

**Not recommended for:**
- Solo-dev projects with light agent involvement.
- Projects where every PR has a thorough human review.
- Teams not willing to invest 1-3h per new project + ongoing maintenance of
  `acceptance-probes.json` + `invariants.json`.

If you're not sure, install with 0 probes/invariants registered. The
hooks are no-ops until you populate the registries. Add probes for
the 3 highest-risk features first. After 2 weeks, decide if value
justifies expanding.

## Optional integrations

### Playwright (browser-level falsification)

Toolkit ships `falsification.type: "playwright"` for probes that need
real browser verification (page load timing, click-then-assert, UI
flow). The falsifier CLI spawns `npx playwright test <spec>` and parses
the JSON reporter output.

**Setup (one-time per project):**

```bash
# 1. Install Playwright in your project (NOT bundled with toolkit)
npm init -y           # if package.json doesn't exist
npm install -D @playwright/test
npx playwright install   # downloads browser binaries

# 2. Add your test spec, e.g. tests/e2e/load_views.spec.ts
```

**Probe schema example:**

```json
{
  "id": "load-views-e2e",
  "description": "load_views must render UI < 1s with cached partner",
  "applies_when": {"path_globs": ["**/controllers/**.py"]},
  "evidence": {"required_tools": ["mcp__realdata_test__run_smoke_test"]},
  "falsification": {
    "type": "playwright",
    "description": "E2E test verifies page load completes < 1s",
    "runner": {
      "spec_file": "tests/e2e/load_views.spec.ts",
      "browser": "chromium",
      "timeout_ms": 30000,
      "workers": 1
    }
  },
  "severity": "blocker"
}
```

**Run via CLI:**

```bash
python .codex/tools/falsify.py --probe load-views-e2e
# or dry-run to preview command
python .codex/tools/falsify.py --probe load-views-e2e --dry-run
```

**Verdict mapping:**

- All tests passed + `npx` rc=0 → PROVEN (rc=0)
- Any test failed or timedout → REFUTED (rc=1)
- `npx` not installed / spec missing / sandbox reject → ERROR (rc=2)

### Playwright MCP server (agent browser control during grill)

If DEV wants the agent to interactively drive the browser DURING grill
phase (`mcp__playwright__navigate`, `mcp__playwright__click`,
`mcp__playwright__screenshot`, etc.) — install Microsoft's official
Playwright MCP server SEPARATELY:

```bash
# Install (one-time)
npx @playwright/mcp@latest install

# Register in your Claude Code MCP config
# (Read https://github.com/microsoft/playwright-mcp for details)
```

agent-toolkit does NOT bundle the MCP server — it's a Node.js app from
Microsoft. Once installed, agent can use `mcp__playwright__*` tools and
clarification-gate skill's PROBE_READINESS block will accept those tools
in the `evidence.required_tools` field.

### Other MCP servers to consider

| Server | Use case | Where to get |
|---|---|---|
| Playwright | Browser automation | github.com/microsoft/playwright-mcp |
| Puppeteer | Alternative browser automation | github.com/modelcontextprotocol/servers |
| Postgres (custom) | Read-only SQL queries | shipped: `.codex/mcp_servers/postgres_server.py` |
| GitHub | PR/issue operations | github.com/modelcontextprotocol/servers |

## Backwards compatibility

The toolkit is internally versioned via:
- `invariants.json` `version` field (currently 2)
- `acceptance-probes.json` `version` field (currently 2)
- `intent_map.json` schema (currently flat — no version field yet,
  treat as v1)

Future updates that change schema MUST bump version + provide a
migration note. Older versions stay readable; the hook is
forward-tolerant (missing fields use defaults).
