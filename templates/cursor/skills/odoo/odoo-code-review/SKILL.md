---
name: odoo-code-review
description: Exhaustive code review for Odoo modules at ANY major version (12, 17, 18, 19, 20, future). Step 0 auto-detects the addon's Odoo version from __manifest__.py, then loads the matching reference (references/odoo-<N>-rules.md). 17→18→19→20 inherit each other (cascading); 12 is standalone. Open whenever the user asks "review", "audit", "phân tích sâu", "tìm bug", "kiểm tra code", or "còn gì cần fix?" against Odoo code. Module-agnostic; works for mixed-version monorepos.
---

# Odoo — Code Review (Unified, Version-Aware)

Read `_common/code-review/SKILL.md` first — it owns the cross-stack
workflow, severity rubric, PROOF contract, lock-file precedence,
rationalizations, red flags, change sizing, and reporting format. This
file adds the Odoo layer: version detection, shared Odoo dimensions, tool
routing, and pointers to version-specific deltas.

## 0. Version detection (MANDATORY first step)

Before applying ANY Odoo-version-specific rule, identify the major version
of every module in scope. Wrong version → wrong rules → bogus findings.

### Detection order (stop at the first signal that works)

1. **`__manifest__.py` `version` field** — canonical.
   - `'12.0.1.0.0'` → major **12**.
   - `'17.0.1.0.0'` → major **17**.
   - Pattern: `^(\d+)\.0\.`.
   - MCP call: `codebase.read_manifest({module_path})` (Odoo-17 setups) or
     `codebase.read_manifest({module_path})`.
2. **Fallback signals** when manifest is missing or unparseable. Signals
   are listed from "narrowest version" to "broadest":
   - `from odoo.api import multi` import or `@api.multi` decorator → ≤13 (12 expected in our scope).
   - View uses `attrs="{...}"` / `states="..."` → ≤13 (deprecated in 14, removed in 17+).
   - `web.AbstractWebClient` import / `var Widget = require('web.Widget')` → 12 / 13.
   - `@api.model_create_multi` decorator → ≥14, recordset-default era.
   - `invisible="<py expr>"` directly on `<field>` → ≥17.
   - `/** @odoo-module **/` header at top of `static/src/*.js` → ≥15 (OWL era).
   - `search(domain=...)` keyword instead of `search(args=...)` → ≥18 (renamed in 18).
   - Field declares `aggregator='sum'` (not `group_operator='sum'`) → ≥18.
   - Use of `SQL` wrapper from `odoo.tools` → ≥18.
   - Use of `check_access(operation)` (the unified call) → ≥18.
   - `name_get()` model override → ≤17 (deprecated in 16.4, still works in 18 but flagged).
   - `_compute_display_name()` method on a model → ≥16.4 (canonical in 18+).
   - `<list>` tag in view XML (instead of `<tree>`) → ≥18 preference, both legal.
   - `@http.route(type='jsonrpc')` → ≥19 (renamed from `type='json'`).
   - `@http.route(type='json2')` → ≥19 (new JSON family).
   - `from odoo import Domain` or use of `any!` operator → ≥19.
   - Model declares `_constraints = [...]` / `_indexes = [...]` as attributes → ≥19 (declarative form).
   - `__manifest__.py` `'version': '<N>.0.x.y.z'` — the most authoritative signal; if you can read the manifest, use this directly and skip the rest.
3. **Cross-check** when signals disagree:
   - Manifest says 17 but file uses `aggregator=`/`search(domain=)` → likely upgraded, manifest forgotten. Flag MEDIUM ("manifest version mismatch with code patterns; treat as detected major").
   - Manifest says 12 but file uses `@api.model_create_multi` / OWL — same MEDIUM, but heavier (12-vs-17 gap is large).
4. **Ask the user** only if all signals are inconclusive.

### Routing table

The 17 / 18 / 19 / 20 references cascade — each newer file inherits the
older one and overrides only the deltas. 12 is standalone.

