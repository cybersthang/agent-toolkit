---
name: odoo-owl-17-refactor
description: Odoo 17 OWL framework BREAK — removed `LegacyComponent` + `WidgetRegistry`, mandatory class-based `Component`, new `useService('orm'|'action'|'rpc')` hooks with v15/16-incompatible signatures, relocated view JS (controller/renderer/view triad), stricter `t-inherit`. Distinct from `odoo-owl-components` (generic OWL 2.x patterns). Version-aware: Step 0 reads `__manifest__.py`; applies when major ≥ 17. For 14-16 (older OWL v1/v2-early), defer to `odoo-owl-components`. Open whenever the user says "owl", "owl v17", "owl refactor", "Component", "LegacyComponent", "useService", "do_action", "v17 owl", "static/src", "renderer", "controller", or when editing `static/src/**/*.js` / `static/src/**/*.xml` on a v17+ codebase.
license: MIT
---

# Odoo 17+ OWL Refactor — migration delta

Odoo 17 landed a hard break in the frontend framework. v16 code with
deprecation warnings simply **does not load** on 17 — wrong import
paths fail silently (component never registers), `do_action` becomes
undefined, `LegacyComponent` no longer exists in the bundle.

This skill enumerates the 5 anti-patterns every consultancy hits when
migrating an addon to 17 (or reviewing a v17+ branch authored with
v15/16 muscle memory), each with a falsification recipe and
`must_keep_regex` / `forbid_regex` invariant suggestion.

> Distinct from `odoo-owl-components` (generic OWL 2.x: lifecycle,
> `useState`, props-down/events-up, `t-on`). Always call
> `odoo-owl-components` first for OWL questions; reach for this skill
> only when version is ≥ 17 and symptoms are import errors, missing
> `LegacyComponent`, or `do_action` breaks.

Pair with `odoo-code-review` (severity anchors) and `odoo-codebase-discovery`
(locate `static/src/` + read manifest).

## 0. Version detection (MANDATORY first step)

1. **`__manifest__.py` `version`** — `codebase.read_manifest({module_path})`.
   Pattern `^(\d+)\.0\.`.
2. **Fallback signals** (only if manifest missing):
   - `web.legacy.LegacyComponent` import → ≤ 16 (a finding only on v17+).
   - Three-file view layout (`*_controller.js` + `*_renderer.js` + `*_view.js`
     registered via `registry.category("views")`) → ≥ 17.
   - `import { rpc } from "@web/core/network/rpc"` (standalone, not via
     `useService`) → ≥ 17.
3. **Ask the user** only if signals are inconclusive.

| Detected major | Skill to use |
|---|---|
| 12 / 13 | OWL absent → `odoo-code-patterns` (jQuery widgets) |
| 14 / 15 / 16 | `odoo-owl-components` (OWL 2.x) — this skill out of scope |
| 17 | **this skill** + `odoo-owl-components` for generic patterns |
| 18 / 19 / 20 | this skill + flag MEDIUM (`useService` stable 17→20; re-check release notes per major) |

Falsify a v17 finding by re-reading `__manifest__.py` — if declared
version is `16.0.x`, `LegacyComponent` import is legal on that branch.

## 1. Pattern A — Importing from removed `web.legacy.*` paths

**Confidence: H**

v17 deleted the `web.legacy.*` namespace + `web/static/src/legacy/`.
Imports that resolved on 16 **silently fail at bundle time** — the
component never registers, the view stays blank, no Python traceback.
Common breaks: `web.legacy.LegacyComponent`, `web.legacy.WidgetRegistry`,
`web.utils.legacy`, `web.AbstractAction`, `web.AbstractController`.

```javascript
// BAD — v15/16; on v17 module never registers
import LegacyComponent from "web.legacy.LegacyComponent";
import WidgetRegistry from "web.legacy.WidgetRegistry";
export class MyDashboard extends LegacyComponent { /* ... */ }
WidgetRegistry.add("my_dashboard", MyDashboard);
// GOOD — v17: pure Component + new registry category
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
export class MyDashboard extends Component {
    static template = "my_module.MyDashboard";
}
registry.category("actions").add("my_dashboard", MyDashboard);
```

**Falsify.** `grep -rn "web\.legacy\." static/src/` on v17+ — any hit
is a finding. DevTools Console at page load shows `[ERROR]
OdooFrontend missing dependency`; the asset bundle loads anyway so the
failure is **per-module** and easy to miss. Removing the legacy import
+ switching to `Component` makes the error vanish.

