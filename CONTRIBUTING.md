# Contributing to agent-toolkit

Thanks for opening this — agent-toolkit is small enough that one engineer reads every issue and PR personally. Please keep the loop tight: short repro, narrow patch.

## Reporting bugs

Open an issue on the toolkit repo (the canonical home is GitLab; if you found this via a GitHub mirror, file there and the maintainer will sync) with:

1. **What you ran** — exact command (`setup.py update <path> --preset <name>`, or the slash command).
2. **What you expected** — one sentence.
3. **What actually happened** — paste the relevant lines from stdout/stderr. If a hook fired unexpectedly, include the JSON output of the hook.
4. **Environment** — OS, Python version (`python --version`), and the toolkit version (`python setup.py --version`).
5. **`.agent-toolkit/.hook_crash_log.json` excerpt** if a hook crashed.

A 5-line failing test in `tests/` is the gold standard. If you can't write one, prose is fine — we'd rather have an imperfect issue than no issue.

## Proposing a change

The toolkit follows a simple lifecycle: **ADR → invariant → hook → test → CHANGELOG**.

For non-trivial changes (>30 LOC, new hook, new rule):

1. Open an issue first to align on direction. Drive-by PRs that surprise the maintainer are likely to be closed.
2. Reference the relevant Harness Engineering principle the change touches (mechanical enforcement / observability / fail-safe / etc. — see [README §Harness Engineering principles](README.md)).
3. If you're adding a hook: include a test under `tests/` that runs the hook via subprocess with a synthesised envelope. The bar is "the test would catch a regression by future-me", not "the test maxes coverage".

For trivial changes (typo, doc fix, obvious bug):

- Skip the issue, send the PR directly. Include a 1-line description and the file path. Branch name `fix/<slug>` or `docs/<slug>`.

## Local dev setup

```bash
git clone https://github.com/<your-fork>/agent-toolkit
cd agent-toolkit
python -m venv .venv
.venv/Scripts/activate     # Windows
# source .venv/bin/activate  # macOS/Linux
python -m pip install --upgrade pip pytest

# Smoke-test the CLI on a throwaway directory
mkdir /tmp/toolkit-smoke
python setup.py init /tmp/toolkit-smoke --preset generic --yes --dry-run

# Run the test suite (587 tests as of v0.21.0; ~50s on a modern laptop)
python -m pytest tests/ --no-cov

# Optional: lint
python -m pip install ruff
ruff check setup.py lib/ tests/
```

**Faster path — `make`**: the repo ships a `Makefile` that wraps the
common targets:

```bash
make install   # pip install pytest pytest-cov ruff (no version pins needed —
               # see docs/AUDIT_HISTORY.md F7 for why pytest-cov 7.x works)
make test      # full pytest suite, no coverage gate
make coverage  # pytest with --cov-fail-under=70 (CI parity)
make lint      # ruff check
make rebuild   # full CI-equivalent sequence (install + lint + test + smoke + cov)
```

Or pin everything via `pip install -r requirements-dev.txt`.

The toolkit is intentionally stdlib-only at runtime (`lib/installer.py` docstring documents this). Dev-time deps live in `pytest`, `pytest-cov`, and `ruff` — that's it.

## Code style

- **No comments unless the WHY is non-obvious.** Self-explanatory code with descriptive names beats prose every time. The toolkit eats its own dog food on this — see `.cursor/rules/_common/karpathy-guidelines.mdc` §Surgical Changes.
- **`<module>` placeholders in templates.** Don't hard-code a stack/module name in `templates/` or `presets/generic.json` / `presets/odoo-*.json` (private overlays in gitignored `presets/*-private.json` may do whatever).
- **Atomic JSON writes.** Use `atomic_write_json` from `templates/claude/hooks/_common.py` for any state file under `.agent-toolkit/`. Parallel hook fires will corrupt naive `path.write_text`.
- **Subprocess on Windows.** Always pass `encoding="utf-8", errors="replace"` when spawning child processes that may print non-ASCII. Forgetting this is the #1 source of flaky Windows tests (see v0.11.0/v0.12.0 honest CHANGELOG entries).
- **Hook output discipline.** Hooks either print **nothing** (silent allow) or emit a single-line `additionalContext` / `decision: block` JSON. No stderr chatter for non-error paths.

## Tests

- `tests/test_*.py` is the source of truth. CI runs the matrix (Ubuntu/macOS/Windows × Python 3.8/3.10/3.12).
- New hook → new `test_<hook_name>.py` exercising at minimum: happy path, DISABLE env-var bypass, malformed-input fail-safe (must `exit 0`).
- Use `subprocess.run([sys.executable, str(HOOK)], ...)` not module import — hooks call `wrap_utf8_stdio()` at module init and that corrupts pytest's stdout capture.

## License + DCO

By submitting a PR you agree your contribution is licensed under the MIT license (see `LICENSE`). No CLA. Sign your commits if you want (`git commit -s`); we don't require it but it's a habit worth having.

## Questions

Open a Discussion (GitLab Discussions on the canonical repo, or the equivalent on whichever mirror you found) — preferred over issues for "how do I..." questions. Or email the maintainer listed in `README.md`.
