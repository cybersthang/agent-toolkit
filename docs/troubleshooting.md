---
version: 0.21
audience: agent-toolkit users
last_updated: 2026-05-25
---

# Agent-Toolkit Troubleshooting

Common issues encountered and their resolutions. Indexed by symptom. Each
entry: stderr you see → why it fired → concrete fix → optional bypass.

If the stderr line you got is not listed here, search this file for the
hook tag in square brackets (e.g. `[evidence-audit]`,
`[gap-completeness-gate]`) — those map 1:1 to the entries below.

---

## Hook blocks

### 1. Clarification gate blocked: missing markers

**Symptom**
```
[clarification-gate-enforcer] block: response missing required markers
  (UNDERSTANDING/ASSUMPTIONS/QUESTIONS/Searched:)
```
**Cause**: `intent_router` detected a state-changing intent (edit, scaffold,
refactor) and suggested the `clarification-gate` skill. The agent's reply
finalised without the 4 markers the gate requires.

**Fix**: Re-emit the response with **all four** sections, in this order:
```
UNDERSTANDING: <one-line restatement of the ask>
ASSUMPTIONS:   <what you assumed without asking>
QUESTIONS:     <gated questions; later ones collapse if earlier ones answer>
Searched:      Read <path>, Grep "<pattern>", mcp__codebase__search_text "<q>"
```
The `Searched:` line MUST cite real tool calls from this turn — the
`evidence_audit` hook double-checks.

**Bypass once**: prepend the next user prompt with
`skip-clarification: <reason ≥ 8 chars>`. Token TTL 600s, single-use.

---

### 2. Evidence audit blocked: PASS/DONE claim without MCP tool

**Symptom**
```
[evidence-audit] PASS/DONE/VERIFIED claim detected — nhưng turn này KHÔNG có
  tool call MCP nào chạy verification trên real data.
```
**Cause**: response said "verified", "tests pass", "done", "ready" but the
turn made zero `mcp__realdata_test__*` / `mcp__postgres__*` calls. Toolkit
refuses honor-system claims (see `feedback_exhaustive_analysis`).

**Fix**: Actually run a probe before claiming PASS, e.g.
```
mcp__realdata_test__run_module_test   (module test)
mcp__realdata_test__eval_orm_expression
mcp__postgres__query_readonly
```
Then quote the raw output (row count / fingerprint) in your response.

**Bypass options** (single-shot, must appear in the agent response):
- `probe-skip: <probe-id|all> <reason>` — probe genuinely unavailable
- `[assumption]` tag per claim — downgrades from FACT to GUESS
- `evidence-audit: skip` — only for trivially harmless claims (style/format)

---

### 3. Invariant guard blocked Edit (pattern stripped)

**Symptom**
```
[invariant-guard] Edit vi phạm invariant đã thoả thuận.
BLOCKER (deny):
  - INV-12: <description>
      Patterns mất: <regex>
      Lý do invariant: <rationale>
```
**Cause**: the Edit/Write/MultiEdit removed a `must_keep_regex` or
`must_keep_call` pattern from a file in scope, and the invariant is
`severity: blocker`.

**Fix** (pick one):
1. **Keep the pattern** — adjust the diff so the regex still matches the
   post-edit file.
2. **Change the invariant first** — run `/adr-add` to record the new
   decision, then `/inv-add` to weaken/remove the pattern. *Then* re-run
   the Edit.

**Bypass once**: next user prompt includes `bypass-invariant: <INV-id>`
(e.g. `bypass-invariant: INV-12`). Token TTL 300s, consumed on first
matching Edit. Multiple ids comma-separated.

---

### 4. Git guardrails blocked commit/push/add

**Symptom**
```
[git-guardrails] DENY: 'git commit' is not authorised for the agent.
  feedback_no_ai_commit — DEV must explicitly authorise git state changes
  in the current turn.
```
**Cause**: the agent tried `git commit` / `push` / `add` / `reset --hard` /
`--no-verify` / `--force` / `clean -fd` / `branch -D` / `checkout .` /
`restore .`. Per `feedback_no_ai_commit`, only DEV is allowed to run these.

**Fix**: DEV runs the git command directly in their shell. Do not ask the
agent to do it.

**Bypass once** (DEV-only):
```
bypass-git-guard: <reason ≥ 8 chars>
```
in the prompt — this writes `.agent-toolkit/.skip_git_guard_next.json`
(mtime TTL 600s, single-use). Covers exactly ONE git command. Implied
language like "ship it" or "/implement" does NOT trigger bypass.