| Detected major | Load reference (rule chain, newest first) | Notes |
|----------------|--------------------------------------------|-------|
| 12             | `references/odoo-12-rules.md` (standalone) | `@api.multi`, `attrs/states`, jQuery+QWeb, single-record `create(vals)` |
| 13 / 14 / 15   | Treat as legacy transitional. Apply 12-rules where matches, ask user before applying 17 rules. Flag MEDIUM. | This skill targets 12, 17, 18, 19, 20; intermediate versions are uncommon in our scope. |
| 16             | Apply `odoo-17-rules.md` + flag LOW ("16 is transitional — some 17 conventions backported") | Treat as 17 with caveat. |
| 17             | `references/odoo-17-rules.md` | recordset-default, `@api.model_create_multi`, removed `attrs/states`, OWL |
| 18             | `references/odoo-18-rules.md` ← `odoo-17-rules.md` (cascade) | `args`→`domain`, `aggregator` rename, `name_get` deprecated, `SQL` wrapper, `check_access`, removed `inselect`/`_mapped_cache`/`_sequence`, `<list>` preferred |
| 19             | `references/odoo-19-rules.md` ← 18 ← 17 (cascade) | `type='jsonrpc'` controller rename, `Domain` API + `any!` operator, declarative `_constraints` / `_indexes`, Python 3.12 recommended, AI server actions |
| 20             | `references/odoo-20-rules.md` ← 19 ← 18 ← 17 (cascade) | **Pre-GA stub** (May 2026). Apply 19 rules + flag 20-specific roadmap items as MEDIUM until GA changelog ships. |
| 21+ (future)   | Apply 20 stub + flag LOW ("version newer than skill — verify each rule still applies") | Update this skill when 21 ships. |
| Mixed monorepo | Detect **per module**; load each module's matching ref chain; label every finding `(v<N>)` | A finding can be BLOCKER in one version and N/A in another (e.g. `attrs="..."` is correct in 12, BLOCKER on upgrade to 17+). |

If you skip Step 0 (assume version), the review is methodologically broken —
restart it.

## 1. Methodology (same for every version)

Workflow, lock-file precedence, severity rubric, PROOF contract, common
rationalizations, red flags, change sizing, dead code, dependency
discipline — all live in `_common/code-review/SKILL.md`. Do not duplicate.

## 2. Shared Odoo dimensions (apply to ALL versions, before loading the version reference)

These don't change between 12 and 17 (or 18+):

### A. ORM safety
- `ensure_one()` whenever a method assumes a single record.
- Parameterized SQL only — never `%-format` / f-string concatenation of user input.
- ORM domain leaves built from typed values, not stringly user input.
- `sudo()` documented with a one-line "why bypass record rules" comment.
- ORM preferred over raw SQL; when raw SQL writes are unavoidable, invalidate or refresh affected caches.

### B. Performance (loops + queries)
- No `search()` / `browse(id)` inside a Python `for` loop.
- `search_count(domain)` over `len(search(domain))`.
- `read_group(..., lazy=False)` for aggregations.
- Batch `write()` / `unlink()` once on a recordset, not per-record.
- `@api.depends(...)` complete on every computed field.
- `store=True` only when the field is searched / grouped / sorted at scale.
- Prefetch-friendly compute (the prefetch is automatic when `@api.depends` is correct).

### C. Manifest hygiene
- `data` order: `security/` → `data/` → `views/` → menus. Files load top-to-bottom; referenced XML IDs must exist by their line.
- `depends` lists exactly what the module imports / inherits.
- `installable: True`; `application` only when the module is a top-level app.
- `version` follows the project's pattern for this Odoo major (`12.0.x.y.z` or `17.0.x.y.z`).

### D. Security / multi-company
- Every new `models.Model` (not `TransientModel` / `AbstractModel`) has at least one row in `ir.model.access.csv`.
- Multi-company models have `ir.rule` aligned with parent `_inherit` chain.
- `_check_company` invoked before write on multi-company linked records.
- Errors: `UserError` for business rules, `ValidationError` for invalid data.
- Logging: `_logger`, never `print`.
- See `_common/code-review/references/security-checklist.md` for the full list.

