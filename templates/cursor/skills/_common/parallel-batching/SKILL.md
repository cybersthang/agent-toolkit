---
name: parallel-batching
description: Use this skill BEFORE spawning multiple sub-agents (Agent / Task tool) in parallel to do disjoint work. It guides you to declare a file-ownership manifest so the `parallel_conflict_guard` PreToolUse hook can mechanically block any sub-agent (or the main agent) from editing a file owned by a different concurrent sub-agent. Without the manifest, two sub-agents that happen to touch the same file produce silent race conflicts. Read this whenever you plan a parallel fan-out — even a 2-agent fan-out benefits from the declaration. Pairs with `tools/parallel_wave.py` (CLI) and `parallel_conflict_guard.py` (Stop-chain guard hook).
---

# Parallel batching — file-disjoint sub-agent waves (v0.25.0)

> Mechanical guard, not honor system. Toolkit cannot make the model spawn
> sub-agents — that's the model's job. But once you spawn N sub-agents in
> parallel, the guard ensures they CANNOT clobber each other's files.

## When to apply

- You're about to call the `Agent` / `Task` tool 2+ times in a single
  message (parallel fan-out).
- The work is naturally **file-disjoint** — each sub-agent owns a distinct
  set of files (different hooks, different test modules, different docs).
- You want a hard guarantee that two sub-agents won't race-edit the same
  file, instead of trusting them to behave.

## When to SKIP

- You're spawning ONE sub-agent (no concurrency, no conflict possible).
- The sub-agents share write access to the same file by design (rare —
  reconsider the task split).
- The fan-out is read-only (no Edit/Write) — the guard only fires on
  Edit/Write/MultiEdit/NotebookEdit, so read-only fan-outs are untouched.

## The 5-step template (dogfood: Wave A v0.21 ran this and shipped 0 conflicts)

### Step 1 — Plan zones file-disjoint

For each sub-agent, list the files it will edit. **Zones must not overlap**.
Use the smallest precise expression:

| Want | Pattern |
|---|---|
| One file | `templates/claude/hooks/foo.py` |
| Whole dir (recursive) | `templates/claude/hooks/` (trailing `/`) |
| Glob | `templates/claude/hooks/*_gate.py` or `tests/**/test_x.py` |

Worked example (real Wave A pattern):

| Sub-agent | Owned files |
|---|---|
| `wave-a-1` | `templates/claude/hooks/probe_coverage_gate.py`, `tests/test_probe_coverage_gate.py` |
| `wave-a-2` | `templates/claude/hooks/bypass_rate_alarm.py`, `tests/test_bypass_rate_alarm.py` |
| `wave-a-3` | `templates/claude/hooks/_audit/cross_source.py` |

### Step 2 — Emit the manifest via CLI helper

```bash
python tools/parallel_wave.py emit \
    --wave wave-a-quickwins \
    --zone wave-a-1:templates/claude/hooks/probe_coverage_gate.py,tests/test_probe_coverage_gate.py \
    --zone wave-a-2:templates/claude/hooks/bypass_rate_alarm.py,tests/test_bypass_rate_alarm.py \
    --zone wave-a-3:templates/claude/hooks/_audit/cross_source.py \
    --ttl 3600
```

This writes `.agent-toolkit/.parallel_wave.json`. `parallel_conflict_guard`
starts enforcing immediately on the next Edit/Write.

### Step 3 — Spawn the sub-agents in ONE message

Multiple Agent tool calls in a single assistant message → they run in
parallel. Pass the agent's owned zone in its prompt so it knows what to
edit:

```
Agent(subagent_type="general-purpose", description="Wave A-1",
      prompt="You are wave-a-1. Only edit your owned files: ...")
Agent(subagent_type="general-purpose", description="Wave A-2",
      prompt="You are wave-a-2. Only edit your owned files: ...")
Agent(subagent_type="general-purpose", description="Wave A-3",
      prompt="You are wave-a-3. Only edit your owned files: ...")
```

If a sub-agent tries to edit outside its zone (e.g. wave-a-1 edits
`bypass_rate_alarm.py`), the guard returns a `deny` permissionDecision
explaining the conflict — the Edit never lands.

### Step 4 — Wait for all sub-agents to finish

Each Agent tool call returns when its sub-agent stops. You'll receive N
result blocks. Inspect for failures.

### Step 5 — Declare done (clears the manifest)

```bash
python tools/parallel_wave.py declare-done   # sets wave_done: true
# OR
python tools/parallel_wave.py clear          # removes the manifest file
```

Either trigger makes the guard go silent again. There's also a 1-hour TTL
fallback (`--ttl`) and automatic clearing when the autonomy session ends.

## Anti-patterns the guard catches

| Bad pattern | What the guard does |
|---|---|
| Two sub-agents listed as owning the same file | `emit` records it; the second editor is blocked at write time |
| Main agent edits a sub-agent's owned file mid-wave | Blocked — main is treated as "no agent_id ≠ owner" |
| Sub-agent edits a file outside its declared zone | Blocked if the file is in another zone; silent allow if outside every zone |
| Forgot to clear the manifest after a wave | TTL (default 1h) auto-expires it; otherwise `clear` it manually |

## Identity model (so you know what the guard sees)

- The PreToolUse envelope carries `agent_id` (and `agent_type`) for
  sub-agent calls — verified in Claude Code docs (hooks.md "Common Input
  Fields", "Only in subagents").
- Main-agent Edits arrive with no `agent_id` → treated as "no owner".
- The guard's comparison is `envelope.agent_id == zone.agent_id`. Make
  sure each sub-agent prompt names its agent_id explicitly (e.g.
  "wave-a-1") and the agent uses that name in its work — otherwise the
  guard can't match.

## Emergency bypass (DEV-only, single-shot)

If you genuinely need to bypass the guard for one specific Edit, type
literally in a DEV prompt:

```
bypass-parallel-guard: <reason ≥ 8 chars>
```

`intent_router` writes a single-shot token consumed by the very next
matching Edit. Do not use this as a workaround — re-plan the zones if
conflicts keep occurring.
