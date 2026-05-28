# Parallel sub-agents without conflicts (v0.25.0)

When you spawn multiple sub-agents in parallel (via the `Agent` / `Task`
tool, multiple calls in a single message), two agents can race-edit the
same file and silently clobber each other's work. The agent-toolkit ships
a **mechanical guard** that makes this race impossible.

## Two pieces

1. **`tools/parallel_wave.py`** — CLI helper. The main agent declares a
   "wave" with file ownership zones BEFORE spawning sub-agents. Writes
   `.agent-toolkit/.parallel_wave.json`.
2. **`parallel_conflict_guard.py`** — PreToolUse hook. On every
   Edit/Write/MultiEdit, checks: is the target file owned by a different
   agent than the one editing? If yes, deny.

Plus the **`parallel-batching` skill** which teaches the model the 5-step
pattern: plan zones → emit manifest → spawn N agents → wait → clear.

## Identity model (what the guard sees)

Claude Code's PreToolUse envelope carries `agent_id` (and `agent_type`)
for sub-agent tool calls — documented in
[hooks.md "Common Input Fields"](https://code.claude.com/docs/en/hooks)
(marked "Only in subagents"). Main-agent Edits have no `agent_id`. The
guard's rule (D8 in the spec):

```
file F is in zone Z, and envelope.agent_id != Z.agent_id → DENY
```

This naturally covers main↔sub and sub↔sub conflicts.

## Quick recipe

```bash
# 1. Declare zones
python tools/parallel_wave.py emit \
    --wave my-wave \
    --zone agent-a:src/feature_x.py,tests/test_feature_x.py \
    --zone agent-b:src/feature_y.py,tests/test_feature_y.py

# 2. Spawn parallel sub-agents in one assistant message (model side):
#    Agent(prompt="You are agent-a, edit only feature_x...")
#    Agent(prompt="You are agent-b, edit only feature_y...")
#
#    If either tries to edit the other's zone, the guard returns
#    permissionDecision=deny on that Edit.

# 3. Clean up
python tools/parallel_wave.py declare-done   # OR `clear`
```

## Zone pattern syntax

A `--zone agent:patterns` zone supports three patterns in `owned`:

| Pattern | Match | Example |
|---|---|---|
| Exact path | only that file | `src/foo.py` |
| Dir prefix (trailing `/`) | any file under that dir (recursive) | `templates/claude/hooks/` |
| Glob (`*`, `?`, `[…]`) | fnmatch on the path | `tests/**/test_*.py` |

Mixing in one zone is allowed.

## Lifecycle

The manifest clears in 4 ways:

- `parallel_wave.py declare-done` — sets `wave_done: true`. Guard treats
  it as cleared.
- `parallel_wave.py clear` — unlinks the file.
- **TTL** — `--ttl` (default 3600 s) auto-expires. Guard treats expired
  manifest as cleared.
- Autonomy off — when `.autonomy_active.json` clears, the manifest is
  also considered stale (next emit must be explicit).

## Bypass (DEV-only, single-shot)

If a cross-zone Edit is truly intentional (rare), type literally in a DEV
prompt:

```
bypass-parallel-guard: <reason ≥ 8 chars>
```

`intent_router` writes a single-shot token consumed by the very next
matching Edit. Symmetric with `bypass-gap-gate:`, `bypass-scope-gate:`,
etc.

## Enforce mode

Default `block` (mirrors sibling guards). Tune via
`.agent-toolkit/enforce_mode.json`:

```json
{ "per_hook": { "parallel_conflict_guard": "warn" } }
```

`warn` allows the Edit but logs a stderr line; `off` is silent allow.

## Cross-platform

Works on Windows + Linux/Ubuntu (and macOS). Paths normalized via
`Path.resolve()` (backslash → forward slash) before zone matching; globs
via `fnmatch` (cross-platform stdlib).

## Anti-patterns

| Bad pattern | Outcome |
|---|---|
| Two zones owning the same file | Both agents block each other — re-split |
| Sub-agent's prompt doesn't match its `agent_id` | Guard can't match → false-positive blocks |
| Forget to clear after wave | TTL auto-expires; or use `clear` |
| Use bypass routinely | Re-plan zones; bypass is for one-off emergencies |

## v0.26 — sub-agent hang detection (multi-transcript)

Conflict-prevention (above, v0.25) catches **two sub-agents writing the
same file**. It does NOT catch **one sub-agent hanging** (529 exhausted,
deadlock, etc.) — that gap is closed by v0.26.

`tools/agent_supervisor.py` auto-activates a multi-transcript mode when
`.parallel_wave.json` is present + autonomy is active. It discovers every
`*.jsonl` in the project's transcript dir whose mtime is newer than the
wave's `created_ts` (and is NOT the main session's transcript), then
checks each one's idle time independently. When any sub-agent transcript
stays idle past `subagent_stall_seconds` (default = `stall_seconds`,
180s), the watcher dispatches ONE aggregate notify per tick listing all
stalled transcripts — channel reused from v0.24 (toast/log/SMTP/webhook),
prefixed `[sub-agent <wave>]` so you can tell it apart from main-session
stalls in your toast/email subject.

**Notify-only** for sub-agents: the toolkit cannot relaunch a sub-agent
(`Agent` / `Task` is model-invoked). When notified, DEV decides: kill the
wave, let it continue, or re-spawn manually.

The v0.24 main-session watcher (with `--relaunch` cap-10 auto-recovery)
keeps running in parallel on the same loop — multi-mode never touches
main-session logic.

## See also

- Spec: `specs/v0.25.0-parallel-subagent-guard.md`,
  `specs/v0.26.0-sub-agent-stall-watcher.md`
- Skill: `templates/cursor/skills/_common/parallel-batching/SKILL.md`
- Sibling: [docs/resilience.md](resilience.md) (v0.24 — 529/hang resilience)
- Hook docs: https://code.claude.com/docs/en/hooks
