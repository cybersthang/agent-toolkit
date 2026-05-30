# Odoo 12 — PRE-OWL frontend patterns (standalone)

Standalone reference: Odoo 12 has **no OWL**. The frontend is jQuery +
QWeb + the `web.Widget` class hierarchy, wired through the AMD-style
`odoo.define` module system. Load this when Step 0 detected major =
**12** (or 13 — same model) and the parent `odoo-owl-components` skill
exited "OWL not present". OWL arrives in **Odoo 14** (OWL 1).

When patching a v12 frontend, you are NOT writing components, hooks, or
`useState`. Match the legacy idioms below exactly — mixing OWL imports
(`@odoo/owl`, `@web/...`) into a v12 bundle fails: those module paths do
not exist before v14/15.

## Module system — `odoo.define`, not ES modules

```javascript
odoo.define('my_module.MyWidget', function (require) {
"use strict";

var Widget = require('web.Widget');
var core = require('web.core');
var _t = core._t;                       // translation helper

// ... define MyWidget ...

return MyWidget;
});
```

There is **no** `/** @odoo-module **/` pragma (that is a v14+ marker),
no `import`/`export`. Every dependency comes through `require('web.X')`;
every module returns its public value. The explicit-deps form
`odoo.define('name', ['web.Widget'], function (require) {...})` is also
valid.

## `web.Widget` — the jQuery component base

```javascript
var MyWidget = Widget.extend({
    template: 'my_module.MyWidget',     // QWeb template id (see below)
    events: {
        'click .o_btn': '_onClick',     // delegated jQuery events
        'change input.o_qty': '_onQtyChange',
    },
    init: function (parent, options) {
        this._super.apply(this, arguments);   // ALWAYS chain super
        this.value = options.value || 0;
    },
    willStart: function () {
        // async pre-render — return a Promise; render waits for it
        var self = this;
        return this._rpc({ route: '/my_module/data' }).then(function (res) {
            self.records = res;
        });
    },
    start: function () {
        // DOM exists here — this.$el is the rendered root
        this.$('.o_btn').addClass('o_highlight');
        return this._super.apply(this, arguments);
    },
    _onClick: function (ev) {
        ev.preventDefault();
        this.$('.o_total').text(this.value);
    },
});
```

Mental map to the OWL world (so v14+ migrators recognize it):

| v12 legacy | OWL 1 (14+) equivalent |
|---|---|
| `Widget.extend({...})` | `class extends Component` |
| `init(parent, opts)` | `setup()` (no parent arg — env is implicit) |
| `willStart()` | `onWillStart()` hook |
| `start()` | `onMounted()` hook |
| `destroy()` | `onWillUnmount()` hook |
| `events: { 'click .x': '_h' }` | `t-on-click` in template |
| `this.$el` / `this.$('.x')` | `useRef("x")` (no jQuery) |
| `this._super.apply(this, args)` | `super.method(...)` |

## DOM access — jQuery, always scoped

```javascript
this.$el            // jQuery-wrapped root element of the widget
this.$('.o_row')    // == this.$el.find('.o_row') — scoped query
this.el             // raw DOM node of the root
```

Never `$('.o_row')` globally — scope through `this.$(...)` so the
widget only touches its own subtree. Manual binds beyond the `events`
map use `.on()` and must be unbound or rely on `destroy()` removing
`$el`.

## QWeb templates — separate XML, `qweb` manifest key

Templates are plain QWeb in a static XML file, NOT inline:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="my_module.MyWidget">
        <div class="o_my_widget">
            <span t-esc="widget.value"/>
            <button class="o_btn">Go</button>
        </div>
    </t>
</templates>
```

Registered via the `qweb` key in `__manifest__.py` (this key is how v12
loads frontend templates — replaced by the `assets` bundle system in
v15+):

```python
'qweb': ['static/src/xml/my_widget.xml'],
```

Inside the template the widget instance is exposed as `widget` —
`t-esc="widget.value"`, `t-foreach="widget.records"`. QWeb directives
(`t-if`, `t-foreach`, `t-att-*`, `t-esc`, `t-raw`) only; there is **no**
`t-on-click` / `t-ref` / `t-model` here — those are OWL directives that
do not exist pre-14. DOM events are wired through the `events:` map.

## Client actions — `AbstractAction` + `action_registry`

A full-screen client action extends `web.AbstractAction` and registers
its tag:

```javascript
odoo.define('my_module.MyAction', function (require) {
"use strict";

var AbstractAction = require('web.AbstractAction');
var core = require('web.core');

var MyAction = AbstractAction.extend({
    template: 'my_module.MyAction',
    hasControlPanel: true,
    start: function () {
        return this._super.apply(this, arguments);
    },
});

core.action_registry.add('my_client_action', MyAction);
return MyAction;
});
```

Bound to an `ir.actions.client` record whose `tag` matches the
registry key:

```xml
<record id="action_my_client" model="ir.actions.client">
    <field name="name">My Dashboard</field>
    <field name="tag">my_client_action</field>
</record>
```

`AbstractAction` replaced the older `Widget`-based `client_action` of
Odoo ≤10; it is itself superseded by OWL `Component` +
`registry.category("actions")` from v14/17. Server-side RPC inside any
widget uses `this._rpc({ model, method, args })` — the legacy ancestor
of the v14+ `orm`/`rpc` services.

## Hard rules (Odoo 12 frontend)

- No OWL. No `import` from `@odoo/owl` or `@web/...` — those paths first
  appear in v14/15. Use `odoo.define` + `require('web.X')`.
- Always `this._super.apply(this, arguments)` in overridden `init` /
  `start` / `willStart` — forgetting it skips base setup.
- DOM only in `start()` / after render; `init()` has no rendered `$el`.
- Templates live in static XML loaded via the `qweb` manifest key; the
  widget is exposed as `widget` inside QWeb.
- Wire events through the `events: {}` map or `this.$('.x').on(...)`,
  never global `$(...)`.
- Client actions = `AbstractAction.extend` + `core.action_registry.add`
  + an `ir.actions.client` record whose `tag` matches.

## Sources (verified 2026-05)

- `odoo.define`, `Widget.extend` (`init`/`start`/`events`/`_super`/
  `this.$el`/`this.$()`), QWeb `<templates><t t-name>`, `qweb` manifest
  key: odoo.com/documentation/12.0 JavaScript reference.
- `web.AbstractAction` + `core.action_registry.add` + `ir.actions.client`
  `tag` binding: odoo.com/documentation/12.0 JavaScript reference
  (client-actions section).
- OWL introduced in Odoo 14 (absent in 12/13): odoo.com Owl docs +
  Odoo 14 release notes.
