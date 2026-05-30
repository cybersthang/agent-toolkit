# Available presets

```bash
python setup.py list-presets
```

**10 presets** ship out of the box (9 Odoo versions + 1 generic fallback):

| Preset | Stack | Python | Frontend | Rules / Memory |
|--------|-------|--------|----------|----------------|
| `odoo-12` | Odoo 12, `@api.multi` era | 3.8 | QWeb + jQuery | _common + odoo-12 |
| `odoo-13` | Odoo 13, `@api.multi` era | 3.6+ | QWeb + jQuery | _common + odoo-12 (legacy shared) |
| `odoo-14` | Odoo 14, `@api.multi` era | 3.7+ | QWeb + jQuery | _common + odoo-12 (legacy shared) |
| `odoo-15` | Odoo 15, transitional | 3.8+ | QWeb + OWL 1.x | _common + odoo-12 (legacy shared) |
| `odoo-16` | Odoo 16, modern ORM | 3.10+ | OWL 2.x | _common + odoo-17 (modern shared) |
| `odoo-17` | Odoo 17, modern ORM, `@api.model_create_multi` | 3.10+ | OWL framework | _common + odoo-17 |
| `odoo-18` | Odoo 18, modern ORM | 3.10+ | OWL framework | _common + odoo-17 (modern shared) |
| `odoo-19` | Odoo 19, modern ORM | 3.11+ | OWL framework | _common + odoo-17 (modern shared) |
| `odoo-20` | Odoo 20 (expected GA late 2026) | 3.11+ | OWL framework | _common + odoo-17 (modern shared) |
| `generic` | Plain Python — fallback for stack-agnostic experiments only. **Not** the recommended preset for Odoo work. | — | — | _common |

Default `addon_roots` for Odoo presets: `addons` / `custom_addons` /
`enterprise`. MCP servers: `codebase` + `postgres` + `realdata_test`.
Every Odoo version 12-19 ships its **own dedicated** rule pack
(`templates/cursor/rules/odoo-<v>/`), memory pack
(`templates/memory/odoo-<v>/`), and canonical-decisions file
(`templates/codex/canonical_decisions.odoo-<v>.json`) — no sharing.
Only **odoo-20** is an honest pre-GA **stub-extends-v19** (v20 is not
yet released; its rules are extrapolated from v19 and every v20-specific
claim is unconfirmed until verified against installed source).

> **Project-specific overlays**: real projects almost always have extra
> addon roots, a custom `odoo-bin` path, internal JIRA endpoints,
> Enterprise-only modules, etc. Keep those in a **private preset** that
> `extends` one of the public presets — see
> [`PORTING.md`](../templates/agent_toolkit/PORTING.md)
> for the recipe. Don't fork the toolkit just to bake in your defaults.

The toolkit's *design* is stack-agnostic — you can drop a new preset
JSON into `presets/` (e.g. for Django, Rails) and matching
`templates/cursor/rules/<name>/` + `templates/memory/<name>/`. **In
practice the shipped presets target Odoo**; the rules, skills,
canonical decisions, and MCP servers are tuned for Odoo conventions.

## Shipped skills

**Spec Kit workflow skills** (`_common`, every preset):

| Skill | Phase | What it does |
|-------|-------|--------------|
| `plan-feature` | 1 — SPECIFY | Turn a feature request into an 8-section spec at `.agent-toolkit/specs/<branch>/<slug>.md` + emit `acceptance_evals` skeleton. |
| `clarify` | 2 — CLARIFY | One Q per turn until every Open Question closes; refine `acceptance_evals` (set grader/layer/expected, smoke-test); auto-fire `/tasks`. |
| `tasks-breakdown` | 3 — TASKS | Emit `tasks.md` next to spec — Touches / Acceptance / Verification / Risk per task. STOPs for DEV review. |
| `analyze-artifacts` | 3.5 — ANALYZE | 7 cross-artifact checks (story / eval coverage + invariant + constitution + path realism + verification concreteness) before implement. |
| `verify-feature` | 5 — VERIFY | Real-data probes via realdata_test/postgres/Playwright MCP in parallel; emit Verify Report (PASS/GAP/BLOCKER per User Story). |

