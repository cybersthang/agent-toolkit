---
name: gap-fix-cycle
description: Diagnose-patch-rerun loop for probes that returned REFUTED. Up to N iterations, then escalate to DEV. Used by `/implement` to take the spec from `implementing` to `verified` without DEV intervening between phases. Triggered implicitly by `/implement` chain when a probe verdict is REFUTED, or explicitly via `/gap-fix <probe-id> [--max-iter 3]`.
---

# gap-fix-cycle

## Purpose

Replace the manual "DEV bảo fix đi" loop with a mechanical diagnose-patch-rerun cycle bounded by a max iteration count. Honors all safety hard-stops from ADR-002 (no prod_db_write, no git_push_*, etc.).

## Workflow

```
For each REFUTED probe (or single probe via /gap-fix <id>):
  iter = 0
  while iter < max_iter:
    iter += 1
    1. DIAGNOSE:
       a. Read probe's last falsify.py stderr from .auto_probes_state.json.
       b. Read probe.applies_when.path_globs files in this turn's context.
       c. Pick a diagnose strategy from
          .agent-toolkit/gap_fix/diagnose_strategies/*.py
          based on error fingerprint (AttributeError, AssertionError,
          regex mismatch, etc.).
       d. Strategy emits {file: str, span: (line_start, line_end),
                           reason: str, proposed_patch: dict}.
    2. PATCH:
       a. Apply Edit with proposed_patch.old_string / new_string.
       b. Append entry to .agent-toolkit/decision-log.md:
          "ADR-NNN: gap-fix-cycle iter <iter> on probe <id> —
           changed <file>:<span> because <reason>."
    3. RERUN:
       a. Invoke: python .codex/tools/falsify.py --probe <probe_id>.
       b. Parse exit code → proven / refuted / error.
    4. UPDATE:
       a. Write {status, ts} to .agent-toolkit/.auto_probes_state.json.
       b. Update verify_report.md cell if spec referenced.
    5. If proven → break loop, report success.
    If max_iter reached without proven →
       a. Print iteration log to systemMessage.
       b. Escalate: emit "DEV-action-required" marker.
```

## Config

`.agent-toolkit/gap_fix.json`:

```json
{
  "max_iter": 3,
  "timeout_per_iter_s": 300,
  "diagnose_strategies_dir": "templates/cursor/skills/_common/gap-fix-cycle/diagnose",
  "decision_log_append": true,
  "respect_hard_stops": [
    "prod_db_write",
    "git_push_force",
    "credentials_write",
    "git_push_main_branch"
  ]
}
```

## Diagnose strategy plug-in interface

Each `.py` file in `diagnose_strategies_dir` exports:

```python
def matches(probe: dict, last_stderr: str) -> bool:
    """Return True if this strategy can address the symptom."""

def diagnose(probe: dict, last_stderr: str,
             workspace: Path) -> Optional[Patch]:
    """Return {file, old_string, new_string, rationale} or None
       (no patch proposed = let next strategy try)."""
```

Public: PR new strategies upstream. Seed strategies:
- `python_attribute_error.py` — locate AttributeError on the missing attr; suggest renaming.
- `python_assertion_mismatch.py` — read expected vs actual from AssertionError; patch expected.
- `js_console_error.py` — Playwright console message → infer JS module + line.
- `regex_mismatch.py` — log_assertion regex stderr → propose looser/tighter regex.
- `import_error.py` — ModuleNotFoundError → suggest adding to __init__.py.

## Safety contracts (inherited from ADR-002)

- Patches NEVER touch files in `still_blocked` scopes.
- Patches NEVER strip an invariant_guard `must_keep_regex` pattern.
- Patches are isolated to files listed in probe.applies_when.path_globs.
- After max_iter, AGENT emits a detailed diff but does NOT auto-commit.

## Output

- Inline systemMessage per iteration: `[gap-fix-cycle] iter 2/3: probe <id> still REFUTED — strategy <X> applied, retrying.`
- Final summary: success or escalation marker + full iteration log written to `.agent-toolkit/.gap_fix_log/<probe_id>_<ts>.json`.

## Refuse / clarify when

- Probe is `severity: warn` AND DEV did not opt-in via `/gap-fix` → defer to DEV.
- Probe has no `path_globs` → cannot scope patches; require DEV intervention.
- Diagnose returns no strategy match after iter 1 → escalate immediately (don't burn iterations on dead end).

## What this skill MUST NOT do

- Commit, push, or branch (DEV holds those gates per ADR-002).
- Edit files outside probe.applies_when.path_globs.
- Suppress invariant_guard or evidence_audit hooks.

## Linked

- /run-probes — single-shot mode for DEV.
- gap-status — read-only state inspector.
- /implement — invokes gap-fix-cycle automatically on REFUTED.
