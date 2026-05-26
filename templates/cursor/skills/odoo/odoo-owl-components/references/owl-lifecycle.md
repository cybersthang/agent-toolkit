# OWL lifecycle — depth reference

Companion to `SKILL.md` §1 (`setup()` vs `onMounted()` race). All examples
use placeholder names — adapt to real components via `codebase.search_text`.

## The full lifecycle graph

```
Component instantiation
        │
        ▼
   constructor()       ← internal OWL bookkeeping; do NOT override
        │
        ▼
     setup()           ← user code: hooks (useState, useRef, useService),
        │                event subscriptions, reactive primitives.
        │                NO DOM ACCESS HERE.
        ▼
   onWillStart()       ← async pre-render data fetch.
        │                Returning a Promise blocks render until resolved.
        ▼
     render            ← OWL builds the vnode tree.
        │
        ▼
   onWillRender()      ← runs before EACH render (initial + updates).
        │                Read state, derive computed values for the next render.
        ▼
    DOM patch          ← OWL diffs and applies to the DOM.
        │
        ▼
    onMounted()        ← runs ONCE after the first DOM attach.
        │                Safe to read this.el / refs / dimensions.
        │                Initialize 3rd-party libs that need DOM.
        ▼
   onWillUpdateProps() ← runs when parent re-renders with new props.
        │                Async: returning a Promise blocks the update.
        ▼
    onPatched()        ← runs after EACH re-render's DOM patch.
        │                NOT the first mount — onMounted handles that.
        ▼
    onWillUnmount()    ← cleanup: destroy 3rd-party instances, clear timers.
        │
        ▼
   Component removed
```

`<see Odoo Frontend Framework lifecycle docs>` for the exact list per
OWL minor version — `onError` was added in 2.1, `onRendered` was renamed
between releases.

## Common pitfalls per hook

### `setup()` — no DOM

```javascript
setup() {
    // BAD — refs are not yet bound to DOM
    this.myRef = useRef("input");
    this.myRef.el.focus();
}
```

`useRef("input")` returns an object whose `.el` getter is computed
lazily — accessing it inside `setup()` returns `null`.

### `onWillStart` — must return a Promise (or undefined)

```javascript
// BAD — sync work; OWL never blocks render, request fires twice
onWillStart(async () => {
    this.data = this.rpc("/my/endpoint");  // not awaited
});

// GOOD
onWillStart(async () => {
    this.data = await this.rpc("/my/endpoint");
});
```

OWL awaits the returned Promise before initial render. Synchronous
`onWillStart` returns `undefined`, which OWL treats as "ready
immediately" — your fetch runs but the component renders without
its data.

### `onMounted` — runs ONCE, not on re-renders

```javascript
// BAD — observer attached every re-render (memory leak)
onWillRender(() => {
    new IntersectionObserver(...).observe(this.el);
});

// GOOD
onMounted(() => {
    this.observer = new IntersectionObserver(...);
    this.observer.observe(this.el);
});
onWillUnmount(() => {
    this.observer.disconnect();
});
```

### `onPatched` vs `onMounted`

| Hook | When |
|---|---|
| `onMounted` | After first render attaches to DOM. Runs ONCE. |
| `onPatched` | After every subsequent re-render's DOM patch. |

If you need work on EVERY render (initial + updates), use both:

```javascript
const initThirdParty = () => { /* ... */ };
onMounted(initThirdParty);
onPatched(initThirdParty);
```

### `onWillUnmount` — async cleanup is forbidden

OWL ignores return values from `onWillUnmount`. If you need async
cleanup, fire-and-forget the Promise but don't expect OWL to await it.

```javascript
// Cleanup that MUST happen — synchronous
onWillUnmount(() => {
    clearInterval(this.timer);
    this.chart?.destroy();
});

// Cleanup that's nice-to-have — fire and forget
onWillUnmount(() => {
    this.rpc("/api/track/unmount", { id: this.props.id }).catch(() => {});
});
```

## Hook composition — `useService` etc.

Hooks like `useService`, `useState`, `useRef`, `useBus` MUST be called
inside `setup()` only. They register with OWL's component context;
calling them elsewhere raises:

```
Error: Hook 'useState' can only be called inside 'setup' function
```

If you need a service later (e.g. inside a callback), capture it during
setup:

```javascript
setup() {
    this.notification = useService("notification");
    this.action = useService("action");
}

handleClick() {
    this.notification.add("Hello");   // captured reference, fine
    // useService("notification") here — would throw
}
```

## Race-condition checklist

- [ ] Is DOM access (`this.el`, `ref.el`, `getBoundingClientRect`)
      strictly inside `onMounted` / `onPatched`?
- [ ] Is every `onMounted` resource (`setInterval`, `Observer`,
      3rd-party instance) paired with cleanup in `onWillUnmount`?
- [ ] Is every async `onWillStart` actually `await`-ed (returning the
      Promise, not firing and dropping it)?
- [ ] Are all `use*` hooks called at the TOP of `setup()`, before any
      conditional / loop?
- [ ] Is `onWillUnmount` cleanup sync? (no `await` inside the callback's
      critical resource teardown)
