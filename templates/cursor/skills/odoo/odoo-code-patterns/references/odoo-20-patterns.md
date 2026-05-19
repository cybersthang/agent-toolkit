# Odoo 20 — pattern deltas (cascade from 19 ← 18 ← 17) — PRE-GA STUB

> **Status**: Pre-GA stub as of toolkit version 0.5.0 (May 2026).
> Apply Odoo 19 patterns + flag 20-specific items as MEDIUM until the
> GA changelog ships.

Load this **on top of** `odoo-19-patterns.md`. Until Odoo 20 GA, fall
back to 19 patterns for anything not explicitly listed here.

## Verified deltas (so far)

(none yet — Odoo 20 is pre-GA)

## Roadmap signals to flag MEDIUM

- ORM batch API changes (rumored).
- Stricter access enforcement (rumored).
- New frontend framework features in OWL (rumored).

If you see code that looks 20-specific (e.g. unfamiliar import path, new
decorator), do NOT auto-apply 19 rules — flag for user review and ask.

## Updating this file

When Odoo 20 GA ships:
1. Read the official changelog.
2. Move verified rules from "Roadmap" into "Verified deltas".
3. Drop the PRE-GA STUB banner.
4. Bump toolkit MINOR version.
