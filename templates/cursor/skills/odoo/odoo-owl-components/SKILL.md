---
name: odoo-owl-components
description: OWL reactive component patterns for Odoo 14+ — lifecycle (setup vs onMounted), reactive state (useState vs ref), props-down/events-up, t-on binding, template inheritance. Falsification recipes per pattern. Skill is version-aware: OWL v1 (14-15) coexists with jQuery/QWeb; OWL v2 mature 16+; v17 introduced a deeper refactor (see sibling `odoo-owl-17-refactor` skill). OWL does NOT exist in Odoo 12/13 — code-review must flag those codebases out of scope. Open when user says "OWL", "owl component", "useState", "useEffect", "onMounted", or when editing a `.js` file with `/** @odoo-module **/` header.
---

# Odoo — OWL component patterns (v14+ ; OWL v2 default 16+)

OWL is Odoo's reactive frontend. Timeline:

- **Odoo 12, 13** — no OWL. jQuery + QWeb only. This skill exits.
- **Odoo 14** — OWL v1 INTRODUCED; coexists with jQuery/QWeb widgets.
  Pick the framework matching the existing widget before patching;
  don't mix.
- **Odoo 15** — broader OWL adoption + legacy kanban JS removed. Still
  mixed (some QWeb/jQuery widgets remain). New components prefer OWL.
- **Odoo 16** — OWL v2 mature; web client mostly OWL. Patterns below
  are stable from here on.
- **Odoo 17+** — additional refactor (removed `LegacyComponent`,
  `do_action` → `actionService`, controller/renderer/view split, etc.).
  For v17+ specifics see sibling skill `odoo-owl-17-refactor`.

Module-agnostic. Confidence: **H** stable across OWL 2.x (16+); **M**
when on 14/15 (OWL v1 — some lifecycle hooks named differently); v17+
adds new APIs — cross-check `odoo-owl-17-refactor` before patching.

## 0. Version detection (MANDATORY)

Read `__manifest__.py` via `codebase.read_manifest`. Behaviour by major:

| Major | Action |
|---|---|
| 12, 13 | STOP — OWL not present. Use `odoo-code-patterns/references/odoo-12-patterns.md` (jQuery widgets). |
| 14, 15 | OWL v1 — apply patterns below; flag MEDIUM since some APIs (e.g. `mounted()` instead of `onMounted()`) differ. Check which framework the target widget uses before patching. |
| 16     | OWL v2 mature — apply patterns below directly. |
| 17, 18, 19, 20 | OWL v2 + v17 refactor. Apply patterns below AND consult `odoo-owl-17-refactor` for removed-symbol checks. |

Signal for "OWL in scope?": grep for `/** @odoo-module **/` in any
`static/src/**/*.js`.

| Topic | Reference |
|---|---|
| Lifecycle hooks + race conditions | `references/owl-lifecycle.md` |
| `useState` / `reactive` / `useEffect` | `references/owl-state-management.md` |

## 1. Pattern A — `setup()` vs `onMounted()` race (H)

**Problem.** `setup()` runs before the DOM exists. Reading `this.el` /
`ref.el` returns `undefined`. Use `onMounted(callback)` for
DOM-dependent work — registered in `setup()`, called after first render.

```javascript
// BAD — canvasRef.el is null inside setup(); no DOM yet
import { Component, useRef } from "@odoo/owl";
export class MyChart extends Component {
    setup() {
        this.canvasRef = useRef("canvas");
        this.chart = new Chart(this.canvasRef.el, this.chartConfig);  // crashes
    }
}
// GOOD — defer DOM work to onMounted; pair with onWillUnmount cleanup
import { Component, useRef, onMounted, onWillUnmount } from "@odoo/owl";
export class MyChart extends Component {
    setup() {
        this.canvasRef = useRef("canvas");
        onMounted(() => { this.chart = new Chart(this.canvasRef.el, this.chartConfig); });
        onWillUnmount(() => { this.chart?.destroy(); });
    }
}
```

**Falsify.** Add `console.log(this.canvasRef.el)` inside `setup()` AND
inside `onMounted(() => {...})`. First prints `null`; second prints
`HTMLCanvasElement`. If both print `null` → ref name doesn't match
template `t-ref`. If both print the element → OWL lifecycle changed in
your version (`<see OWL release notes>`).

## 2. Pattern B — Reactive state: `useState` vs `useRef` (H)

**Problem.** `useState(obj)` returns a Proxy — mutations re-render.
`useRef("name")` returns a DOM handle, NOT reactive. Newcomers from
Vue 3 confuse Vue's `ref()` (reactive) with OWL's `useRef()` (DOM only).
Bonus pitfall: replacing a property with a raw object then keeping a
separate reference bypasses the proxy.

