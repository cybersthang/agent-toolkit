---
description: Run `hook_health.py` to surface aggregated telemetry from all hook ring buffers — fires, crashes, warns, bypasses — across the last N events.
argument-hint: [window]
---

# /hook-health

Aggregate hook telemetry into single markdown report. Reads:
- `.agent-toolkit/.hook_crash_log.json` (P9 v0.8.0)
- `.agent-toolkit/.hook_fire_log.json` (Phase C v0.9.0)
- `.agent-toolkit/.spec_first_guard_log.json`
- `.agent-toolkit/.implement_notes_gate_log.json`

## Usage

```
/hook-health
/hook-health 100   # Window override (last 100 events per log)
```

## Output

Markdown table per:
- Fires per hook + avg duration ms.
- Crashes per hook (if any).
- spec_first_guard activity (warns / bypasses).
- implement_notes_gate activity.

Health verdict: green / yellow / red based on crash counts + recency.

## When to use

- Periodic DEV health check (weekly).
- After v0.x.x upgrade — confirm hooks firing normally.
- Debugging "why is AGENT slow today" — check fire counts + avg duration.
- After AGENT_TOOLKIT_STRICT=1 enabled in CI — surface any propagated crashes.

## Reference

Tool: `templates/codex/tools/hook_health.py` — Phase C v0.9.0 closure for
Dim 3 Observability (HE evaluation 6.5 → ~8.5).
