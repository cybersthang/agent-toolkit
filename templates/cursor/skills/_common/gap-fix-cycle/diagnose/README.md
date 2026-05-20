# gap-fix-cycle diagnose strategies

This directory holds pluggable strategies that translate a probe's failure
stderr into a concrete patch proposal. Each `.py` file exports two
functions:

```python
def matches(probe: dict, last_stderr: str) -> bool: ...
def diagnose(probe: dict, last_stderr: str, workspace: Path) -> Optional[dict]: ...
```

`diagnose()` returns either `None` (no patch proposed) or a dict:

```python
{
    "file": "<path-relative-to-workspace>",
    "old_string": "<exact text to replace>",
    "new_string": "<replacement>",
    "rationale": "<one-line WHY for decision-log>",
}
```

## Built-in strategies

- `python_attribute_error.py` — `AttributeError: '<X>' object has no attribute '<Y>'` → propose adding a stub for `<Y>` on `<X>` (or rename a near-match attr).
- `python_assertion_mismatch.py` — Compare expected vs actual in AssertionError; if expected is a literal value, propose replacing it.
- `regex_mismatch.py` — `log_assertion` failure due to regex anchor mismatch; propose loosening anchors.
- `playwright_dom_missing.py` — Playwright test failure with "Selector resolved to 0 elements" → propose template / view file edit.
- `python_import_error.py` — `ModuleNotFoundError` → propose adding the missing module to a `__init__.py`.

## Adding a strategy

1. Create `<name>.py` in this directory.
2. Implement `matches()` and `diagnose()`.
3. Add unit test in `tests/skills/gap_fix_cycle/test_<name>.py`.
4. PR upstream.

## Order of evaluation

Strategies are tried in alphabetical filename order. First strategy
whose `matches()` returns True is invoked. If `diagnose()` returns
None, evaluation moves to the next strategy.
