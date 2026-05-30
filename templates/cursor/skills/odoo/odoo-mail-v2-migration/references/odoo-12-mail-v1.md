# Odoo 12 — mail framework v1 (legacy deep dive)

Standalone reference for the mail/discuss subsystem on **major = 12**. 12
does NOT cascade from 17 — signatures differ. Every signature below is
quoted from `odoo/addons/mail/models/mail_thread.py` @ branch `12.0`.

## Inherit the thread + activity mixins

```python
from odoo import api, fields, models


class CustomerComplaint(models.Model):
    _name = 'my.customer.complaint'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Customer Complaint'

    name = fields.Char(track_visibility='onchange')   # NB: 12 uses track_visibility
    state = fields.Selection([('new', 'New'), ('done', 'Done')],
                             default='new', track_visibility='onchange')
```

Key 12-era rules:
- Tracking attribute is **`track_visibility='onchange'`** (or `'always'`),
  NOT `tracking=True`. `tracking=True` is the v13+ spelling.
- `mail.thread` gives `message_ids`, `message_follower_ids`,
  `message_channel_ids` (channels are first-class followers in 12 —
  removed later).
- `mail.activity.mixin` gives `activity_ids` + `activity_schedule()`.

## `message_post()` — 12 signature (positional, `@api.multi`)

```python
@api.multi
@api.returns('mail.message', lambda value: value.id)
def message_post(self, body='', subject=None,
                 message_type='notification', subtype=None,
                 parent_id=False, attachments=None,
                 notif_layout=False, add_sign=True, model_description=False,
                 mail_auto_delete=True, **kwargs):
```

12-specific facts:
- Decorated **`@api.multi`** (recordset iteration is opt-in in 12).
- Subtype passed as **`subtype=`** — an xml_id string OR a record. There
  is **no** `subtype_xmlid=` / `subtype_id=` keyword split (that arrives
  in 17). Internally `subtype` is resolved via `self.env.ref(subtype)`.
- Notification template arg is **`notif_layout=`** (renamed to
  `email_layout_xmlid=` by 17).
- `body` is a plain str (no `Markup`; the Markup-aware path is 14+).

```python
# 12 — post a visible comment
self.message_post(body=_("Đã giao việc"), subtype='mail.mt_comment')

# 12 — log an internal note (no follower notification), shortcut method
self._message_log(body=_("Audit entry"), message_type='notification')
```

## `_message_log()` — audit shortcut (no notify); NO batch variant

```python
def _message_log(self, body='', subject=False, message_type='notification', **kwargs):
```

- `_message_log` exists in 12 (single record, sudo, skips notification).
- **`_message_log_batch` does NOT exist in 12** — it lands in 15. To
  audit on batch create you must loop `_message_log` per record (only
  when audit is genuinely required) or rely on `track_visibility`.

## `message_subscribe()` — channels are followers in 12

```python
def message_subscribe(self, partner_ids=None, channel_ids=None, subtype_ids=None):
```

- Takes **`channel_ids=`** alongside `partner_ids=` — channels follow
  records in 12. That param is **dropped in 17** (followers become
  partner-only). Migrating 12→17: strip `channel_ids` from every
  `message_subscribe()` call.

## `_message_post_after_hook()` — official after-hook (param `msg_vals`)

```python
def _message_post_after_hook(self, message, msg_vals,
                             model_description=False, mail_auto_delete=True):
```

- Second arg is named **`msg_vals`** in 12 (renamed `msg_values` in 17 —
  positional, so callers are unaffected, but `super()` overrides that
  use the kwarg name must update).
- Runs only after a successful post — put external side effects here, not
  in a `message_post()` super-override.

## Tracking subtype resolution

```python
def _track_subtype(self, init_values):
    # return an xml_id (str) picking which subtype fires for a field change
    self.ensure_one()
    if 'state' in init_values and self.state == 'done':
        return 'my_module.mt_complaint_done'
    return super()._track_subtype(init_values)

def _track_template(self, tracking):
    return super()._track_template(tracking)
```

Both `_track_subtype(init_values)` and `_track_template(tracking)` exist
in 12 — the tracking → subtype mapping API is stable from 12 onward.

## Mail templates (`mail.template`)

```xml
<record id="email_template_complaint" model="mail.template">
    <field name="name">Complaint: Acknowledgement</field>
    <field name="model_id" ref="model_my_customer_complaint"/>
    <field name="subject">Re: ${object.name}</field>            <!-- 12: ${} qweb-legacy -->
    <field name="body_html" type="html"><![CDATA[<p>Hello ${object.partner_id.name}</p>]]></field>
</record>
```

- 12 templates use **`${...}` / `%if`** legacy placeholders (jinja-like).
  The switch to **`{{ }}` inline + qweb `body_html`** comes in 16. Do not
  port 12 `${}` syntax forward without converting.

## Chatter widget — jQuery `web.Widget` (NO OWL)

```javascript
odoo.define('mail.Chatter', function (require) {
"use strict";
var Widget = require('web.Widget');
var Chatter = Widget.extend({ /* ... */ });
});
```

- 12 chatter lives at `mail/static/src/js/chatter.js` as a classic
  `web.Widget`. **OWL does not exist in 12.** No `store_service.js`, no
  OWL `Component`.

Form-view chatter tag in 12:

```xml
<div class="oe_chatter">
    <field name="message_follower_ids" widget="mail_followers"/>
    <field name="activity_ids" widget="mail_activity"/>
    <field name="message_ids" widget="mail_thread"/>
</div>
```

## Hard rules (Odoo 12 mail specific)

- `track_visibility='onchange'` — NOT `tracking=True` (that's 13+).
- `message_post(..., subtype='mail.mt_comment')` — single `subtype=`
  kwarg; no `subtype_xmlid`/`subtype_id` split.
- Notification layout kwarg is `notif_layout=` (→ `email_layout_xmlid` in 17).
- `message_subscribe(partner_ids=, channel_ids=, subtype_ids=)` — channels
  are followers in 12.
- No `_message_log_batch` — loop `_message_log` or use tracking instead.
- `message_post` is `@api.multi`; after-hook arg is `msg_vals`.
- Chatter is jQuery `web.Widget`; no OWL/store in 12.