**Invariant.**
```json
{
  "id": "owl-v17-no-legacy-imports",
  "applies_to": ["**/static/src/**/*.js"],
  "rules": { "forbid_regex": [
      "from\\s+[\"']web\\.legacy\\.",
      "from\\s+[\"']web\\.utils\\.legacy",
      "from\\s+[\"']web\\.AbstractAction[\"']",
      "from\\s+[\"']web\\.AbstractController[\"']"
  ]},
  "severity": "blocker",
  "rationale": "Symbols removed in v17 — import fails silently. See SKILL §1."
}
```

## 2. Pattern B — `this.do_action(...)` instead of `useService('action').doAction(...)`

**Confidence: H**

v15/16 OWL components inherited `do_action` via the `LegacyComponent`
shim. v17 removed it — canonical API is `useService("action")` returning
an object with a `doAction` method (camelCase, returns a Promise). Calls
to `this.do_action(...)` raise `TypeError: this.do_action is not a function`.

```javascript
// BAD — inherited helper; undefined in v17
export class MyButton extends Component {
    onClick() {
        this.do_action({ type: "ir.actions.act_window", res_model: "sale.order" });
    }
}
// GOOD — explicit action service hook
import { useService } from "@web/core/utils/hooks";
export class MyButton extends Component {
    setup() { this.action = useService("action"); }
    onClick() {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "sale.order" });
    }
}
```

**Falsify.** `grep -rn "\.do_action(" static/src/` on v17+ — any hit is
a finding. Clicking the offending button shows `TypeError:
this.do_action is not a function` in DevTools.

**Invariant.**
```json
{
  "id": "owl-v17-no-do-action-helper",
  "applies_to": ["**/static/src/**/*.js"],
  "rules": { "forbid_regex": [
      "this\\.do_action\\s*\\(",
      "this\\.trigger\\s*\\(\\s*[\"']do[-_]action[\"']"
  ]},
  "severity": "blocker",
  "rationale": "do_action helper removed in v17. See SKILL §2."
}
```

## 3. Pattern C — Subclassing `Widget` (jQuery legacy) instead of `Component`

**Confidence: H**

Pre-OWL Odoo (v12-15) used `web.Widget` — jQuery-based with `start()`,
`_render()`, `this.$el`. v17 removed `Widget` from the backend view
layer entirely (only `point_of_sale` still ships it, scheduled for
removal in v18). Symptoms: `Cannot read properties of undefined
(reading '$el')`, `start()` never called, widget area blank.

```javascript
// BAD — v15 jQuery Widget; broken on v17 backend
import Widget from "web.Widget";
import core from "web.core";
const MyWidget = Widget.extend({
    template: "my_module.MyWidget",
    events: { "click .o_btn": "_onClick" },
    start() { this._super(...arguments); this.$el.find(".o_btn").addClass("o_hl"); },
});
core.action_registry.add("my_widget", MyWidget);
// GOOD — pure OWL Component
import { Component, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
export class MyWidget extends Component {
    static template = "my_module.MyWidget";
    setup() {
        this.btnRef = useRef("btn");
        onMounted(() => this.btnRef.el?.classList.add("o_hl"));
    }
    onClick(ev) { /* ... */ }
}
registry.category("actions").add("my_widget", MyWidget);
```

Template change: `events: { "click .o_btn": "..." }` → `<button t-ref="btn" t-on-click="onClick">`.

**Falsify.** `grep -rn 'Widget\.extend\|from "web.Widget"\|from "web.core"' static/src/`
— any hit on a v17+ backend module (excluding `point_of_sale/`) is a
finding. Route renders blank; console may show `_super is not a
function` or stay silent depending on compile-time catching.

**Invariant.**
```json
{
  "id": "owl-v17-no-jquery-widget",
  "applies_to": ["**/static/src/**/*.js"],
  "exclude": ["**/point_of_sale/**"],
  "rules": { "forbid_regex": [
      "from\\s+[\"']web\\.Widget[\"']",
      "Widget\\.extend\\s*\\("
  ]},
  "severity": "blocker",
  "rationale": "Widget removed from v17 backend. See SKILL §3."
}
```

## 4. Pattern D — Direct `rpc` import instead of `useService('orm'|'rpc')`

**Confidence: H**

v15/16 RPC: `import rpc from "web.rpc"` (legacy) or `useService("rpc")`
(modern). v17 deleted `web.rpc` and split RPC into three paths:

