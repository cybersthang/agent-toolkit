# OWL state management — depth reference

Companion to `SKILL.md` §2 (`useState` vs `ref`). All examples use
placeholder names — adapt via `codebase.search_text`.

## The three reactive primitives

| Primitive | Purpose | Returns |
|---|---|---|
| `useState(obj)` | Reactive component state | Proxy wrapping `obj` — mutations trigger re-render |
| `reactive(obj)` | Reactive object OUTSIDE a component (shared store) | Proxy; subscribe via `useState` reference |
| `useRef("name")` | DOM element handle | `{ el: HTMLElement \| null }` — NOT reactive |

Coming from other frameworks:
- Vue 3 `ref()` ≠ OWL `useRef()`. Vue's `ref` is a reactive primitive
  (closest OWL equivalent: `useState({value: ...})`).
- React `useState` returns `[value, setter]`; OWL `useState` returns a
  mutable Proxy. Mutate it directly: `state.count++`.

## How `useState` reactivity works

```javascript
const state = useState({ count: 0, items: [] });

state.count++;              // Proxy intercepts → re-render scheduled
state.items.push("a");      // Proxy intercepts on the nested array → re-render
state.items = ["a"];        // Replaces the array; new array is wrapped on assign → re-render
```

The proxy is **deep** — nested objects accessed via `state.x.y.z = v`
also re-render. But there are edge cases:

### Edge case 1 — replacing a property with an unwrapped object

```javascript
const raw = { name: "Anna" };
state.user = raw;
// raw is now wrapped (state.user IS a Proxy)
// BUT a separate `raw.name = "Bob"` does NOT re-render
// because `raw` was wrapped on assignment — the OUTER variable still
// points to the unwrapped object.
state.user.name = "Bob";    // re-renders (going through proxy)
raw.name = "Bob";           // does NOT re-render (bypassing proxy)
```

Rule: never keep a separate reference to a raw object after assigning
it to reactive state.

### Edge case 2 — primitive values can't be wrapped

```javascript
// state.count = 5 — OK, primitives are tracked via the parent proxy
// But you cannot do:
const myCount = state.count;   // captures the primitive value 5
state.count++;                  // re-renders the component
console.log(myCount);          // still 5 — primitives don't reference back
```

If you want a "live" reference to a primitive, wrap it:

```javascript
const state = useState({ counter: { value: 0 } });
const counterObj = state.counter;
state.counter.value++;
console.log(counterObj.value);  // 1 — counterObj IS the proxy
```

### Edge case 3 — `Map` / `Set` are NOT deeply reactive

OWL's proxy wraps plain objects and arrays. `Map` / `Set` / `Date` are
opaque — mutations to them do NOT trigger re-render.

```javascript
// BAD — mutations to Map are invisible
const state = useState({ cache: new Map() });
state.cache.set("k", "v");      // does NOT re-render

// GOOD — use plain object
const state = useState({ cache: {} });
state.cache["k"] = "v";          // re-renders
```

If you must use `Map`, wrap mutations in a re-assign:

```javascript
state.cache.set("k", "v");
state.cache = state.cache;       // forces re-render trigger
```

(This is a hack — prefer plain objects.)

## `useEffect` — running code on state change

OWL 2.2+ has `useEffect(callback, depsFn)`:

```javascript
import { useEffect, useState } from "@odoo/owl";

setup() {
    this.state = useState({ filter: "" });

    useEffect(
        (filter) => {
            console.log("filter changed to", filter);
            this.fetchResults(filter);
            // optional cleanup
            return () => console.log("filter changing away from", filter);
        },
        () => [this.state.filter],   // deps function — return array of tracked values
    );
}
```

Behavior:
- Runs after first mount (like React's `useEffect`).
- Runs again when ANY dep returned by the second arg changes.
- The cleanup function (if returned) runs BEFORE the next effect run.

`<see Odoo Frontend Framework useEffect docs>` for the exact behavior in
Odoo 17 vs 18 — early OWL 2.0 did not ship `useEffect`; teams polyfilled
via `onWillRender + lastValue` comparison.

## Shared state — `reactive` + cross-component sync

For state shared across siblings (e.g. a feature flag, current user,
shopping cart), use `reactive(obj)` defined OUTSIDE the component:

```javascript
// cart_store.js
import { reactive } from "@odoo/owl";

export const cartStore = reactive({
    items: [],
    total: 0,
    addItem(item) {
        this.items.push(item);
        this.total += item.price;
    },
});
```

```javascript
// any component
import { useState } from "@odoo/owl";
import { cartStore } from "@my_module/cart_store";

setup() {
    this.cart = useState(cartStore);   // subscribe THIS component
}
```

Calling `useState(cartStore)` does NOT create a new state — it subscribes
the current component to the existing store's changes.

## Common bugs (paste into review)

- [ ] Any `useRef` used for non-DOM data? → switch to `useState`.
- [ ] Any plain `Map` / `Set` / `Date` inside `useState({...})`? →
      reactivity does not work on these; use plain object/array.
- [ ] Any `state.x = rawObj` followed by `rawObj.y = v`? → mutation
      bypasses proxy.
- [ ] Any captured primitive (`const x = state.count`) used later as a
      "live" value? → primitives are snapshots.
- [ ] Any `useEffect` whose deps function doesn't actually return a
      stable array reference? → effect may run every render.
- [ ] Any `reactive(obj)` declared INSIDE `setup()`? → defeats sharing
      across components; should be module-level.

## Falsification recipe — Map reactivity bug

1. `const state = useState({ m: new Map() });`
2. Bind `<t t-esc="state.m.get('k') || 'none'"/>` in template.
3. In a click handler: `this.state.m.set('k', 'X');`
4. Click — observe: DOM still shows `none` (no re-render).
5. Add `this.state.m = this.state.m;` after the `set` — re-render fires.
6. Refactor to plain object `{}` — re-render fires automatically.
