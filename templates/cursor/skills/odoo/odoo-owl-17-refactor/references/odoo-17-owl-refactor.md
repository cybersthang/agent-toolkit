# Odoo 17 OWL refactor — removed-symbol changelog (depth reference)

Companion to `SKILL.md`. Verify exact signatures against the `17.0`
branch of `github.com/odoo/odoo` before a code review — paths drift
per minor. All examples use placeholder names.

OWL timeline (verified):
- **Odoo 14** — OWL **1** introduced; coexists with legacy jQuery widgets.
- **Odoo 15** — broader OWL 1 adoption; legacy still present.
- **Odoo 16** — OWL **2** (announced at Odoo Experience 2022) becomes
  the web-client default; legacy adapter still ships.
- **Odoo 17** — heavy OWL 2; legacy widget layer / `web.legacy.*`
  largely removed; view JS split into the controller/renderer/view triad.

## Canonical v17 module skeleton

Every backend JS file starts with the module pragma and imports OWL
primitives from `@odoo/owl`, framework helpers from `@web/...`:

```javascript
/** @odoo-module **/
import { Component, useState, onWillStart, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MyDashboard extends Component {
    static template = "my_module.MyDashboard";   // string id, NOT inline xml
    static props = {};
    static components = { /* child components */ };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ records: [], loading: true });
        onWillStart(async () => {
            this.state.records = await this.orm.searchRead(
                "res.partner", [["is_company", "=", true]], ["name"],
                { limit: 80, order: "name asc" },
            );
            this.state.loading = false;
        });
        onMounted(() => { /* DOM-dependent init */ });
    }
}
registry.category("actions").add("my_dashboard", MyDashboard);
```

`/** @odoo-module **/` is mandatory — without it the file is treated as
a raw script, the `import`/`export` statements are not transpiled, and
the bundle silently drops the module.

## Removed symbols + replacements (the migration delta)

| v15/16 symbol | v17 status | Replacement |
|---|---|---|
| `web.legacy.LegacyComponent` | removed | extend `Component` from `@odoo/owl` |
| `web.legacy.WidgetRegistry` | removed | `registry.category("...")` |
| `web.AbstractAction` | removed (backend) | `Component` + `registry.category("actions")` |
| `web.AbstractController` | removed (backend) | view triad `Controller` class |
| `web.Widget` (jQuery) | removed from backend views | `Component` (only `point_of_sale` still ships it) |
| `web.core` (`action_registry`, `bus`) | removed | `@web/core/registry`, `useService("bus_service")` |
| `web.rpc` | removed | `useService("orm")` / `useService("rpc")` / standalone `rpc` |
| `this.do_action(...)` (inherited shim) | removed | `useService("action").doAction(...)` |
| `mounted()` / `willStart()` class methods (OWL 1) | n/a in OWL 2 | `onMounted()` / `onWillStart()` hooks in `setup()` |

Most of these fail **silently per-module** at bundle time: the module
never registers, the view/route stays blank, and there is no Python
traceback. Only DevTools console at page load reveals the missing
dependency.

## The three RPC paths (verified — `addons/web/static/src/core`)

```javascript
// 1. ORM service — typed CRUD, the default for model work
this.orm = useService("orm");
await this.orm.searchRead("res.partner", domain, ["name"], { limit: 80 });
await this.orm.read("res.partner", [id], ["name", "email"]);
await this.orm.call("res.partner", "my_method", [ids], { kwargs });
await this.orm.write("res.partner", [id], { name: "X" });

// 2. rpc service — low-level controller calls inside a component
this.rpc = useService("rpc");
await this.rpc("/my_module/endpoint", { token: "xyz" });

// 3. standalone rpc — usable OUTSIDE a component (registry-time, utils)
import { rpc } from "@web/core/network/rpc";
async function bootstrap() { return await rpc("/my_module/bootstrap", {}); }
```

The `orm_service.js` source confirms `searchRead(model, domain, fields,
kwargs = {})` — the 4th arg is an **options object** (`{ limit, offset,
order }`), NOT positional `limit`. v16 positional code (`searchRead(m, d,
f, 80, 0, "name asc")`) is silently misread on v17 — the `80` lands in
`kwargs` as an integer and is ignored, returning all rows.

## `patch()` lost its name argument (verified — `utils/patch.js`)

```javascript
import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";

// v17: patch(objToPatch, extension) — TWO args only
patch(ListController.prototype, {
    setup() { super.setup(); /* extra */ },     // MUST call super
});
```

The v17 source signature is `export function patch(objToPatch,
extension)` and explicitly throws if the 2nd arg looks like a string:
`"Second argument is not the patch name anymore"`. v16 3-arg calls
`patch(target, "my.patch", ext)` therefore break loudly here (or
silently no-op on intermediate builds). Always call `super.<method>()`
inside an overridden method or you wipe the original behavior.

## Sanity-check grep set (run on a v17+ tree)

```bash
grep -rn 'web\.legacy\.'              static/src/   # removed namespace
grep -rn 'from "web\.\(Widget\|core\|rpc\)"' static/src/   # removed modules
grep -rn '\.do_action('               static/src/   # removed shim
grep -rnP 'searchRead\([^,]+,[^,]+,[^,]+,\s*\d+' static/src/   # positional limit
grep -rn 'patch([^,]+,\s*["'\'']'     static/src/   # 3-arg patch (name string)
```

Falsify any hit by re-reading `__manifest__.py`: if `version` declares
`16.0.x`, the legacy symbols are legal on that branch and these are NOT
findings.

## Sources (verified 2026-05)

- OWL introduced in 14 / OWL 2 default 16: odoo.com Owl docs +
  Odoo 14/16 release notes; OWL 2 announced Odoo Experience 2022.
- `@odoo-module` + `Component` + `static template` + `registry.category`:
  odoo.com/documentation/17.0 (frontend howtos + owl_components).
- `useService` from `@web/core/utils/hooks`; `registry` from
  `@web/core/registry`: odoo.com/documentation/17.0 services + registries.
- `searchRead(model, domain, fields, kwargs={})` and `patch(objToPatch,
  extension)`: raw source on `odoo/odoo@17.0`
  (`addons/web/static/src/core/orm_service.js`, `.../utils/patch.js`).