---

### 5. Gap completeness gate blocked done-claim

**Symptom**
```
[gap-completeness-gate] block: Turn này claim done nhưng còn N gap chưa resolve:
  G1 — <desc>
  G2 — <desc>
```
**Cause**: the agent emitted a numbered gap list (`G1 — …`, `G2 — …`)
earlier in the conversation and then claimed "implement done / all done /
hoàn thành" without resolving them. Drip-feed anti-pattern (see
`feedback_exhaustive_analysis`).

**Fix** — three resolution tiers, all in the agent response:
1. **Fix the gap** → re-emit; the gap auto-clears.
2. `gap-defer: G<N> <reason ≥ 8 chars>` — punt to next sprint, logged.
3. `gap-cant-fix: G<N> <reason>` — escalate to DEV, stderr-surfaced.

**Whole-gate bypass once** (DEV prompt):
`bypass-gap-gate: <reason ≥ 8 chars>`. Skipped automatically when
`.autonomy_active.json` is fresh (auto-chain mid-fix). Stale gaps (>24h)
auto-flip to `status: stale`.

---

### 6. Debug sentry blocked traceback without root cause

**Symptom**
```
[debug-sentry] block: traceback / exception detected in turn output but
  response did not attempt root-cause + fix or tag [assumption].
```
**Cause**: a Stop hook scanned the turn and matched a strong traceback
pattern (`Traceback (most recent call last)`, `psycopg2.errors.…`,
`File "<path>", line N`) — but the response did not invoke the
`<stack>-<version>-debug-troubleshoot` skill nor disclaim.

**Fix**:
1. Open the matching debug skill — root-cause, fix, re-run.
2. Or tag the traceback-related claim with `[assumption]` /
   `[low-confidence]` / `[unverified]` if you genuinely can't fix yet.

**Bypass once**: `bypass-debug-sentry: <reason ≥ 8 chars>` in next prompt.
Token TTL 600s.

**Toggle off entirely**: edit `.agent-toolkit/debug.json` →
`"block_on_match": false` (warn-only) or `"enabled": false`.

---

### 7. Verify lint blocked: Verify Report missing acceptance_evals coverage

**Symptom**
```
[verify-lint] block: missing N evals: AE-1, AE-3, AE-7
```
**Cause**: response contained a "Verify Report" header but the lint script
(`.codex/lint_verify_report.py`) found acceptance_evals declared in the
spec frontmatter that the report did not cite. Exit code 1.

Other exit codes:
- `3` — spec has no `acceptance_evals:` block → lint skipped (allow).
- `4` — classifier spec missing required "Real-Data Proof" section → BLOCK.

**Fix**:
1. Re-emit the Verify Report and cite every AE id from the spec
   frontmatter (per-AE pass/fail line).
2. Or, if AEs are stale, run `/eval-backfill <slug>` to refresh the
   `acceptance_evals:` YAML from prose, then re-emit.

**No single-shot bypass** — lint is the contract. To disable entirely,
delete the `acceptance_evals:` block from the spec (and accept the
verification quality drop).

---

### 8. Post-edit verify gate blocked done-claim without `/verify`

**Symptom**
```
[post-edit-verify-gate] block: Turn touched file in spec <slug> (status:
  implementing) and claimed done — but no /verify run in this turn.
```
**Cause**: an Edit/Write/MultiEdit landed on a file referenced by a spec
at status `implementing` or `gaps-found`, the response claimed completion,
and neither `/verify` nor `run_python_tests` nor `mcp__*` probe ran.

**Fix**: invoke `/verify <slug>` (or the relevant
`mcp__realdata_test__run_module_test`) before claiming done. The probe
output goes into the Verify Report.

**Bypass once**: prepend the agent response with `verify-gate: skip` —
use only for genuinely WIP commits where the loop is intentionally open.

---

## Setup / runtime issues

### 9. `setup.py update` overwrites my custom edits

**Symptom**: after `python ~/agent-toolkit/setup.py update <project>`,
files you locally edited (e.g. `.agent-toolkit/debug.json`, a skill MD)
are reverted. Backup `.bak.<timestamp>` files appear next to them.

**Cause**: `setup.py update` is a template re-sync. Any file under
`.codex/`, `.claude/`, `.cursor/`, `.agent-toolkit/` that mirrors a
template path is overwritten — your edits land in `.bak.<timestamp>`.