```javascript
// BAD — useRef is not reactive; assigning unwrapped object loses proxy
import { Component, useState, useRef } from "@odoo/owl";
export class Counter extends Component {
    setup() {
        this.countRef = useRef("count");      // not reactive
        this.state = useState({ user: null });
        this.loadUser().then((u) => {
            this.state.user = u;               // u is not a Proxy
            this.state.user.name = "X";        // does NOT re-render
        });
    }
    increment() { this.countRef.value = (this.countRef.value || 0) + 1; }
}
// GOOD — state for data, spread when assigning objects
export class Counter extends Component {
    setup() { this.state = useState({ count: 0, user: null }); }
    increment() { this.state.count++; }
    async loadUser() {
        const u = await this.fetchUser();
        this.state.user = { ...u };            // spread → proxy wraps → re-renders
        this.state.user.name = "X";
    }
}
```
Rule: `useState` = data; `useRef` = DOM handle. Never mix.

**Falsify.** Bind `<t t-esc="state.user.name"/>`. Run
`state.user = rawObj` (no spread) then `state.user.name = "Changed"` —
DOM does NOT update. Replace with `state.user = { ...rawObj }` — DOM
updates. Confirms the proxy-wrap rule.

## 3. Pattern C — Sub-component comms: props down, events up (H)

**Problem.** OWL is uni-directional: parents pass `props`; children
notify via callback-props (not custom DOM events). Anti-patterns: child
mutates a prop (silently ignored in prod, throws in dev), or teams use a
global bus that hides data flow.

```javascript
// BAD — child mutates a prop
export class CounterChild extends Component {
    static props = ["count"];
    increment() { this.props.count++; }   // throws in dev, silent in prod
}
// GOOD — callback prop
export class CounterChild extends Component {
    static props = { count: Number, onIncrement: Function };
    increment() { this.props.onIncrement(this.props.count + 1); }
}
export class CounterParent extends Component {
    static components = { CounterChild };
    setup() { this.state = useState({ count: 0 }); }
    handleIncrement(newCount) { this.state.count = newCount; }
}
```
Parent template: `<CounterChild count="state.count" onIncrement.bind="handleIncrement"/>` —
`.bind` keeps `this` pointing to the parent.

**Falsify.** Enable OWL dev mode (`window.__OWL_DEVTOOLS__ = true`). In
the child write `this.props.count++` and click. Dev mode raises
`Cannot assign to read only property 'count'`. If no error → OWL in
production mode; diff parent's `state.count` before/after to confirm
no update.

## 4. Pattern D — `t-on` event handling (H)

**Problem.** Three common typos: (1) `t-on-onclick` instead of
`t-on-click` (silently ignored); (2) `t-on-click="handler()"` calls at
render time, not on click; (3) forgetting `.bind` on a prop callback.

```xml
<!-- BAD -->
<button t-on-onclick="increment">+</button>     <!-- typo: silently ignored -->
<button t-on-click="increment()">+</button>     <!-- runs at render time -->
<!-- GOOD -->
<button t-on-click="increment">+</button>
<button t-on-click="() => this.incrementBy(5)">+5</button>
<button t-on-click="props.onIncrement">+</button>   <!-- prop callback -->
```
Form events: `onSubmit(ev) { ev.preventDefault(); }` bound via
`<form t-on-submit="onSubmit">`.

**Falsify.** Replace `t-on-click="increment"` with `t-on-onclick="increment"`.
Reload, click — nothing happens, no error. Inspect rendered HTML — button
has NO `onclick` attribute. Confirms unknown `t-on-` directives are silently ignored.

## 5. Pattern E — Template inheritance (M)

`<see Odoo 17/18 template inheritance docs>` for `t-inherit-mode` deprecations.

**Problem.** Override another component's template via `<t t-inherit>` +
xpath. Anti-patterns: (1) re-declare the same template id without
`t-inherit` (last-loaded wins, shadows original + future updates);
(2) forget `t-inherit-mode="extension"` (replaces instead of patching).

**Bad:** redeclares same id, no inherit — loses original markup:
```xml
<t t-name="other_module.SomeComponent">
    <button t-on-click="myExtra">Extra</button>
</t>
```

**Good:** extension-mode inherit + xpath patch (new id ≠ source id):
```xml
<t t-name="my_module.SomeComponent"
   t-inherit="other_module.SomeComponent"
   t-inherit-mode="extension" owl="1">
    <xpath expr="//div[hasclass('o_main_actions')]" position="inside">
        <button t-on-click="myExtra">Extra</button>
    </xpath>
</t>
```

To extend JS behavior, use `patch()` from `@web/core/utils/patch`:
```javascript
patch(SomeComponent.prototype, {
    setup() { super.setup(); /* additional setup */ },
    myExtra() { /* new method */ },
});
```
`<see Odoo @web/core/utils/patch docs>` for return-value behavior in 17+.

**Falsify.** Copy the parent component's template id verbatim with no
`t-inherit` — original markup disappears, replaced by your fragment.
Add `t-inherit="..." t-inherit-mode="extension"` and change the new id;
reload — original markup preserved AND your patch appears. If step 2
still shows only your fragment → `t-inherit-mode` defaulted to `primary`;
force `extension` explicitly.

## Sibling skills

- `odoo-code-patterns` — generic patterns; for Odoo 12 use `references/odoo-12-patterns.md` (jQuery).
- `odoo-code-review` — finding gate.
- `odoo-tdd` — OWL test setup (`mountInFixture`, hoot runner in 17+).
- `odoo-performance` — reactive mutations (Pattern B) can cause re-render storms.
