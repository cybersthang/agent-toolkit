# Enterprise MRP — depth reference

Companion to `SKILL.md` §5 (MRP work-order lifecycle). All examples use
placeholder names — discover real model names via
`codebase.search_model_definitions` before applying.

> **Version note.** Work-order state names + the `mrp.workorder` /
> `mrp.production` button method names shifted between 12, 13, and 17+.
> The pattern below uses 13+ shape (`button_start` / `button_finish` /
> `button_mark_done`). For 12, the equivalents are `action_start` /
> `record_production`. `<see Odoo Enterprise mrp_workorder release notes>`
> for the exact selection values per version.

## The MO lifecycle — the actual graph

```
                              action_confirm()
                              (explodes BOM into
                              move_raw_ids +
draft ───────────────────────►move_finished_ids +
                              workorder_ids)
                                     │
                                     ▼
                                 confirmed
                                     │
                          action_assign() (reserves
                          components from stock)
                                     │
                                     ▼
                              ready  (work orders
                                     are now startable)
                                     │
                       button_plan() (schedules WO on
                       work centers per routing)
                                     │
                                     ▼
                              progress
                                     │
                       all WO button_finish() done
                                     │
                                     ▼
                          to_close ── button_mark_done() ──► done
                                                              │
                                                              │ (immutable
                                                              │  post-done;
                                                              │  reverse via
                                                              │  scrap or
                                                              │  unbuild)
```

### State transition pitfalls

- **Skipping `action_confirm`**: code that mutates `mrp.production` fields
  *before* `action_confirm` may not trigger the BOM explosion at all.
  Look for `mo.button_mark_done()` calls on records still in `draft`.

- **Skipping `action_assign`**: work orders proceed in `ready` state but
  no reservations exist on `stock.move`. The final `button_mark_done`
  backflushes the components — if stock is empty, it writes negative
  `qty_available` on quants (allowed by Odoo, but corrupts inventory).

- **Calling `button_mark_done` while WOs are still `progress`**: raises
  a `UserError` in v13+, but in v12 it silently closes the MO and leaves
  orphaned work orders. Always loop work orders and `button_finish` them
  first.

## BOM explosion — the N+1 trap

When a BOM has sub-BOMs (kit explosion), iterating naively explodes line
by line:

```python
# BAD — N+1 + recursive sub-BOM read on every line
def explode_bom(self, product, qty):
    components = []
    for line in product.bom_ids[:1].bom_line_ids:  # 1 query: bom_line_ids
        sub_bom = self.env['mrp.bom']._bom_find(product=line.product_id)  # N searches
        if sub_bom:
            components.extend(self.explode_bom(line.product_id, line.product_qty * qty))
        else:
            components.append((line.product_id, line.product_qty * qty))
    return components
```

For a BOM with 20 lines, each with a sub-BOM, that's 20 `_bom_find` calls
plus 20 recursive descents — easily 200+ queries on a moderately-sized
product structure.

```python
# GOOD — use the Odoo helper that batches the recursion
def explode_bom(self, product, qty):
    bom = self.env['mrp.bom']._bom_find(product=product)
    if not bom:
        return []
    boms_done, lines_done = bom.explode(product, qty)
    return [(line.product_id, line_qty['qty']) for line, line_qty in lines_done]
```

`bom.explode()` is the canonical Odoo helper — it handles sub-BOM
recursion in a single pass with proper prefetching. `<see Odoo
mrp.bom.explode() docs>` for the exact return shape per version.

Cross-reference: this overlaps with `odoo-performance` Pattern 1.1
(N+1 queries). Run the perf falsification recipe from that skill
against any custom BOM-explosion code before approving.

## Work-order reservation + backflush

Default Odoo backflushes components at `button_mark_done`:

1. Each `move_raw_id` reduces `stock.quant` by `quantity_done`.
2. Lot/serial linking happens via `move_line_ids` (the detailed moves).
3. If `quantity_done > qty_available`, the quant goes negative — by
   default this is **allowed** unless `picking_type.use_create_lots`
   or a custom `_check_negative_inventory` constraint blocks it.

```python
# Inspect what would happen — pre-flight check
def _can_produce(self, mo):
    for move in mo.move_raw_ids:
        available = move.product_id.with_context(
            location=mo.location_src_id.id,
        ).qty_available
        if move.product_uom_qty > available:
            return False, "Insufficient %s (need %s, have %s)" % (
                move.product_id.display_name, move.product_uom_qty, available,
            )
    return True, None
```

For lot-tracked components, this gets more nuanced — you must check
`stock.production.lot` quantities per-lot, not just product-aggregate.

## Routing + work-center capacity

`mrp.routing` (12–14) / `mrp.routing.workcenter` lines define which work
center performs each operation, with `time_cycle` (minutes per unit).
The MO planner (`button_plan`) walks these and assigns time slots
respecting `workcenter.resource_calendar_id`.

The common bug pattern: code that creates work orders manually and
sets `date_planned_start` / `date_planned_finished` by hand, without
consulting `workcenter._get_capacity_intervals()`. Result: two work
orders overlap on the same machine, but the planner doesn't catch it
because the WOs are pre-scheduled.

Always use `mo.button_plan()` to let Odoo place WOs on the calendar.
If you must override timing, call `workcenter._get_first_available_slot()`
to find a non-overlapping window.

## Scrap + unbuild — the only post-done modifications

Once `mo.state == 'done'`, the MO is immutable. To correct it:

- **Scrap** (`stock.scrap`): remove finished product from stock (e.g.
  defective unit). Does NOT return components.
- **Unbuild** (`mrp.unbuild`): full reversal — reads `mo.move_finished_ids`,
  removes the finished product, re-stocks the components. The audit
  trail links unbuild → original MO via `mo_id`.

```python
def unbuild_mo(self, mo, qty):
    return self.env['mrp.unbuild'].create({
        'mo_id': mo.id,
        'product_id': mo.product_id.id,
        'product_qty': qty,
        'product_uom_id': mo.product_uom_id.id,
        'location_id': mo.location_dest_id.id,
        'location_dest_id': mo.location_src_id.id,
    }).action_unbuild()
```

`<see Odoo Enterprise mrp.unbuild docs>` for the exact field list per
version (`bom_id` is required in some versions, computed in others).

## Pitfalls checklist (paste into review)

- [ ] Does `produce_*` flow call `action_confirm` BEFORE any
      `button_mark_done`?
- [ ] Does it call `action_assign` to reserve components?
- [ ] Does it loop `workorder_ids` and `button_finish` each before
      `button_mark_done`?
- [ ] Any custom BOM explosion that doesn't use `bom.explode()`?
      → check for N+1 (cite odoo-performance §1.1).
- [ ] Any post-done modifications to `mo`? → must go through
      `stock.scrap` or `mrp.unbuild`.
- [ ] Manual `date_planned_*` writes that bypass `button_plan()`? →
      capacity conflicts.
- [ ] Negative `qty_available` after `button_mark_done`? → reservation
      step was skipped.
