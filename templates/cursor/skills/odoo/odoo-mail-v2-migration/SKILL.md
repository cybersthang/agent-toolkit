---
name: odoo-mail-v2-migration
description: Odoo mail framework v1 (v12-18 — `mail.thread` + `mail.activity.mixin` + `mail.message` with `message_post()` / `message_subscribe()`) vs v2 (v19+ — refactored thread/follower/notification storage + APIs). CAVEAT — v19 mail-v2 docs are unstable at v0.27 time of writing; this skill describes v1 in depth and v2 abstractly. Agents working on v19+ MUST verify exact APIs against the installed Odoo source (`codebase.search_model_definitions({"model": "mail.thread"})`) before applying any pattern below. Top 5 v1 anti-patterns (mail.thread bloat, N+1 message_post in create, hardcoded subtype xmlids, bypassing _message_post_after_hook, direct INSERT into mail_message). Trigger phrases — "mail", "thread", "activity", "message_post", "subscribe", "follower", "subtype", "notification", "v19 mail", "mail.v2". Audience — Odoo consultancies migrating mail-heavy modules across v12→v19 boundaries.
license: MIT
---

# Odoo — Mail framework v1 → v2 migration (version-aware)

Mail-framework code is the **most version-fragile** part of Odoo. The
`mail.thread` + `mail.activity.mixin` + `mail.message` triad stayed
stable v12-v18 — but v19 refactors it into "mail-v2" with different
storage (separate notification table, denormalized follower index) and
different APIs.

This skill enumerates the **top 5 v1-era anti-patterns** + migration
notes for multi-version modules (v15 + v17 + v19 in parallel support).

> CAVEAT — Mail-v2 (v19+) is described **abstractly** here. Public docs
> are unstable as of v0.27 (Jan 2026). Before pattern-matching any
> v19+ codebase, **read the installed source**:
> `codebase.search_model_definitions({"model": "mail.thread"})` plus
> `mail.followers` and `mail.notification`. Do NOT assume v1 patterns
> carry — name a method only after you've seen it in installed source.

Pair with `odoo-code-review` and `odoo-data-verification`.

## 0. Version detection (MANDATORY first step)

Same protocol as `odoo-multi-company` / `odoo-code-review`:

1. **`__manifest__.py` `version` field** — `codebase.read_manifest({module_path})`.
   Pattern `^(\d+)\.0\.`.
2. **Fallback signals** (only if manifest missing):
   - `_inherit = ['mail.thread', 'mail.activity.mixin']` with classic
     `message_post(...)` call sites → v12-18 (mail-v1).
   - Imports / refs to `mail.notification.web.push` or `discuss.channel`
     as the new thread base, or absence of `mail.followers` rows → v19+
     (mail-v2 candidate; verify against source).
   - `@api.depends('message_ids', 'message_follower_ids')` compute
     fields → v1 era; if those field names changed, you're on v2.
3. **Ask the user** only if signals are inconclusive.

Then load the matching reference:

| Detected major | Reference (mail specifics) |
|---|---|
| 12 | `references/odoo-12-mail-v1.md` (legacy, deep dive on v1) |
| 13 / 14 / 15 / 16 | apply `odoo-17-mail-v1.md` + flag LOW transitional |
| 17 / 18 | `references/odoo-17-mail-v1.md` (v1 mature) |
| 19+ | `references/odoo-19-mail-v2.md` (annotated stub — **verify against installed source** before relying on any signature) |

## 1. Pattern A — Inheriting `mail.thread` on every model

**Confidence: H**

### Problem

Every model inheriting `mail.thread` gets follower index, chatter,
activity slots. Addons sprinkling `_inherit = ['mail.thread']` on every
business model "just in case" bloat `mail_message` and `mail_followers`
with rows that never serve any UX purpose — and every `unlink()`
cascades through follower sweeps. Invisible at dev scale, painful at
10M+ rows.

### Bad / Good

```python
# v17 — BAD: chatter inherited but no chatter view ever shown
class InternalScratchpad(models.Model):
    _name = 'my.internal.scratchpad'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # bloat
    name = fields.Char()

# v17 — GOOD: inherit only when model surfaces chatter in a form view
class CustomerComplaint(models.Model):
    _name = 'my.customer.complaint'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(tracking=True)  # tracking only on visible fields
```

### Falsification recipe

1. `grep -r "_inherit.*mail.thread" addons/` → list candidate models.
2. Check `views/` for `<chatter/>` (v17+) or `<div class="oe_chatter">` (v12-16).
3. No chatter view = decorative inheritance; row cost only.
4. Probe: `SELECT COUNT(*) FROM mail_followers WHERE res_model='my.internal.scratchpad';`
   — non-zero on a chatter-less model confirms the bloat.