### E. Monkey-patches / install-uninstall symmetry
- Registry patches (`setattr(BaseModel, …)`) have a teardown path that restores the original.
- Cron records use `noupdate="0"` on first install, `noupdate="1"` afterward.
- Patches paired in `_register_hook` / uninstall hook so ghost behaviour doesn't survive a removal.

### F. XML / views (syntax differs per version — see references)
- Inheritance edits use `<xpath expr="..." position="...">`.
- XML IDs stable across releases; renaming = LOW (migration step required).
- Field referenced in a view exists on the model (`search_xml_ids` + `find_inheritance_chain` to confirm).

### G. Persisted JSON / data schema
- Producer-consumer field consistency — every key written by Python has a reader in views / JS / SQL.
- `json.dumps(payload, ensure_ascii=False)` if the payload may contain non-ASCII (Vietnamese function names, partner names).
- gzip + base64 wrapped JSON: SQL paths must peek through (`additional_info::json -> 'key'` returns NULL on wrapped rows). Either decompress in a view, or add dedicated promoted columns.
- Decompression: explicit max-output-bytes cap before `gzip.decompress` (else decompression bomb).

### H. Concurrency / workers
- Daemon thread `while True:` body wrapped in outer try/except so a transient raise doesn't kill the worker.
- Queues bounded (`Queue(maxsize=...)` / `deque(maxlen=...)`).
- Watchdog dicts (`_entries`, etc.) have a prune path; finished entries popped, not just skipped.
- Thread-local state cleaned up in a `finally` block — including the exception path.

### I. Tests
- New branch / fix has a regression test.
- Tests assert behavior, not implementation details.
- Fixtures cover edge cases (empty, unicode, huge, concurrent).
- Round-trip equality where applicable: `load(dump(x)) == x`.
- `list_test_targets({module_path})` to confirm test entry points exist.

## 3. Version-specific deltas — load the matching reference

After Step 0 detection, load the matching file. The 17 / 18 / 19 / 20
chain is cascading: load the detected version's file PLUS every older file
in the chain back to 17. 12 is standalone (load only `odoo-12-rules.md`).

| Detected major | Files to load (in order) |
|----------------|--------------------------|
| 12             | `odoo-12-rules.md` |
| 17             | `odoo-17-rules.md` |
| 18             | `odoo-17-rules.md` → `odoo-18-rules.md` |
| 19             | `odoo-17-rules.md` → `odoo-18-rules.md` → `odoo-19-rules.md` |
| 20 (pre-GA)    | `odoo-17-rules.md` → `odoo-18-rules.md` → `odoo-19-rules.md` → `odoo-20-rules.md` |

What each file covers:

- **`odoo-12-rules.md`** — `@api.multi` required, `attrs/states` correct in 12, jQuery+QWeb, single-record `create(vals)`, NAKIVO addon roots, Odoo-12 severity calibration.
- **`odoo-17-rules.md`** — `@api.multi` removed, recordset by default, `@api.model_create_multi` mandatory, `attrs/states` removed (use `invisible="<expr>"`), OWL, no jQuery.
- **`odoo-18-rules.md`** (delta on 17) — `args`→`domain` keyword rename, `group_operator`→`aggregator`, `name_get()` deprecated (use `_compute_display_name()`), `SQL` wrapper, unified `check_access()`, removed `inselect`/`_mapped_cache`/`_sequence`/`limit-on-x2many`, `<list>` preferred over `<tree>`, manifest `'assets'` key.
- **`odoo-19-rules.md`** (delta on 18) — controller `type='json'` → `type='jsonrpc'` (and new `type='json2'`), `odoo.Domain` API + `any!` operator, declarative `_constraints` / `_indexes` as model attributes, Python 3.12 recommended, AI-powered server actions.
- **`odoo-20-rules.md`** (delta on 19, **pre-GA**) — provisional stub based on April-2026 roadmap. Themes: AI-embedded actions, read-replica consistency caveats, reconciliation auto-adjustments, rebuilt mobile UI. Real changelog pending GA (~October 2026).

If detection returned 13–16 / 21+, see the routing table in Step 0.

## 4. Tool routing

