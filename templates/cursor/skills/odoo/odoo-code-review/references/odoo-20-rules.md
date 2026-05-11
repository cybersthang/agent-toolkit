# Odoo 20 — Code Review Reference (Provisional / Pre-GA Stub)

> **Status**: Odoo 20 is **not yet GA at the time this file was written
> (May 2026)**. Official roadmap was presented in **April 2026** by Odoo
> Product Management; general availability is expected after **Odoo
> Experience 2026 in Brussels (24–26 September 2026)**.
>
> **Until 20 GA**: apply `odoo-19-rules.md` as the base and flag any 20-only
> deviation as MEDIUM ("targeting pre-release Odoo 20 — verify rule when GA
> ships"). Update this file as soon as the 20.0 ORM changelog is published
> at `https://www.odoo.com/documentation/20.0/developer/reference/backend/orm/changelog.html`.

Load this file when Step 0 of `odoo-code-review/SKILL.md` detects major
version **20** (likely from a pre-release `__manifest__.py` `version: '20.0.x'`).
Combine with `odoo-19-rules.md` (which itself inherits `odoo-18-rules.md`),
the shared dimensions in the parent SKILL.md, and the cross-version
checklists under `_common/code-review/references/`.

## A. Inherits all 19 rules (and 19 inherits 18)

Treat every Odoo-19 rule as applying to 20 unless explicitly overridden
below. The 19 file in turn inherits the 18 file. Effective rule chain:
**12** → standalone | **17/18/19/20** → cascading.

## B. Confirmed-by-roadmap themes (verify per-finding before flagging)

Based on Odoo's April-2026 roadmap presentation, these areas are evolving
in 20. **None of these are ORM API breakages confirmed by a changelog yet** —
flag findings carefully and ask the user / read the actual 20 changelog when
GA ships.

### 1. AI-embedded server actions (continuation of 19's AI features)

- AI Server Actions expanded across Accounting, Website, Helpdesk, record CRUD.
- **Review concern**: any addon that calls `ir.actions.server` with AI steps must:
  - Audit-log the AI's input prompt + output (compliance / reproducibility).
  - Treat external user input as untrusted in the prompt (prompt injection).
  - Have a deterministic fallback when the LLM is unavailable.
- **Severity**: MEDIUM for missing audit trail on AI-driven mutations of financial / customer-PII data. BLOCKER if AI step silently swallows errors and leaves a half-completed transaction.

### 2. Read-replica database support

- Odoo 20 is expected to support read-replica databases for scaling reads.
- **Review concern**: any code that assumes "read returns my just-written value" (read-after-write consistency) may break when the replica lags. Look for:
  - `create()` → immediately `search()` with the new id (race vs replica lag).
  - Long-running cron jobs that read after write expecting fresh data.
- **Severity**: MEDIUM where a workflow assumes strong read-after-write consistency. LOW for read-only reporting queries (replica lag is fine).

### 3. Reconciliation auto-adjustments (Accounting)

- Automatic FX-difference and revenue-deferral entries triggered by reconciliation.
- **Review concern**: any custom addon overriding `_reconcile_lines` / `js_assign_outstanding_line` must respect the new auto-adjustment flow; if it suppresses adjustment entries, that's a BLOCKER on financial correctness.

### 4. Mobile UI (rebuilt)

- Purpose-built mobile UI with visible field labels and touch optimizations.
- **Review concern**: legacy mobile-specific JS / CSS workarounds in the addon may conflict with the new mobile shell. Flag LOW for any `@media (max-width:)` overrides that the new mobile UI handles natively.

### 5. POS / Retail improvements

- Automatic combo application, kiosk improvements, reduced RAM usage, snooze product availability.
- **Review concern**: POS addons should use the new combo API instead of manual combo-line construction; flag MEDIUM for manual workarounds.

### 6. Website Builder AI

- Natural-language content/image/page editing.
- **Review concern**: any addon that exposes the website builder to user-content must validate inputs before passing to the AI step.

## C. Provisional severity calibration

Use these as **guidelines only** until the 20 changelog confirms behavior:

| Severity | Pre-GA Odoo-20 example |
|----------|------------------------|
| BLOCKER  | All BLOCKER cases from `odoo-19-rules.md` |
| BLOCKER  | Custom reconciliation override that suppresses Odoo-20's new auto-adjustment entries → financial-data correctness gap |
| BLOCKER  | AI server action with `try/except: pass` that silently swallows LLM errors and leaves partial state |
| MEDIUM   | Addon assumes read-after-write consistency on data that may live on a read replica |
| MEDIUM   | AI step mutates accounting / PII data without an audit trail |
| MEDIUM   | Targeting Odoo 20 pre-release without a CI verification job against the 20 nightly — flag for the team |
| LOW      | Legacy mobile CSS override that the new mobile shell handles natively |
| LOW      | Manual POS combo construction where the new combo API would suffice |

## D. Action when Odoo 20 GA ships

When `https://www.odoo.com/documentation/20.0/developer/reference/backend/orm/changelog.html`
becomes available (estimated October 2026):

1. Read the full ORM changelog top-to-bottom.
2. Extract REMOVED / DEPRECATED / RENAMED / ADDED sections.
3. Rewrite Sections A–C of this file to mirror the structure of
   `odoo-19-rules.md` with concrete examples.
4. Update `odoo-code-review/SKILL.md` Step 0 detection signals — any new
   20-only patterns become signals.
5. Drop the "pre-GA stub" header.

Until then: when a finding cites a "20-only" rule, the reviewer must say so
explicitly in the PROOF line: *"Proof relies on Odoo 20 pre-release roadmap;
verify against final changelog when GA ships."*

## Anti-patterns specific to pre-GA Odoo-20 review

- Treating pre-GA roadmap items as confirmed API breaks — they may shift before GA.
- Demanding the addon migrate to "Odoo 20 patterns" before GA — premature.
- Skipping the rule chain (20 → 19 → 18) and only checking 20-roadmap items.
- Assuming the read-replica behavior is on by default — verify with the user / deployment topology.

## Migration notes (19 → 20)

To be filled when 20 GA ships. Until then, the 19 → 20 migration is **not
recommended for production** — wait for the official changelog + at least
one point release (e.g. 20.1).