---

## 2. Pattern B — `message_post()` inside `create()` without batching

**Confidence: H**

### Problem

`message_post()` does ≥1 INSERT each into `mail_message`,
`mail_notification`, possibly `mail_followers`, plus bus events. In a
batched `@api.model_create_multi` path, looping per-record produces
N×3+ INSERTs instead of one bulk path.

### Bad / Good

```python
# v17 — BAD: N+1 inside batch create override
@api.model_create_multi
def create(self, vals_list):
    recs = super().create(vals_list)
    for rec in recs:
        rec.message_post(body=_("Auto-created"), subtype_xmlid='mail.mt_comment')
    return recs

# v17 — GOOD: single batched write via _message_log_batch (v15+)
@api.model_create_multi
def create(self, vals_list):
    recs = super().create(vals_list)
    if recs:
        recs._message_log_batch(bodies={r.id: _("Auto-created") for r in recs})
    return recs
```

For v12-14 (no `_message_log_batch`), use `_message_log` per record
only when audit is genuinely required — otherwise drop the auto-post
and rely on `tracking=True` changelog.

### Falsification recipe

1. Enable `pg_stat_statements`.
2. Call `.create([{...}] * 100)`.
3. Count `INSERT INTO mail_message` — bad: 100 rows; good: 1 bulk.

---

## 3. Pattern C — Hardcoding subtype `xml_id`s

**Confidence: M**

### Problem

Subtype `xml_id`s are stable **within** a major Odoo version but rename
across majors (some `mt_*` consolidated v15→v17; v19 mail-v2 reshuffles
again). A hardcoded string either falls back silently to the note
subtype (visibility leak — internal note becomes external) or raises
`ValueError: External ID not found`.

### Bad / Good

```python
# v17 — BAD: hardcoded, no fallback
def _notify_assigned(self):
    self.message_post(body=_("Assigned"), subtype_xmlid='mail.mt_comment')

# v17 — GOOD: resolve via ref() with fallback, fail loud
def _notify_assigned(self):
    subtype = self.env.ref('mail.mt_comment', raise_if_not_found=False)
    if not subtype:
        _logger.error("mail.mt_comment subtype missing on this Odoo version")
        return
    self.message_post(body=_("Đã giao việc"), subtype_id=subtype.id)
```

### Falsification recipe

1. `grep -r "subtype_xmlid=" addons/` → list every hardcoded subtype.
2. For each: `self.env.ref(xmlid, raise_if_not_found=False)` on the
   target version's installed DB.
3. If any returns `False` — the call silently degraded.

---

## 4. Pattern D — Bypassing `_message_post_after_hook()`

**Confidence: M**

### Problem

`_message_post_after_hook()` is the official extension point for
post-message side effects (downstream records, external mirrors).
Overriding `message_post()` itself and running side effects **before**
`super()` means a later exception rolls back the message — but the
external API call already fired.

### Bad / Good

```python
# v17 — BAD: side effect before super; rollback leaves external out-of-sync
def message_post(self, **kwargs):
    self._sync_to_external_crm()  # fires even if super() raises later
    return super().message_post(**kwargs)

# v17 — GOOD: official after-hook only runs on successful post
def _message_post_after_hook(self, message, msg_vals):
    super()._message_post_after_hook(message, msg_vals)
    self._sync_to_external_crm(message)
```

### Falsification recipe

1. `grep -rn "def message_post" addons/` → custom overrides.
2. Check side effects pre- vs post-`super()`.
3. Monkeypatch a forced exception in `_notify_thread()` during test;
   confirm external side effect fired despite rollback.

---

## 5. Pattern E — Direct INSERT into `mail_message`

**Confidence: H**

### Problem

Writing directly to `mail_message` via `cr.execute("INSERT ...")` or
`self.env['mail.message'].sudo().create({...})` skips:
- Follower notification dispatch (`mail.notification` rows).
- Activity sync (`mail.activity` linked records).
- Subtype-driven visibility filtering.
- Bus events to the discuss client.

The row exists but nobody is notified. In mail-v2 (v19+), denormalized
follower indexes won't update either — chatter UI shows stale state.

### Bad / Good

```python
# v17 — BAD: direct INSERT, bypasses everything
def _audit_log(self, body):
    self.env['mail.message'].sudo().create({
        'model': self._name, 'res_id': self.id,
        'body': body, 'message_type': 'comment',
    })

# v17 — GOOD: _message_log for audit-only (no follower notify);
# message_post for user-visible chatter
def _audit_log(self, body):
    self._message_log(body=body)

def _user_visible(self, body):
    self.message_post(body=body, subtype_xmlid='mail.mt_note')
```