**Fix**:
1. Restore: `cp .agent-toolkit/debug.json.bak.<timestamp> .agent-toolkit/debug.json`.
2. Don't edit synced files in-project. Either:
   - Edit the upstream toolkit (`C:/Users/thang.vo/Desktop/NAKIVO/agent-toolkit/templates/...`)
     and re-run `setup.py update`, OR
   - Use override files: most JSON configs (`debug.json`, `tdd.json`,
     `enforce_mode.json`) merge with template defaults — keep only the
     overridden keys in the project copy.
3. Clean up the accumulating `.bak.*`:
   ```bash
   find <project> -name "*.bak.*" -mtime +30 -delete
   ```
   (Track upstream issue A3 — `.bak.*` should land in `.gitignore`.)

---

### 10. MCP server not connecting — check `.codex/mcp.local.env`

**Symptom**: `mcp__postgres__*` / `mcp__realdata_test__*` tools missing
from the available-tools list, or `env_status` returns
`{"status": "no_config"}` / connection refused.

**Cause**: MCP servers read credentials from
`.codex/mcp.local.env` (gitignored, per `feedback_credentials`). If the
file is missing or has wrong keys, the server fails to start and Claude
Code silently drops it from the toolset.

**Fix**:
1. Copy the example:
   ```bash
   cp .codex/mcp.local.env.example .codex/mcp.local.env
   ```
2. Fill in `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`,
   `ODOO_RPC_URL`, `ODOO_RPC_USER`, `ODOO_RPC_PASSWORD` (whichever your
   preset declares).
3. Restart Claude Code (file is read at MCP-server-spawn time).
4. Verify with `mcp__postgres__env_status` — should return
   `{"status": "connected", "database": "..."}`.

**Never** paste real credentials into committed files — that's an
invariant `feedback_credentials` enforces.

---

### 11. Claude Code doesn't see slash command — restart

**Symptom**: typing `/verify` / `/plan` / `/inv-add` shows
"Unknown command" or the command list does not include them.

**Cause**: slash commands are loaded from
`.claude/commands/*.md` at Claude Code **session start only**. If you
just ran `setup.py init` or `setup.py update` while a session is live,
the new commands are on disk but the session's loaded set is stale.

**Fix**:
1. Quit the Claude Code session (Ctrl+C twice).
2. Re-launch from the project root.
3. List commands: `/help` — confirm `/verify`, `/plan`, `/clarify`,
   `/tasks`, `/analyze`, `/implement` are present.
4. If still missing: check `ls .claude/commands/` — should have 15+ `.md`
   files. If empty, re-run `setup.py update --preset <preset> .`.

Same applies for newly added skills (`.claude/skills/*/SKILL.md`) and
new hooks (`.claude/settings.json`).

---

### 12. Hook crashes repeatedly — check `.agent-toolkit/.hook_crash_log.json`

**Symptom**: every turn ends with stderr
```
[hook] crash logged to .agent-toolkit/.hook_crash_log.json
```
or hooks are silently fail-open and you don't get expected DENYs anymore.

**Cause**: a hook hit an unhandled exception. `run_main_safe` wrapper
logged it and (depending on `enforce_mode.json`) either fail-open
(allow) or fail-closed (exit 1).

**Fix**:
1. Inspect the log:
   ```bash
   cat .agent-toolkit/.hook_crash_log.json | python -m json.tool | tail -50
   ```
   Each entry has `hook`, `ts`, `traceback`, `envelope_keys`.
2. Run `/hook-health` (skill) — surfaces aggregated counts across hooks.
3. Common root causes:
   - Stale JSON state file (`.open_gaps.json`, `.bypass_next_edit.json`)
     — delete to reset.
   - Python venv mismatch — confirm `.claude/settings.json` `python_bin`
     points at a venv with required deps.
   - Schema-version drift after toolkit update (see case 14).
4. If a single hook is the offender, disable it via
   `.agent-toolkit/enforce_mode.json`:
   ```json
   {"per_hook": {"<hook_name>": "off"}}
   ```

---

### 13. Bypass token doesn't work — TTL 600s, single-shot

**Symptom**: typed `skip-clarification: refactor pure rename` /
`bypass-invariant: INV-12` / `bypass-git-guard: ship CI fix` in a prompt
but the next turn still gets blocked.

**Cause** (in order of likelihood):
1. **TTL expired** — most tokens are 600s (skip-clarification,
   skip-debug-sentry, skip-git-guard); `bypass-invariant` is 300s.
   Tokens are written by `intent_router` (UserPromptSubmit) and consumed
   on the next matching Stop / PreToolUse fire.
2. **Already consumed** — bypass is single-shot. One Edit / one git
   command / one Stop only. Re-type for the next operation.
