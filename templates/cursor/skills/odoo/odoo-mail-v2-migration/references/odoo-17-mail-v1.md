# Odoo 17 — mail framework v1 (mature)

Reference for the mail/discuss subsystem on **major = 17 / 18**, and the
fallback for 13–16 (apply this, flag LOW transitional). Signatures quoted
from `odoo/addons/mail/models/mail_thread.py` @ branch `17.0`.

This is the **stable v1 plateau**: the server-side `mail.thread` API here
is, for the load-bearing methods, the same as 19 (see the v19 reference
for what actually changed — it's the frontend, not these signatures).

## Inherit the thread + activity mixins

```python
from odoo import api, fields, models


class CustomerComplaint(models.Model):
    _name = 'my.customer.complaint'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Customer Complaint'

    name = fields.Char(tracking=True)                    # 13+: tracking=True
    state = fields.Selection([('new', 'New'), ('done', 'Done')],
                             default='new', tracking=True)
```

Deltas vs 12:
- Tracking is **`tracking=True`** (the `track_visibility='onchange'` form
  was removed in 13).
- Followers are **partner-only** — `message_channel_ids` is gone; the
  `mail.channel` model was renamed to **`discuss.channel`** in 17.
- `@api.multi` / `@api.one` were removed in 13 — every recordset method
  iterates implicitly. Do NOT decorate with `@api.multi`.

## `message_post()` — 17 signature (keyword-only, no `@api.multi`)

```python
@api.returns('mail.message', lambda value: value.id)
def message_post(self, *,
                 body='', subject=None, message_type='notification',
                 email_from=None, author_id=None, parent_id=False,
                 subtype_xmlid=None, subtype_id=False, partner_ids=None,
                 attachments=None, attachment_ids=None, body_is_html=False,
                 **kwargs):
```

Deltas vs 12:
- **No `@api.multi`** (kept `@api.returns`).
- **Keyword-only** (`def message_post(self, *, ...)`) — positional calls
  now raise `TypeError`. Always pass kwargs.
- Subtype split into **`subtype_xmlid=`** (str xml_id, resolved via ref)
  and **`subtype_id=`** (int record id). The old single `subtype=` kwarg
  is gone.
- Notification layout kwarg is **`email_layout_xmlid=`** (was
  `notif_layout=` in 12).
- `body` accepts a `Markup` object for raw HTML (str is auto-escaped).

```python
# 17 — visible comment, resolve subtype defensively (xml_ids rename across majors)
subtype = self.env.ref('mail.mt_comment', raise_if_not_found=False)
if subtype:
    self.message_post(body=_("Đã giao việc"), subtype_id=subtype.id)

# 17 — internal note shortcut
self.message_post(body=_("Note"), subtype_xmlid='mail.mt_note')
```

## `_message_log()` + `_message_log_batch()` — audit, keyword-only

```python
def _message_log(self, *,
                 body='', subject=False,
                 author_id=None, email_from=None, **kwargs):

def _message_log_batch(self, bodies, subject=False,
                       author_id=None, email_from=None,
                       message_type='notification', **kwargs):
```

- **`_message_log_batch` exists from 15** — use it to audit a batch
  `@api.model_create_multi` create in ONE write instead of N posts:

```python
@api.model_create_multi
def create(self, vals_list):
    recs = super().create(vals_list)
    if recs:
        recs._message_log_batch(bodies={r.id: _("Auto-created") for r in recs})
    return recs
```

## `message_subscribe()` / `message_unsubscribe()` — partner-only

```python
def message_subscribe(self, partner_ids=None, subtype_ids=None):
def message_unsubscribe(self, partner_ids=None):
```

- **`channel_ids` is gone** (was in 12). Followers are partners only.
  When migrating 12→17 strip `channel_ids=` from every call.

## `_message_post_after_hook()` — after-hook (param renamed `msg_values`)

```python
def _message_post_after_hook(self, message, msg_values):
    return
```

- Second arg renamed **`msg_values`** (was `msg_vals` in 12 — positional,
  so passthrough callers are fine; kwarg-using overrides must update).
- Still the only correct place for post-message side effects:

```python
def _message_post_after_hook(self, message, msg_values):
    super()._message_post_after_hook(message, msg_values)
    self._sync_to_external_crm(message)        # runs only on successful post
```

- The internal dispatcher is `_notify_thread(self, message, msg_vals=False, **kwargs)`.

## Mail templates (`mail.template`) — `{{ }}` inline + qweb body

```xml
<record id="email_template_complaint" model="mail.template">
    <field name="name">Complaint: Acknowledgement</field>
    <field name="model_id" ref="model_my_customer_complaint"/>
    <field name="subject">Re: {{ object.name }}</field>          <!-- 16+: {{ }} -->
    <field name="body_html" type="html">
        <t t-out="object.partner_id.name or ''"/>                <!-- qweb t-out -->
    </field>
</record>
```

- The `${...}` legacy placeholders (12) were replaced by **`{{ }}`
  inline expressions + qweb `body_html`** in 16. Do not mix syntaxes.

## Chatter — clean OWL `Component` (the 16→17 rewrite)

- **17 is the mail-frontend rewrite boundary.** The old OWL
  messaging-store framework (16: `mail/static/src/models/messaging.js`
  with `registerModel`, chatter as a `LegacyComponent`) was replaced by a
  new store service `mail/static/src/core/common/store_service.js`, and
  the chatter became a clean OWL `Component`
  (`mail/static/src/core/web/chatter.js`, `export class Chatter extends
  Component`).
- 16 chatter = `LegacyComponent` (transitional). 12 chatter = jQuery
  `web.Widget`. Only **17** has the modern OWL store-based chatter.

Form-view chatter tag in 17 is still the **`oe_chatter` div** (the
`<chatter/>` element does NOT exist until 18):

```xml
<div class="oe_chatter">
    <field name="message_follower_ids"/>
    <field name="activity_ids"/>
    <field name="message_ids"/>
</div>
```

## Hard rules (Odoo 17 mail specific)

- `tracking=True` on visible fields only (never `track_visibility`).
- `message_post()` is keyword-only — never positional; subtype via
  `subtype_xmlid=` or `subtype_id=`, never the old `subtype=`.
- Resolve xml_ids with `self.env.ref(xmlid, raise_if_not_found=False)` +
  log on miss (subtypes rename across majors).
- Batch audit with `_message_log_batch(bodies={id: body})`, not a
  per-record `message_post()` loop.
- Side effects only in `_message_post_after_hook(self, message, msg_values)`.
- `message_subscribe(partner_ids=, subtype_ids=)` — no `channel_ids`.
- Form chatter is `<div class="oe_chatter">` in 17 (NOT `<chatter/>`,
  which is 18+).
