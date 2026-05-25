# Odoo multi-currency — cross-company conversion patterns

Not version-locked. Apply to all Odoo majors. Where v12 and v17+ differ
on a specific call, the section flags `[v12]` / `[v17+]`.

## 1. The 4 things that affect a currency conversion result

Every `_convert()` call answers: "how many units of `to_currency`
equals N units of `from_currency`, *for company C on date D*?" The
inputs are:

1. `from_amount` (float) — source amount.
2. `to_currency` (`res.currency` record) — target currency.
3. `company` (`res.company` record) — controls which rate table is
   consulted (rates are per-company).
4. `date` (`fields.Date`) — picks the rate row whose `name` ≤ D (the
   most-recent rate not in the future).

Getting any of these wrong → silent FX drift. The most common mistake
is passing `self.env.company` when the conversion logically belongs to
a different company's books.

## 2. Canonical signature

```python
# v17+ — modern
target_amount = src_currency._convert(
    from_amount=amount,
    to_currency=target_currency,
    company=rec.company_id,
    date=fields.Date.context_today(self),
    round=True,
)
```

```python
# v12 — older positional form, same semantics
target_amount = src_currency._convert(
    amount, target_currency, rec.company_id, fields.Date.today(),
)
```

The `round=True` default applies `target_currency.rounding` to the
result. Pass `round=False` only when accumulating in a higher-precision
intermediate before final rounding.

## 3. The "which company's rates" question

Rates live in `res.currency.rate` keyed by `(currency_id, company_id,
name)`. When two companies have **different rate sets** for the same
currency pair (common in groups operating in different markets), the
choice of `company` argument determines which set is used.

Rules of thumb:

- **Inter-company invoice / bill**: use the *originating* company's
  rates (the company issuing the document).
- **Consolidation report**: use the *consolidating* (parent) company's
  rates — this is the explicit "we are translating subsidiary numbers
  to parent currency" call.
- **Per-record aggregation**: use `rec.company_id`'s rates per record;
  do NOT cache one company's `_convert` arg outside the loop.

```python
# WRONG — caches the wrong company's rates across heterogeneous records
def _sum_in_usd(self, records):
    company = self.env.company  # bug: not all records belong to this co
    usd = self.env.ref('base.USD')
    return sum(
        r.currency_id._convert(r.amount, usd, company, fields.Date.today())
        for r in records
    )

# RIGHT — each record's own company picks the right rate table
def _sum_in_usd(self, records):
    usd = self.env.ref('base.USD')
    return sum(
        r.currency_id._convert(r.amount, usd, r.company_id, fields.Date.today())
        for r in records
    )
```

## 4. Date-axis pitfalls

`_convert` selects the rate row where `name <= date`. Two common bugs:

- **`fields.Date.today()` vs `context_today`** — `today()` returns the
  server's UTC date; `context_today(self)` respects the user's
  timezone. Cross-timezone deployments can land on the wrong rate
  row at the day boundary.
- **Historical conversion using "today's" rate** — when re-computing
  amounts for an old invoice, pass the invoice's `invoice_date`, not
  `fields.Date.today()`. The cron / report that retro-computes with
  today's rate silently restates history.

```python
# RIGHT — historical doc uses its own date
target = src.currency_id._convert(
    src.amount, target_currency, src.company_id, src.invoice_date or src.date,
)
```

## 5. Rounding semantics

Per-currency `rounding` field (`res.currency.rounding`) defines the
quantum. Examples:

- USD `rounding=0.01` → 2 decimal places, banker's round.
- JPY `rounding=1.0` → integer yen.
- BHD (Bahraini Dinar) `rounding=0.001` → 3 decimal places.

The rule: **round in each currency's quantum BEFORE summing**, then
round the final sum in the target currency's quantum. Summing
unrounded floats and rounding once at the end is a classic source of
last-cent drift across thousands of rows.

```python
# RIGHT — per-record round-then-sum
total = 0.0
for r in records:
    amount_in_target = r.currency_id._convert(
        r.amount, target, r.company_id, r.date,  # round=True default
    )
    total += amount_in_target
final = target.round(total)
```

Use `currency.compare_amounts(a, b)` instead of `a == b` for monetary
equality — it accounts for `rounding`. Direct float comparison is a
floating-point trap.

## 6. `currency_id` on the record — store-vs-related decision

Three shapes appear in the wild:

```python
# A — currency stored on the record (sale.order, account.move)
currency_id = fields.Many2one('res.currency', required=True,
                              default=lambda s: s.env.company.currency_id)

# B — currency related from a parent (sale.order.line follows order)
currency_id = fields.Many2one('res.currency', related='order_id.currency_id',
                              store=True, readonly=True)

# C — currency = company's currency (always)
currency_id = fields.Many2one('res.currency',
                              related='company_id.currency_id',
                              store=True, readonly=True)
```

Pitfall: if you use shape B or C with `store=False`, every monetary
read triggers a related-field traversal — slow at report scale. Force
`store=True` for any currency_id used in `read_group` or as a sort
key.

Inter-company invoicing requires shape A (the buyer's invoice currency
may differ from the seller's company currency).

## 7. Falsification recipes

### Recipe 1 — wrong-company rates picked

1. Create 2 companies sharing a currency pair (e.g. USD ↔ EUR), but
   with **different rates** in their `res.currency.rate` tables
   (Company A: 1 USD = 0.90 EUR; Company B: 1 USD = 0.95 EUR).
2. Create one record of `amount = 100 USD` under each company.
3. Sum in EUR using `self.env.company` (set to A) for both.
4. Bug: both convert at 0.90 → total = 180 EUR. Correct: A at 0.90,
   B at 0.95 → total = 185 EUR.

### Recipe 2 — rounding drift

1. Currencies: source = JPY (`rounding=1.0`), target = USD
   (`rounding=0.01`).
2. Create 1000 records with `amount = 0.49 JPY` each.
3. Sum in USD with per-record round (correct) vs sum-then-round (bug).
4. Per-record round: each `0.49 JPY` rounds to `0 JPY` → total = 0 USD.
5. Sum-then-round: `1000 * 0.49 = 490 JPY` → ~3.27 USD at 0.0067 rate.
6. The per-record path is correct for "list of JPY transactions" —
   you can't have a fraction of a yen on any individual line.

### Recipe 3 — historical-rate drift

1. Create an invoice on date D with rate R1.
2. Update the rate table: new row for currency pair on date D+30.
3. Re-render the invoice's "amount in company currency" using
   `fields.Date.today()` (= D+30).
4. Bug: shows the new amount under the old date. Correct: must use
   the invoice's own date / lock the rate at creation.

## 8. Cross-references

- `references/odoo-12-multicompany.md` — `force_company` context key
  flowing into rate selection.
- `references/odoo-17-multicompany.md` — `with_company()` chain
  propagation into `_convert`.
- `<see Odoo res.currency module source>` — for the exact
  `_get_conversion_rate` algorithm + tiebreaker when a date matches
  no rate row.

## 9. Hard rules

- Never call `_convert` with `self.env.company` when iterating
  heterogeneous-company records — use `rec.company_id`.
- Never round once at the end of a multi-record sum — round per-record
  first.
- Never use `fields.Date.today()` for historical document conversion
  — use the document's own date.
- Never compare monetary amounts with `==` — use
  `currency.compare_amounts(a, b)`.
- Never store a `currency_id` `related=` field with `store=False` if
  it appears in `read_group` / `order=` clauses — measurable perf hit.
