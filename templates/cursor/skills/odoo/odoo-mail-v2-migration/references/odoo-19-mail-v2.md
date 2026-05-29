# Odoo 19 — mail framework (annotated; VERIFY against installed source)

> **VERIFY-FIRST.** Before relying on any signature here, read the
> installed source: `codebase.search_model_definitions({"model":
> "mail.thread"})`, plus `mail.followers`, `mail.message`,
> `mail.notification`. Signatures below were verified against branch
> `19.0` of `github.com/odoo/odoo` at time of writing — but 19 is recent;
> point releases move. Name a method only after you've seen it installed.

## What "mail-v2" actually is (and isn't)

"Mail v2" is **not an Odoo marketing term** and there is **no server-side
rename of `mail.thread`/`message_post`** in 19. Verified against 19.0
source, the load-bearing facts are:

- **`mail.thread` core Python API is stable 17 → 19.** `message_post`,
  `message_subscribe`, `_message_post_after_hook`, `_message_log`,
  `_message_log_batch` all keep their 17 signatures (one additive change
  to `message_post` kwargs — below).
- **`mail.followers` model is unchanged** — same `_name`, same fields
  (`res_model`, `res_id`, `partner_id`, `subtype_ids`). There is **no
  "separate notification table" / "denormalized follower index"
  refactor** visible in source. Do not assert one.
- **`mail.message` model fields are stable** — `model`, `res_id`,
  `message_type`, `subtype_id`, `mail_activity_type_id` all present and
  unchanged from 17.

The real, verifiable deltas in the 19 mail/discuss subsystem are: (1) the
**`<chatter/>` form element** (18+), and (2) **OWL frontend
reorganization** (file paths moved). Describe those; do NOT invent a
storage rewrite.

## `message_post()` — 19 signature (stable + additive email kwargs)

```python
def message_post(self, *,
                 body='', subject=None, message_type='notification',
                 email_from=None, author_id=None, parent_id=False,
                 subtype_xmlid=None, subtype_id=False,
                 partner_ids=None, outgoing_email_to=False,
                 incoming_email_to=False, incoming_email_cc=False,
                 attachments=None, attachment_ids=None, body_is_html=False,
                 **kwargs):
```

Delta vs 17:
- **Still keyword-only**, still `subtype_xmlid=` / `subtype_id=` — the
  v1-era core anchors hold. Code written for 17 keeps working.
- New **additive** kwargs: `outgoing_email_to`, `incoming_email_to`,
  `incoming_email_cc` (email routing; the 19 "reply with CC" chatter UX).
  Optional — existing callers unaffected.
- NB: the `@api.returns('mail.message', ...)` decorator that wraps it in
  17 is no longer directly above the def in 19 source — `message_post`
  still returns the `mail.message` recordset; do not assume the decorator
  presence, just rely on the return value.

```python
# 19 — identical call shape to 17; resolve subtype defensively
subtype = self.env.ref('mail.mt_comment', raise_if_not_found=False)
if subtype:
    self.message_post(body=_("Đã giao việc"), subtype_id=subtype.id)
```

## Hooks + log methods — unchanged from 17

```python
def _message_post_after_hook(self, message, msg_values):    # same 2 args as 17
    return

def _message_log(self, *, body='', subject=False, author_id=None,
                 email_from=None, **kwargs): ...

def _message_log_batch(self, bodies, subject=False, author_id=None,
                       email_from=None, message_type='notification', **kwargs): ...
```

- After-hook is still `(self, message, msg_values)` — the migration-table
  guess that "the hook name may have changed" is **not** borne out in
  source. Still the correct place for post-message side effects.
- `_message_log_batch` still present — keep using it for batched-create
  audit.

## `message_subscribe()` — unchanged from 17

```python
def message_subscribe(self, partner_ids=None, subtype_ids=None): ...
def message_unsubscribe(self, partner_ids=None): ...
```

- Partner-only, same as 17. No new "unified record-or-partner ref"
  appears in source. Do not assert one without reading installed code.

## Chatter view tag — `<chatter/>` element (18+)

This is a **real, breaking view delta** for 17→18/19 migration:

```xml
<!-- 17 and earlier: the oe_chatter div -->
<div class="oe_chatter">
    <field name="message_follower_ids"/>
    <field name="activity_ids"/>
    <field name="message_ids"/>
</div>

<!-- 18 / 19: the <chatter/> element (verified in 18.0 + 19.0 crm forms) -->
<chatter reload_on_post="True"/>
```

- Introduced in **18** (18.0 stock forms already use `<chatter/>`;
  17.0 still uses `oe_chatter`). The bare-field `oe_chatter` div is
  deprecated. When migrating form views, replace the div with
  `<chatter/>` (optional `reload_on_post`, `open_attachments` attrs).
- Falsification: `grep -rn "oe_chatter" addons/` on a 18/19 module — any
  hit is a stale view that should be the element.

## OWL frontend — reorganized, NOT rewritten again

- 19 keeps the **OWL store-service** framework introduced in 17
  (`mail/static/src/core/common/store_service.js` — present 17, 18, 19).
  There is no second store rewrite in 19.
- The chatter OWL `Component` **moved paths**: 17
  `core/web/chatter.js` → 19 `chatter/web_portal/chatter.js` (still
  `export class Chatter extends Component`). Custom JS patching the
  chatter by file path must update the import path; the component model
  is the same OWL `Component`/store pattern.
- If you patch `store_service` or the chatter component, **read the
  installed JS** — the `static/src` tree reshuffles between majors more
  than the Python API does.

## Migration checklist (18 → 19, mail-heavy module)

| Anchor | Status in 19 (verified) | Action |
|---|---|---|
| `message_post(body=, subtype_xmlid=)` | Stable signature | No change needed |
| `_message_post_after_hook(message, msg_values)` | Stable | No change needed |
| `message_subscribe(partner_ids, subtype_ids)` | Stable | No change needed |
| `_message_log_batch(bodies=...)` | Present | Keep for batch audit |
| `mail.followers` / `mail.message` fields | Stable | No data migration for these |
| Form `<div class="oe_chatter">` | Replaced by `<chatter/>` (18+) | **Convert view** |
| Chatter OWL JS path | Moved to `chatter/web_portal/` | **Update JS import path** if patched |
| `subtype_xmlid` strings (e.g. `mail.mt_comment`) | xml_ids can rename across majors | Re-resolve via `env.ref(..., raise_if_not_found=False)` |

## Hard rules (Odoo 19 mail specific)

- **Read installed `mail.thread` source before asserting any signature** —
  this file is annotated, not a contract.
- Do **not** claim a "v2 storage refactor" / "separate notification
  index" — it is not in 19 source. The verifiable changes are the
  `<chatter/>` element (18+) and OWL `static/src` path moves.
- `message_post` is still keyword-only with `subtype_xmlid=`/`subtype_id=`
  — 17-era call sites carry forward unchanged.
- Convert form `oe_chatter` divs to `<chatter/>`; update any chatter JS
  patch to the new `chatter/web_portal/` path.
- Always resolve subtype xml_ids defensively (`env.ref(...,
  raise_if_not_found=False)`) — xml_ids, not method names, are the thing
  that drifts across majors.