- `useService("orm")` — typed CRUD helpers (`read`, `searchRead`, `call`).
- `useService("rpc")` — raw `/web/dataset/call_kw` POST.
- `import { rpc } from "@web/core/network/rpc"` — **standalone**,
  usable outside components (utility modules, registry-time setup). New in 17.

Worse: ORM signature changed.
v16: `orm.searchRead(model, domain, fields, limit, offset, order)` positional.
v17: `orm.searchRead(model, domain, fields, { limit, offset, order })` options object.
Old positional 4th arg is **silently ignored** — returns all records.

```javascript
// BAD — legacy web.rpc + positional limit (silently dropped on v17)
import rpc from "web.rpc";
await rpc.query({ model: "res.partner", method: "search_read",
                  args: [[["is_company","=",true]], ["name"]] });
await this.orm.searchRead("res.partner", domain, ["name"], 80, 0, "name asc");
// GOOD — ORM service for CRUD; standalone rpc for /custom routes
import { useService } from "@web/core/utils/hooks";
export class MyList extends Component {
    setup() { this.orm = useService("orm"); }
    async load() {
        this.records = await this.orm.searchRead(
            "res.partner", [["is_company","=",true]], ["name"],
            { limit: 80, order: "name asc" },
        );
    }
}
// Outside a component:
import { rpc } from "@web/core/network/rpc";
async function bootstrap() { return await rpc("/my_module/bootstrap", { token: "xyz" }); }
```

Typed model methods: `this.orm.call("res.partner", "my_method", [ids], {kwargs})`.

**Falsify.** (1) `grep -rn 'from "web\.rpc"' static/src/` → any hit
fails with `Module "web.rpc" not found` at bundle time. (2)
`grep -rnP 'searchRead\([^,]+,[^,]+,[^,]+,\s*\d+' static/src/` → positional
limit on v17 means silent return of all rows.

**Invariant.**
```json
{
  "id": "owl-v17-no-legacy-rpc-import",
  "applies_to": ["**/static/src/**/*.js"],
  "rules": { "forbid_regex": [
      "from\\s+[\"']web\\.rpc[\"']",
      "require\\(\\s*[\"']web\\.rpc[\"']"
  ]},
  "severity": "blocker",
  "rationale": "web.rpc removed in v17. See SKILL §4."
}
```

## 5. Pattern E — `t-name` clashes under stricter v17 template inheritance

**Confidence: M**

v17 tightened template inheritance. In v16, re-declaring with the same
`t-name` as a core template silently won "last loaded". v17 raises
`OwlError: Template <name> already defined` at bundle **compile time**.
Fix: mandatory `t-inherit="<original_id>" t-inherit-mode="extension"
owl="1"` + a **distinct new `t-name`**.

```xml
<!-- BAD — v16-style redeclare; v17 throws at compile -->
<t t-name="web.ListController.SearchBarButton" owl="1">
    <button class="o_my_extra_btn">Extra</button>
</t>
<!-- GOOD — distinct t-name + t-inherit + xpath patch -->
<t t-name="my_module.ListController.SearchBarButton.Extra"
   t-inherit="web.ListController.SearchBarButton"
   t-inherit-mode="extension" owl="1">
    <xpath expr="//div[hasclass('o_search_bar_buttons')]" position="inside">
        <button class="o_my_extra_btn" t-on-click="onExtra">Extra</button>
    </xpath>
</t>
```

JS companion — `patch()` on the controller's prototype. v17 dropped the
2nd `name` arg: v16 `patch(target, name, ext)` → v17 `patch(target,
ext)`. Old 3-arg calls **silently no-op** (M-severity finding on its own).

```javascript
import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
patch(ListController.prototype, {
    setup() { super.setup(); /* additional */ },
    onExtra() { /* ... */ },
});
```

**Falsify.** Boot in dev with `--dev=assets`. Console at page load:
`OwlError: Template <name> has already been registered` aborts compile
of the affected bundle — the entire downstream view stays blank, not
just your component. Adding `t-inherit` + new `t-name` makes it vanish.

**Invariant.**
```json
{
  "id": "owl-v17-template-inheritance-strict",
  "applies_to": ["**/static/src/**/*.xml"],
  "rules": { "must_keep_regex": [
      "t-inherit=\"[^\"]+\"\\s+t-inherit-mode=\"extension\"\\s+owl=\"1\""
  ]},
  "severity": "warn",
  "rationale": "v17 raises OwlError on duplicate t-name without t-inherit. See SKILL §5. Fix-shape regex; full enforcement needs sibling check against core template registry."
}
```