MCP server name is `codebase` (registered key in `.cursor/mcp.json` / `.mcp.json`). Tool names below are identical across setups.

| Need                              | Tool                                              |
|-----------------------------------|---------------------------------------------------|
| Addon roots in scope              | `workspace_status`, `discover_modules({root_hint})` |
| **Detect Odoo version (Step 0)**  | `read_manifest({module_path})` → `version` field  |
| Model + extensions                | `find_inheritance_chain({model})`                 |
| Tests coverage                    | `list_test_targets({module_path})`                |
| Cross-check XML IDs               | `search_xml_ids`                                  |
| Static text search (with cite)    | `search_text({pattern, root_hint})`               |
| Live-verify a Medium against DB   | `eval_orm_expression`, `consistency_check_eval` (realdata_test MCP) |
| Raw SQL (postgres MCP)            | `run_select`                                      |
| Canonical decision lookup         | `lookup_canonical_decision({topic})`              |
| JIRA ticket context (if available)| `jira_production.get_issue`, `jira_preproduction.get_issue` |

## 5. Reporting — per-finding contract additions

Beyond the `_common/code-review` contract, every Odoo finding includes:

```
- Module: <addon-root>/<module-name>
- Detected Odoo version: <e.g. "12.0.1.0.0 → major 12" or "17.0.1.0.0 → major 17">
- Version-specific touchpoint: <e.g. "uses removed `attrs=` in 17", "missing @api.model_create_multi in 17", "extra `@api.multi` decorator — correct in 12">
- Applies to: (v12) | (v17) | (v12 & v17) | (v12 only — N/A in v17)
```

Lock file convention: `.codex/audit_findings_<module>_locked.md`. Header
includes the methodology lock paragraph from `_common/code-review` so the
count cannot drift silently across sessions.

## 6. Final self-check (run BEFORE sending the report)

Beyond the four from `_common/code-review` Step 9, verify:

5. **Step 0 actually ran**: I read every in-scope module's `__manifest__.py` `version` via `read_manifest`, not assumed.
6. **Per-finding version label**: every finding is tagged with the major(s) it applies to.
7. **Right reference loaded**: I opened `references/odoo-12-rules.md` for v12 findings, `references/odoo-17-rules.md` for v17, and `_common/code-review/references/{security,performance}-checklist.md` for the relevant dimensions.
8. **Mixed monorepo handled**: if scope has modules at different majors, each gets the correct ruleset — no cross-contamination.

## 7. Anti-patterns specific to a version-aware review

- Assuming version from path / filename / module name without reading the manifest.
- Applying Odoo-17 rules to an Odoo-12 module ("missing `@api.model_create_multi`" against a 12 module is a false-positive — 12 doesn't require it).
- Flagging `@api.multi` / `attrs="..."` as bugs in 12 (they are required / correct).
- Flagging absence of `@api.multi` in 17 as a bug (it is removed).
- Skipping Step 0 because "this looks like an Odoo 12 codebase" — looks deceive across mixed monorepos.

## Sibling skills

- `_common/code-review` — methodology, severity rubric, PROOF, rationalizations, red flags.
- `_common/code-review/references/security-checklist.md` — security probes (cross-version).
- `_common/code-review/references/performance-checklist.md` — performance probes (cross-version).
- `references/odoo-12-rules.md` — Odoo-12-specific deltas (standalone).
- `references/odoo-17-rules.md` — Odoo-17-specific deltas (base of 17→20 chain).
- `references/odoo-18-rules.md` — Odoo-18 deltas on 17 (`args→domain`, `aggregator`, `SQL` wrapper, `check_access`).
- `references/odoo-19-rules.md` — Odoo-19 deltas on 18 (`type='jsonrpc'`, `Domain` API, declarative constraints).
- `references/odoo-20-rules.md` — Odoo-20 pre-GA stub (apply 19 + flag roadmap items).
- `<version>-code-patterns`, `<version>-codebase-discovery`, `<version>-data-verification`, `<version>-module-scaffold` — pattern / discovery / verify / scaffold skills (still per-version, not unified here).
