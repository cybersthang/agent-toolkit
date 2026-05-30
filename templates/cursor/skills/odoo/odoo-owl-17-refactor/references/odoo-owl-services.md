# Odoo 17 `useService(...)` — service signatures (depth reference)

Companion to `SKILL.md` §2/§4. Verify method names against the `17.0`
branch (`addons/web/static/src/core/`) before review — services gain
methods per minor. All examples use placeholder names.

## The hook

```javascript
/** @odoo-module **/
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

export class MyComp extends Component {
    setup() {
        // MUST be called inside setup() — capture to `this` for later use.
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
    }
    onClick() {
        // useService("orm") HERE would throw — hooks are setup-only.
        this.action.doAction("my_action_xmlid");
    }
}
```

`useService(name)` looks the requested service up by key in
`registry.category("services")` and returns its started value. Calling
it outside `setup()` raises a hook-context error.

## `orm` — model CRUD (verified `orm_service.js`)

The default way to talk to models. Replaces legacy `web.rpc` /
`this._rpc`. Every method returns a Promise.

```javascript
this.orm = useService("orm");

// read specific records by id
await this.orm.read("res.partner", [1, 2], ["name", "email"]);

// search + read in one round-trip — kwargs is an OPTIONS OBJECT (v17)
await this.orm.searchRead(
    "res.partner", [["is_company", "=", true]], ["name"],
    { limit: 80, offset: 0, order: "name asc" },
);

// arbitrary model method
await this.orm.call("res.partner", "action_archive", [[1, 2]], {});

// write / create / unlink
await this.orm.write("res.partner", [1], { name: "X" });
const id = await this.orm.create("res.partner", [{ name: "New" }]);
await this.orm.unlink("res.partner", [id]);
```

Verified method set: `read`, `search`, `searchRead`, `webSearchRead`,
`call`, `write`, `create`, `unlink`. The 4th `searchRead` arg is
`kwargs = {}` (options object) — NOT positional `limit, offset, order`
as in v16. Positional code is silently misparsed and returns all rows.

## `action` — execute window/server actions (verified)

Replaces the removed `this.do_action(...)` shim. Method is **camelCase**
`doAction` and returns a Promise.

```javascript
this.action = useService("action");

// by xmlid
await this.action.doAction("sale.action_orders");

// by inline descriptor
await this.action.doAction({
    type: "ir.actions.act_window",
    res_model: "sale.order",
    views: [[false, "list"], [false, "form"]],
});

// open a specific record form
await this.action.doAction({
    type: "ir.actions.act_window",
    res_model: "sale.order",
    res_id: orderId,
    views: [[false, "form"]],
});
```

Other methods seen on the action service: `doActionButton`,
`switchView`, `restore`, `loadState`. `this.do_action(...)` (snake_case,
inherited) is gone in v17 — calling it raises `TypeError: this.do_action
is not a function`.

## `rpc` — low-level controller calls (verified, services doc)

For custom HTTP/JSON controller routes only. The services doc states the
`rpc` service is low-level and "should only be used to interact with
Odoo controllers... to work with models one should use the `orm`
service instead."

```javascript
this.rpc = useService("rpc");
await this.rpc("/my_module/compute", { product_id: 42 });
```

Outside a component (registry-time setup, plain util modules) use the
**standalone** import instead — it is not a hook:

```javascript
import { rpc } from "@web/core/network/rpc";
const data = await rpc("/my_module/bootstrap", { token: "xyz" });
```

## `notification` + `dialog` — user feedback (verified, services doc)

```javascript
this.notification = useService("notification");
this.notification.add("Saved", { type: "success" });   // info|success|warning|danger
const close = this.notification.add("Working…", { sticky: true });
// later: close();

this.dialog = useService("dialog");
this.dialog.add(ConfirmationDialog, {
    body: "Delete this record?",
    confirm: () => this.doDelete(),
    cancel: () => {},
});
```

## Other commonly-used services

| Key | Returns / use |
|---|---|
| `user` | current user info (`userId`, `context`, `hasGroup(group)`) |
| `router` | browser URL state (`pushState`, `current`) |
| `title` | window title (`setParts({ action: "…" })`) |
| `cookie` | read/modify cookies |
| `effect` | rainbow-man / graphical effects |
| `http` | low-level `GET`/`POST` outside the RPC stack |

Confirmed in odoo.com/documentation/17.0 services reference:
`cookie`, `effect`, `http`, `notification`, `router`, `rpc`,
`scroller`, `title`, `user` (the formally-documented list). `orm`,
`action`, `dialog` are core services living in the same `services`
registry category but documented elsewhere / referenced from the rpc
service note ("use the `orm` service instead").

## v16 → v17 service migration cheats

| v16 | v17 |
|---|---|
| `this._rpc({ model, method, args })` | `this.orm.call(model, method, args, kwargs)` |
| `import rpc from "web.rpc"` | `useService("orm")` or standalone `rpc` import |
| `this.do_action(act)` | `this.action.doAction(act)` |
| `searchRead(m, d, f, 80, 0, "name")` | `searchRead(m, d, f, { limit: 80, order: "name" })` |
| `this.do_notify(title, msg)` | `this.notification.add(msg, { title })` |

## Sources (verified 2026-05)

- `useService` import path + setup-only rule + service list:
  odoo.com/documentation/17.0/developer/reference/frontend/services.html.
- Services registered under `registry.category("services")`;
  `registry` from `@web/core/registry`:
  odoo.com/documentation/17.0 registries reference.
- ORM method set + `searchRead(model, domain, fields, kwargs = {})`:
  raw source `odoo/odoo@17.0/addons/web/static/src/core/orm_service.js`.
- `action.doAction` (camelCase) + removal of `this.do_action`:
  odoo.com/documentation/17.0 + Odoo 16→17 migration writeups.
