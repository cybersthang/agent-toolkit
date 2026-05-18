# Agent-Toolkit — 5-minute Quickstart

For dev who just inherited this project, or for porting to a new
project. **English only** so non-VN devs can onboard.

## TL;DR (90 seconds)

The toolkit catches **"agent reports tests pass, but real-data reveals
bugs"** failures via 5 layers of mechanical enforcement:

1. **Invariant guard** (PreToolUse): blocks Edits that remove
   declared `must_keep_regex` patterns.
2. **PASS-claim contract** (Stop): blocks `tests pass / verified / done`
   claims without an MCP real-data call in the same turn.
3. **Hallucinated-progress checks** (Stop): blocks past-tense action
   claims without matching tool_use, success claims contradicted by
   error tool_results, completion claims while TodoWrite has open
   items, and aggregate over-counts.
4. **Generic claim audit** (Stop): blocks `X is slow / missing / root
   cause` claims without any tool call in the turn.
5. **Pre-commit mirror** (git): same enforcement at commit time so dev
   edits in IDE don't bypass.

## Install in a new project

```bash
# From this repo:
python .codex/tools/agent_toolkit_init.py \
    --target /path/to/your/new/project \
    --stack django-5 \
    --stack-bare django \
    --venv /path/to/your/venv/bin/python
```

Output: copies hooks + commands + tests + tools, writes empty starter
registries + auto-generated `.claude/settings.json` + QUICKSTART.md.

## Verify install

```bash
cd /path/to/your/new/project
python -m unittest discover -s .codex/tests/hooks -p "test_*.py"
```

Expected: 93+ tests pass.

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
/probe-add my-api-list-endpoint
```

Claude will prompt for:
- `description`: "GET /api/v1/items returns ≤500 rows for user X"
- `applies_when.path_globs`: `["app/api/items.py"]`
- `evidence.required_tools`: `["mcp__django_test__run_module_test"]`
- `falsification.runner`:
  ```json
  {
    "target_file": "app/api/items.py",
    "target_line_pattern": "def list_items\\(",
    "sleep_seconds": 2,
    "measurement_command": "curl -s -w '%{time_total}' http://localhost:8000/api/v1/items",
    "expected_delta_seconds": 2.0,
    "tolerance": 0.3
  }
  ```

Now any edit to `app/api/items.py` requires a probe-satisfying MCP
call before Claude can say "PASS". And dev can run:

```bash
python .codex/tools/falsify.py --probe my-api-list-endpoint
```

…to **empirically prove** the endpoint behaves as claimed (or refute
the claim if timing doesn't shift by 2s).

## Slash commands

| Command | When to use |
|---|---|
| `/inv-add <id>` | Durable rule ("always sort by X", "never bypass auth check") |
| `/inv-list` | Audit what's currently enforced |
| `/probe-add <id>` | Feature has verifiable real-data behavior |
| `/probe-coverage` | Pre-merge: which feature files lack a probe? |
| `/adr-add <title>` | Capture WHY behind a decision |
| `/review <scope>` | Exhaustive 3-skill code review with lock-file precedence |

## CLI tools

| Tool | Purpose |
|---|---|
| `.codex/tools/falsify.py --probe <id>` | Run falsification recipe live |
| `.codex/tools/falsify.py --probe <id> --dry-run` | Preview without executing |
| `.codex/tools/agent_toolkit_init.py --target X` | Bootstrap new project |

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