3. **Reason too short** — `<reason>` must be ≥ 8 non-whitespace chars
   for audit-trail compatibility. `bypass-invariant: x` is rejected;
   `bypass-invariant: INV-12 weakening rule for refactor` works.
4. **Wrong gate** — `skip-clarification` does NOT cover
   `gap-completeness-gate`. Each gate has its own token (see entries
   1, 3, 4, 5, 6 above).

**Fix**: re-type the bypass in the *immediately preceding* user prompt
with ≥ 8 char reason; the agent's next response is the single-shot
window. Inspect `.agent-toolkit/.skip_*.json` mtime to confirm the
token was written.

---

### 14. Test suite fails after toolkit update — schema_version migration

**Symptom**: after `setup.py update`, `pytest tests/` shows failures
like `KeyError: 'schema_version'` or
`AssertionError: expected schema_version >= 3, got 1`.

**Cause**: state files in `.agent-toolkit/` (e.g. `.open_gaps.json`,
`invariants.json`, autonomy state) have a `schema_version` key. New
toolkit version bumped the schema; old project state still on v(N-1).

**Fix**:
1. Inspect what changed: `cat .agent-toolkit/CHANGELOG.md` (or the
   toolkit-root `CHANGELOG.md`) for the version you just installed —
   schema bumps are called out under "Breaking".
2. Most state files are safe to delete + regenerate:
   ```bash
   rm .agent-toolkit/.open_gaps.json
   rm .agent-toolkit/.bypass_next_edit.json
   rm .agent-toolkit/.skip_*.json
   ```
   These are runtime caches, not durable rules.
3. **Do NOT delete** `invariants.json`, `decision-log.md`,
   `constitution.md`, `acceptance-probes.json`, or `specs/` — those are
   your project's durable state. If their schema bumped, the install
   ships a migration script under `lib/migrations/` — run it explicitly
   per CHANGELOG instructions.
4. Re-run tests: `python -m pytest tests/ --no-cov -q`.

---

### 15. Slow Stop chain — multiple hooks adding latency

**Symptom**: turns feel laggy at "Stop" (10-20s before the agent's
response is committed). `hook-health` shows total Stop-chain time
> 100s cumulative across recent turns.

**Cause**: Stop chain runs 11 hooks sequentially (v0.19 → v0.21):
`clarification_gate_enforcer`, `gap_completeness_gate`, `verify_lint`,
`evidence_audit`, `post_edit_verify_gate`, `debug_sentry`,
`implement_notes_gate`, `verify_nudge`, etc. Each reads the JSONL
transcript + state files. On large transcripts (> 5 MB) the I/O
dominates. Tracked as B3 in audit findings — full rewrite deferred to
v0.22+.

**Fix** (interim):
1. **Disable non-essential hooks** for slow workspaces — edit
   `.agent-toolkit/enforce_mode.json`:
   ```json
   {
     "per_hook": {
       "verify_nudge": "off",
       "complexity_sentinel": "off",
       "spec_drift_advisory": "off"
     }
   }
   ```
   Keep BLOCK-tier hooks (`evidence_audit`, `invariant_guard`,
   `git_guardrails`) on — they're the safety contract.
2. **Truncate transcript** between long sessions — start a fresh
   session every ~50 turns; old turns aren't re-scanned but file size
   still affects JSONL parse.
3. **Profile**: run `/hook-health` → check `total_ms` per hook.
   Anything > 5s/fire is investigation-worthy — file a bug at
   `gitlab.com/nosafarm/agent-toolkit/issues`.
4. Universal kill-switch (nuclear): `export AGENT_TOOLKIT_DISABLE=1` —
   every hook short-circuits to allow. Use only for emergency unblocking.

---

## Where to look next

| You're seeing | Read |
|---|---|
| Unfamiliar hook tag in stderr | `templates/claude/hooks/<tag>.py` source — top docstring explains intent + bypass |
| Bypass token regex | `templates/claude/hooks/_patterns.py` |
| Hook ordering in Stop chain | `templates/claude/settings.json` |
| Which invariants are active | `/inv-list` slash command |
| Which decisions are durable | `.agent-toolkit/decision-log.md` |
| Aggregated telemetry | `/hook-health` skill |
| Crash details | `.agent-toolkit/.hook_crash_log.json` |
| Open gaps state | `.agent-toolkit/.open_gaps.json` |

If a symptom isn't covered here, open an issue with the stderr block tag
(e.g. `[evidence-audit] block: ...`), the hook name, and the response
excerpt that triggered it.
