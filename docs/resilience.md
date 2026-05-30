# Agent resilience — surviving 529 Overloaded & hangs (v0.24.0)

When an autonomous multi-step run is interrupted — by an `API Error: 529
Overloaded` or by the agent hanging — you don't want to lose progress. This
doc covers the three layers the toolkit gives you, and which one fits how you
run Claude Code.

## TL;DR by how you run Claude Code

| You run Claude via… | What recovers you |
|---|---|
| **VSCode extension chat** | Built-in retry + **resume-brief** on next session + **stall-watcher notify** (semi-auto: you click resume / type "tiếp") |
| **Terminal CLI / headless** | All of the above **+ `agent_supervisor --relaunch`** (full-auto: re-runs `claude -c` up to a cap) |

> The external supervisor cannot wrap the VSCode-extension session (VSCode
> owns that process). For the extension, recovery is semi-auto: the watcher
> *notifies* you, you resume, and the resume-brief + R9 scope manifest let the
> agent continue **without redoing finished work**.

## Layer 1 — tune the built-in 529 retry (do this first)

Claude Code already retries transient API errors (incl. 529) up to 10× with
exponential backoff before surfacing an error. Raise the ceiling for flaky
networks via `~/.claude/settings.json`:

```json
{ "env": { "CLAUDE_CODE_MAX_RETRIES": "20", "API_TIMEOUT_MS": "900000" } }
```

This works in **both** the extension and the CLI. Most 529s never reach you.

## Layer 2 — resume-brief (both extension & CLI)

`session_brief.py` (SessionStart hook) injects a **🔄 RESUME** block when an
autonomous run was interrupted and the R9 scope manifest
(`.agent-toolkit/.scope_manifest.json`) still has pending items. It lists only
the *pending* items — finished tasks are never re-listed (idempotent). When
you reopen the conversation (extension Session History, or a new turn) and type
"tiếp", the agent continues from exactly where it stopped.

> The manifest lives on disk regardless of hooks, so even if `SessionStart`
> does not fire on a particular resume, the agent can still read the manifest.

## Layer 3 — stall-watcher (`tools/agent_supervisor.py`)

A standalone, **read-only** process that watches the active transcript
(`~/.claude/projects/<encoded>/<session>.jsonl`) + autonomy state. When
autonomy is active and the transcript has been idle past `stall_seconds`
(or the `claude` process is gone), it **notifies** you. It never kills or
edits the session — so it is safe and works for the extension too.

```bash
# Read-only watcher (extension or CLI) — just notifies you to resume:
python tools/agent_supervisor.py --project-dir .

# CLI-only full-auto: also re-runs `claude -c -p "<resume brief>"`:
python tools/agent_supervisor.py --project-dir . --relaunch
```

`--relaunch` retries up to `relaunch_cap` (default 10) with exponential
backoff; on exhaustion it notifies you and stops (no infinite token burn).

### Config — `.agent-toolkit/resilience.json`

Copy `templates/agent_toolkit/resilience.example.json`. Keys: `stall_seconds`
(180), `notify_cooldown` (300), `relaunch_cap` (10), `backoff_base` (2),
`notify.channels` (`log`/`toast`/`smtp`/`webhook`; `log` is always on).

### Notify channels & credentials

- **log** (always): writes `.agent-toolkit/.stall_alert.json`.
- **toast**: OS desktop popup (Windows `MessageBox` / macOS `osascript` /
  Linux `notify-send`).
- **smtp** / **webhook**: credentials come from **environment only** —
  put them in the gitignored `.codex/mcp.local.env`, never in
  `resilience.json` or any committed file:
  `SMTP_HOST/PORT/USER/PASSWORD/FROM/TO`, `WEBHOOK_URL` (Slack/Discord).

## Cross-platform

Works on Windows + Linux/Ubuntu (and macOS). Process-liveness uses `psutil`
when installed; without it the watcher degrades to transcript-mtime-only
detection (still functional). Install the optional dep with `pip install
psutil` if you want the process-gone signal.

## v0.26 — multi-transcript mode (sub-agents in a wave)

When a parallel wave is active (`.agent-toolkit/.parallel_wave.json`
present, `wave_done: false`, TTL alive), the same supervisor loop ALSO
watches every sub-agent's `.jsonl` transcript. If any sub-agent goes
idle past `subagent_stall_seconds` (default = `stall_seconds`), the
watcher dispatches an aggregate notify via the same channels, prefixed
`[sub-agent <wave>]` for at-a-glance distinction. **Notify-only** for
sub-agents (Agent tool is model-invoked — no relaunch). See
[docs/parallel.md](parallel.md) for the full sub-agent flow.
