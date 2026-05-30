# Pre-commit setup (agent-toolkit own repo)

This document covers the toolkit's **own** `.pre-commit-config.yaml` at
the repo root — the one that runs the test suite before every commit
to prevent CI-fail-post-push regressions.

> Note: this is NOT the same as `templates/pre-commit-config.yaml.tmpl`,
> which is the *template* shipped into consumer projects (mirrors
> `invariant_guard` etc.). That one runs in downstream repos; this
> one runs in the toolkit repo itself.

## Why

Finding F7 (consolidated audit, v0.21): the agent kept running a
*subset* of tests, declaring "done", pushing to GitHub — then CI
failed because the full suite hit a code path the subset didn't.

The pre-commit hook below runs the **exact** pytest invocation CI
runs (see `.github/workflows/test.yml`) on every local commit that
touches code or tests, so a clean local commit ≈ a green CI test job.

## Install (one-time, per fresh clone)

```bash
# 1. Activate the project venv first (Windows PowerShell)
C:/Users/<you>/agent-toolkit/venv/Scripts/Activate.ps1

# 2. Install the pre-commit framework
pip install pre-commit

# 3. Register the git hook in this repo
cd C:/Users/<you>/agent-toolkit
pre-commit install --hook-type pre-commit
```

After that, `git commit` will automatically:

1. Inspect staged paths.
2. If any path matches `^(templates/|tests/|lib/|setup\.py|pytest\.ini|presets/).*`, run
   `python -m pytest tests/ --no-cov -q`.
3. Abort the commit if pytest exits non-zero.

Doc-only commits (top-level `README.md`, `CHANGELOG.md`, `*.md` outside
`templates/`) skip the hook entirely.

## Venv requirements

`language: system` means pre-commit uses whichever Python is on `PATH`
when you run `git commit`. **You must activate the project venv first**
or the hook will run against the wrong interpreter:

```powershell
# Windows
C:/Users/<you>/agent-toolkit/venv/Scripts/Activate.ps1
git commit -m "..."
```

```bash
# macOS / Linux
source /path/to/venv/bin/activate
git commit -m "..."
```

If the venv lacks `pytest` / `pytest-cov`:

```bash
pip install -r requirements-dev.txt
# or, equivalent:
make install
# or, manual:
pip install pytest pytest-cov ruff
```

(CI installs these explicitly per `.github/workflows/test.yml`. Note: no
`pytest-cov` version pin is needed — see `docs/AUDIT_HISTORY.md` F7 for
why both 5.x and 7.x work with the project's `.coveragerc` config.)

## Bypass (use sparingly)

```bash
git commit --no-verify -m "doc-only typo fix"
```

`--no-verify` is logged in git history via the commit hash, so if you
bypass and CI later fails, the audit trail is intact. Do **not**
bypass for code changes — the whole point is to catch CI breaks
locally.

## Updating the hook

The pytest command lives in `.pre-commit-config.yaml` at repo root.
Editing the YAML takes effect on the next commit — no re-install
needed. If you add a new hook block, run `pre-commit install` again
only when you change `hook-type` or repo definition (not on script
content changes).

## Verifying installation

```bash
pre-commit run --all-files
```

Expected: pytest runs against the full `tests/` tree and prints
either a green `passed` summary or red failure lines. Exit code 0 =
hook would have allowed the commit; non-zero = hook would block.

## Manual one-off run (without installing the hook)

```bash
pre-commit run pytest-toolkit-tests --all-files
```

Useful for verifying the YAML is well-formed before installing.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `pytest: command not found` | Venv not activated, or pytest not installed in active venv | Activate venv + `make install` (or `pip install -r requirements-dev.txt`) |
| Hook runs on doc-only commits | `files:` regex too broad | Adjust regex in `.pre-commit-config.yaml`; double-check the staged paths |
| Hook never runs | `pre-commit install` was skipped, or `.git/hooks/pre-commit` was overwritten by another tool | Re-run `pre-commit install --hook-type pre-commit` |
| `Executable python not found` on Windows | `language: system` cannot resolve `python` on PATH | Activate venv, or change `entry:` to absolute venv path locally (do NOT commit that change — breaks portability) |

## Related

* `.github/workflows/test.yml` — CI job this hook mirrors.
* `pytest.ini` — coverage gate (70%) only enforced in CI; pre-commit
  skips coverage for speed.
* `templates/pre-commit-config.yaml.tmpl` — separate template installed
  into downstream consumer projects (mirrors `invariant_guard`, not
  the test suite).
