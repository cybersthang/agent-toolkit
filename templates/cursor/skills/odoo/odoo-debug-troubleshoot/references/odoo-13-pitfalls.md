# Odoo 13 — debug pitfalls (standalone)

> odoo-13 reference (drafted v0.29). Deltas vs odoo-12-pitfalls.md web-verified where cited; `<!-- VERIFY -->` items need DEV confirmation.

Load when Step 0 detected major = **13**. Odoo 13 shares most v12
pitfalls; the new ones cluster around the removed `@api.multi`/`@api.one`
decorators and the `account.move` merge.

## 13-specific symptoms

| Symptom | Root cause | Fix |
|---|---|---|
| `AttributeError: module 'odoo.api' has no attribute 'multi'` (or `'one'`) at import | `@api.multi` / `@api.one` used in 13 — both removed from `odoo/api.py` | Delete the decorator; methods iterate `self` by default (`for rec in self:`) |
| `KeyError: 'account.invoice'` / `ValueError: Invalid model account.invoice` | Code references the merged-away `account.invoice` model | Use `account.move`; lines via `invoice_line_ids` → `account.move.line` |
| `ValueError: Invalid field 'move_type' on model 'account.move'` | `move_type` is the **v14** field name; 13 uses `type` | Use `type` (`out_invoice`, `in_invoice`, `out_refund`, `in_refund`, `entry`, ...) on 13 |
| Refund wizard `account.invoice.refund` missing | Wizard removed in 13 | Use `account.move.reversal` (`account.action_view_account_move_reversal`) |
| Batch `create([{...},{...}])` only runs override logic on first record | `create()` overridden as single-record `@api.model create(vals)` | Re-declare as `@api.model_create_multi` + `vals_list`, loop inside |
| Company-dependent field reads stale value across companies | Compute missing `@api.depends_context('force_company')`, or value read without `force_company` context | Add the context-depends; read via `.with_context(force_company=<id>)` |
| `self.env.company` returns wrong company in a cron/batch | Active company comes from `allowed_company_ids` context which is empty in cron | Set `force_company` / company in context explicitly per record in batch loops |

## Pitfalls UNCHANGED from v12

The following are identical in 13 — see odoo-12-pitfalls.md:
- Compute không re-run khi `@api.depends` cite sai field path.
- `@api.constrains` timing vs wizard `create()` then compute.
- `ir.cron` direct trigger method name (`method_direct_trigger()`).
- Email validator rejecting `mock@mock`-style addresses (use
  `<prefix>.test@example.com`).
- `attrs="{...}"` parse errors from missing quotes.

(Only difference: drop `@api.multi` from any v12 example code.)

## Patterns to expect in v13 traceback

- `odoo.api` AttributeError for `multi` / `one` — the #1 v12→13 port bug.
- `account.move` / `account.move.line` frames where v12 would have shown
  `account.invoice` — the merge moved all invoice logic here.
- `@api.depends_context` / `force_company` cache-key frames on
  company-dependent field reads.
- `web.Widget` / `odoo.define` frontend frames (still jQuery in 13; OWL
  backend frames would indicate ported-forward 14+/17 code).

<!-- VERIFY(odoo-13): `self.env.norecompute()` reported to "have no effect in v13" in a community GitHub issue (#38178) — the context manager still exists in 13.0 models.py but its observable effect on recompute batching is unconfirmed. DEV confirm before asserting as a pitfall. -->
