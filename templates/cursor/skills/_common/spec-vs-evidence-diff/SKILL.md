---
name: spec-vs-evidence-diff
description: Advisory report comparing each probe's recipe text vs its executable script — surfaces "recipe drift" (script doesn't implement the recipe verbatim). Pairs with `spec_drift_advisory.py` Stop hook. Triggered explicitly via `/spec-drift [<probe-id>]` or implicitly by the Stop hook each turn (advisory, never blocks).
---

# spec-vs-evidence-diff

## Purpose

Probe recipes (`falsification.description`) and probe scripts (Playwright/Python at `runner.spec_file`) tend to drift over time:
- DEV updates the recipe but forgets to regen the script.
- AGENT generates the script via `recipe-to-probe-script` then DEV edits it but doesn't update the recipe.

This skill surfaces the drift mechanically + advisory (NEVER blocks the workflow).

## Mechanism

Three sensitivity levels (per-probe `recipe_drift_tolerance` field):

| Level | Token universe checked |
|---|---|
| `loose`  | Critical keywords only (freeze targets, p99 thresholds, RPC counts) |
| `medium` (default) | Load-bearing nouns/verbs (longpoll, shadow, blockUI, rpc, indexeddb, ms thresholds) |
| `strict` | Every meaningful token in description vs script |

For each probe with a `spec_file`:
1. Tokenize description + script (lowercase, ≥ 2 chars, alphanumeric).
2. Subtract stop-words from both.
3. Compute `desc_tokens - script_tokens` filtered by sensitivity level.
4. Emit "probe X mentions Y but script does not".

## Config: `.agent-toolkit/recipe_drift.json`

```json
{
  "enabled": true,
  "ignore_words": ["..."],
  "load_bearing_keywords": {
    "loose": ["postgres", "odoo", "p99", "1000", ...],
    "medium": ["...same plus rpc, shadow, blockui, indexeddb..."],
    "strict": []
  }
}
```

Public extension: PR new keywords for new stacks (Django: `django`, `pytest`; Rails: `rspec`, `puma`).

## Output

Inline systemMessage (advisory; never blocks):

```
[spec-drift] recipe vs script divergences detected (advisory):
  - probe `hotpot-us5-resilient` description mentions postgres
    but the script (.agent-toolkit/scripts/probes/us5.py) does not.
    Update the script or relax the recipe.
```

## What this skill MUST NOT do

- Modify probe entries or scripts.
- Block Stop.
- Surface false positives for synonym pairs (handled by `ignore_words` config).

## Linked

- `recipe-to-probe-script` — generates the script that this skill checks.
- `/probe-add` — DEV-driven probe + recipe entry; common drift source.
- `gap-fix-cycle` — when drift causes refutation, gap-fix-cycle suggests recipe-side OR script-side fix.