## 6. View JS file layout — controller / renderer / view triad

v17 standardized backend views into **three files**:

| File | Responsibility |
|---|---|
| `<view>_view.js` | Descriptor `{ type, display_name, Controller, Renderer, ArchParser }`, registered via `registry.category("views").add(name, descriptor)` |
| `<view>_controller.js` | State + event handlers (extends `Controller`) |
| `<view>_renderer.js` | Pure render logic (extends `Renderer`) |

Monolithic v16-style files still load but **bypass the new patching
surface** — extension modules can't `patch(Renderer.prototype, ...)`
if the renderer isn't a separate exported class. Split before patching.

## 7. Migration strategy — v16 → v17 (don't big-bang)

The break is too large for a single-PR rewrite. Phase it:

1. **Wrap legacy first.** Mount `Widget`-based code via the v16→v17
   wrapper (officially supported in 17.0 LTS for one major). Confirm
   addon installs + boots with zero refactor.
2. **Patch services.** Migrate `do_action` / `rpc` / `orm` to
   `useService(...)` — mechanical 1:1 per file. Batches of 5-10 files/PR.
3. **Split views.** Extract `_controller.js` + `_renderer.js` from each
   monolithic view file. Highest-risk phase — gate with realdata_test probes.
4. **Drop the wrapper.** Once every component extends `Component`
   directly, remove the legacy wrapper. No-going-back step — schedule
   after a full QA pass on v17 staging.
5. **Tighten templates.** Add `t-inherit-mode="extension"` everywhere;
   rename clashing `t-name` ids.

Do NOT attempt steps 2-5 in a single PR.

## 8. Code-review severity anchors (`static/src/**/*.{js,xml}`)

| Finding | Severity | Why |
|---|---|---|
| `web.legacy.*` / `web.utils.legacy` import | **H** (blocker) | Silent per-module bundle failure |
| `this.do_action(` call | **H** (blocker) | TypeError on click; no fallback |
| `Widget.extend(` in backend module | **H** (blocker) | Widget removed from v17 backend |
| `from "web.rpc"` | **H** (blocker) | Module not found at bundle time |
| Positional `searchRead(m, d, f, N, ...)` | **M** | Silently ignored — wrong page |
| `patch(target, name, ext)` 3-arg form | **M** | Silently no-ops — patch never applies |
| Same `t-name` as core without `t-inherit` | **H** | Aborts bundle compile |
| Monolithic view file (no triad split) | **L** | Loads but blocks downstream patching |
| `super.setup()` missing inside `patch()` | **H** | Breaks original behavior silently |

## 9. References (skill-local)

| File | What it contains |
|---|---|
| `references/odoo-17-owl-refactor.md` | Full changelog of removed symbols + new APIs — paste from Odoo 17 release notes on first use |
| `references/odoo-owl-services.md` | Signatures for every `useService(...)` hook in v17 + how each changed from v16 |

(NOT auto-populated — write on first use from `odoo/odoo` `17.0` branch
docs. Treat pattern claims as structurally correct but verify exact
signatures against live release notes before code review.)

## 10. Cross-references + sibling skills

| Concern | Skill |
|---|---|
| Generic OWL 2.x patterns (lifecycle, `useState`, props, `t-on`) | `odoo-owl-components` — CALL FIRST |
| Severity anchors generally | `odoo-code-review` §D |
| Locate `static/src/` + read manifest | `odoo-codebase-discovery` |
| Realdata browser-driven probes | `odoo-data-verification` |
| Project-specific migration decisions | `odoo-deterministic-answers` (`lookup_canonical_decision`) |

## 11. Hard rules summary

- Never import from `web.legacy.*` / `web.utils.legacy` /
  `web.AbstractAction` / `web.AbstractController` / `web.rpc` on v17+.
- Never call `this.do_action(...)` — use `useService("action").doAction(...)`.
- Never subclass `Widget` in a v17 backend module — extend `Component`.
- Never re-declare a core template's `t-name` without `t-inherit` +
  `t-inherit-mode="extension"` + a distinct new `t-name`.
- Never use 3-arg `patch(target, name, ext)` on v17 — drop the `name`.
- Never put controller + renderer + view descriptor in one file when
  extension modules need to patch them — split into the triad.
- Never big-bang a v16 → v17 migration in one PR — phase services →
  views → templates.