**Guardrails** (`_common`, every preset):

| Skill | What it does |
|-------|--------------|
| `clarification-gate` | Pre-flight 3-block (UNDERSTANDING / ASSUMPTIONS / QUESTIONS) before any action verb. |
| `code-review` | Exhaustive single-pass review — surfaces ALL Blocker + Medium + Low findings in one session, with a reproducible PROOF line. |
| `doubt-driven-review` | CLAIM → EXTRACT → DOUBT → RECONCILE overlay before reporting non-trivial findings. |
| `claim-falsification` | 15-recipe catalog for perturb-test (BLOCK/ASYNC, caching, idempotency, atomicity, …). |
| `classifier-output-audit` | Long-tail audit for classification features (sample K rows, re-derive expected tag, find mismatch groups). |
| `karpathy-guidelines` | Operating-principle skill (think before coding, simplicity, surgical changes, MCP-before-files). |

**Odoo skills** (auto-included by every Odoo preset — **14 skills**, all **version-aware**):

Each skill's Step 0 reads `__manifest__.py` from the target module, then
loads the matching `references/odoo-<N>-*.md`. One skill folder covers
Odoo 12 → 20 (and future 21+ — just add a reference file).

*Core workflow* (Spec Kit + day-to-day):

| Skill | What it does |
|-------|--------------|
| `odoo-code-review` | Exhaustive review. Cascade: 12 standalone, 17→18→19→20. |
| `odoo-code-patterns` | Canonical patterns (model / wizard / view / OWL). Version-specific `references/odoo-<N>-patterns.md`. |
| `odoo-codebase-discovery` | MCP discovery (`discover_modules`, `read_manifest`, …). Version-agnostic. |
| `odoo-debug-troubleshoot` | Quick-fix tables. Version-specific `references/odoo-<N>-pitfalls.md`. |
| `odoo-tdd` | Red-Green-Refactor + perturb-test routing. Version-specific `references/odoo-<N>-tdd-pitfalls.md`. |

*Multi-edition* (v0.22 — Community / Enterprise / multi-company):

| Skill | What it does |
|-------|--------------|
| `odoo-community-patterns` | Community-edition-only conventions; flag Enterprise-only modules/fields. Version-aware. |
| `odoo-enterprise-patterns` | Enterprise-only conventions (studio, marketing automation, accounting full). Version-aware. |
| `odoo-multi-company` | Multi-company / multi-currency record rules + `company_dependent` fields. Version-aware. |

*Frontend* (OWL):

| Skill | What it does |
|-------|--------------|
| `odoo-owl-components` | OWL component patterns (12 jQuery fallback, 15+ OWL 1.x, 17+ OWL framework). Version-specific. |

*Performance*:

| Skill | What it does |
|-------|--------------|
| `odoo-performance` | N+1, slow computed fields, prefetch, `read_group` tuning. 10 cross-version recipes (12 / 17 / 18 references). |

*Operations*:

| Skill | What it does |
|-------|--------------|
| `odoo-jira-workflow` | JIRA MCP tools. Version-agnostic. |
| `odoo-module-scaffold` | New module scaffold. Version-specific `references/odoo-<N>-scaffold.md`. |

*Discovery*:

| Skill | What it does |
|-------|--------------|
| `odoo-data-verification` | Real-DB ORM probes via `realdata_test` MCP. Version-agnostic. |
| `odoo-deterministic-answers` | `canonical_decisions.json` registry workflow. Version-agnostic. |

**Adding support for a new Odoo major** (e.g. 21): drop 5 reference
files (one per version-specific skill), optionally add `presets/odoo-21.json`
extending `odoo-17`. No skill body edits, no preset edits in shipped skills.
Full recipe: see [ADD-A-VERSION.md](ADD-A-VERSION.md).