### Falsification recipe

1. `grep -rn "mail.message.*create\|INSERT.*mail_message" addons/`.
2. For each, check whether a `mail.notification` row exists post-call.
3. If not — invisible to anyone monitoring the thread.

---

## 6. v1 → v2 migration considerations (v18 → v19)

### Code patterns that need attention

| v1 call (v12-18) | v2 strategy (v19+) — verify against source |
|---|---|
| `self.message_post(body=...)` | Likely renamed signature; verify on `mail.thread`. |
| `self.message_subscribe(partner_ids=[...])` | Follower storage refactored; new API may take a unified record-or-partner ref. |
| `self.message_ids` (One2many) | May be denormalized — check if field still exists or moved to a computed proxy. |
| `subtype_xmlid='mail.mt_comment'` | Subtype set reshuffled in v2; verify each xmlid. |
| `_message_post_after_hook()` | Hook name may have changed; grep `_after_hook` on installed `mail.thread`. |
| `mail.activity` direct manipulation | `mail.activity.mixin` likely still works, but rendering moved — verify. |

### Testing the same module on v18 vs v19

1. Spin two scratch DBs (v18, v19) from the same module source.
2. Run shared pytest: `odoo-bin -d <db> -i <module> --test-enable --stop-after-init`.
3. **Always** read `mail.thread` source on both versions before writing
   the test (`find odoo/addons/mail/models -name "mail_thread*.py"` and
   diff signatures).
4. Gate v19-only paths with `@unittest.skipUnless(MAIL_V2, ...)` where
   `MAIL_V2` is detected via a v2-only field on `mail.thread`.

### Backward-compat shim — DO NOT ship as-is

```python
# v17/v18/v19 compat shim — method name is illustrative; VERIFY first
def _post_compat(self, body, subtype_xmlid='mail.mt_comment'):
    if hasattr(self, '_message_post_v2'):   # placeholder — read source!
        return self._message_post_v2(body=body, subtype_xmlid=subtype_xmlid)
    return self.message_post(body=body, subtype_xmlid=subtype_xmlid)
```

## 7. Code-review checklist (files matching `models/mail_*` or any `_inherit = ['mail.thread', ...]`)

| Severity | Check |
|---|---|
| **H** | Direct INSERT into `mail_message` / `sudo().create()` on `mail.message`. |
| **H** | `message_post()` inside `@api.model_create_multi` loop without batching. |
| **H** | `_inherit = ['mail.thread']` on a model with no chatter view. |
| **M** | Hardcoded `subtype_xmlid` without `raise_if_not_found=False` fallback. |
| **M** | Side effects in `message_post()` super-override before calling `super()`. |
| **M** | v19+ code that still uses v1-only field names (`message_ids`, `message_follower_ids`) without source verification. |
| **L** | `message_subscribe(partner_ids=...)` without checking whether the partner already follows. |
| **L** | Activity creation via `self.env['mail.activity'].create({...})` instead of `self.activity_schedule(xmlid)`. |

## 8. References

- `references/odoo-12-mail-v1.md` — legacy v1 (chatter widget,
  `mail.thread` original signatures, v12-era `message_post()` behavior,
  subtype matrix).
- `references/odoo-17-mail-v1.md` — v1 mature (`_message_log_batch`,
  stable `_message_post_after_hook`, enriched activity mixin,
  consolidated subtype xmlids).
- `references/odoo-19-mail-v2.md` — **annotated stub. Mark "verify
  against installed source" at the top.** Sketches v2 storage refactor
  (separate notification index, denormalized follower cache); every
  signature must be re-checked via `codebase.search_model_definitions`.

## 9. Sibling skills to call BEFORE this one

- `odoo-codebase-discovery` — locate target model + read manifest version.
- `odoo-deterministic-answers` — `lookup_canonical_decision` for
  project-specific mail rules (e.g. "always `_message_log` for audit").

## 10. Hard rules summary

- Never inherit `mail.thread` on a model without a chatter view.
- Never call `message_post()` per-record inside a batched
  `create()` — use `_message_log_batch` (v15+).
- Never hardcode `subtype_xmlid` without a `self.env.ref(..., raise_if_not_found=False)`
  fallback + explicit log on miss.
- Never run side effects before `super().message_post()` — use
  `_message_post_after_hook` instead.
- Never INSERT into `mail_message` directly — always go through
  `message_post()` (visible) or `_message_log()` (audit-only).
- On v19+: **always read installed `mail.thread` source first**.
  Mail-v2 APIs in this skill are abstract sketches, not contracts.
