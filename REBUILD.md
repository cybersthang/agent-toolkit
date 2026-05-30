# REBUILD.md — clone, verify, release agent-toolkit

> **Audience**: maintainer publishing or re-publishing this repo.
> **Goal**: 100% deterministic rebuild from a fresh clone — same input,
> same green CI, same release artifact.

This file mirrors the manual sequence that `.github/workflows/test.yml`
+ `.gitlab-ci.yml` + `Makefile` already automate. Use it when you need
to verify locally, push to a new GitHub mirror, or cut a tagged release.

---

## 0. Pre-flight (one-time, per machine)

```bash
# Required: Python >= 3.8 + git + (optionally) pre-commit
python3 --version   # must print 3.8+
git --version
```

If you plan to run pre-commit hooks locally:

```bash
python3 -m pip install pre-commit
pre-commit install --hook-type pre-commit
```

---

## 1. Clone + install dev deps

```bash
git clone <repo-url> agent-toolkit
cd agent-toolkit
make install        # → pip install pytest pytest-cov ruff
```

Override Python:

```bash
make PYTHON=/path/to/venv/bin/python install
```

---

## 2. Local verify (CI parity)

A single command runs everything CI runs:

```bash
make rebuild
```

Expanded, `make rebuild` executes:

| Step | Equivalent CI step | What it does |
|---|---|---|
| `lint` | `.github/workflows/test.yml` lint job | `ruff check setup.py lib/ tests/` |
| `test` | `.github/workflows/test.yml` test job (matrix) | `pytest tests/ -v` (no cov gate) |
| `smoke` | test.yml smoke step | `setup.py --version` + `list-presets` |
| `dry-run` | test.yml dry-run step | `setup.py init /tmp/agent-toolkit-smoke --preset generic --yes --dry-run` |
| `coverage` | `.github/workflows/test.yml` coverage job | `pytest --cov --cov-fail-under=70` (Linux + Python 3.8 only) |

Expected output ends with `REBUILD GREEN — workspace ready`.

If `make rebuild` fails locally, **do not push**. Fix it first; the
exact same failure will surface on every CI matrix cell.

---

## 3. Cross-version test (optional but recommended)

The coverage gate runs on Python 3.12 in CI. **Both pytest-cov 5.x and
7.x are supported** — the `.coveragerc` uses `parallel = True +
concurrency = multiprocessing`, and the `Makefile coverage` target +
CI workflows export `COVERAGE_PROCESS_START` so pytest-cov 7.x's
subprocess-tracking shim activates. (Without these, 7.x would silently
skip subprocess setup.py runs from `test_e2e.py` and drop `setup.py`
coverage from 85% to 17%; see `docs/AUDIT_HISTORY.md` F7.)

If you run pytest manually (not through `make`), remember to set the
env var:

```bash
export COVERAGE_PROCESS_START="$(pwd)/.coveragerc"
pytest tests/ --cov --cov-fail-under=70
```

Then verify the matrix locally:

```bash
make PYTHON=python3.10 test     # tests only — should PASS
make PYTHON=python3.12 test     # tests only — should PASS
make PYTHON=python3.12 coverage # cov gate — should report >= 70%
```

---

## 4. Push to GitHub (mirror setup)

The canonical remote is GitLab. If you need a GitHub mirror so people
can find the repo from Google + see CI badge:

```bash
# 4.1 — add GitHub remote (one-time per local clone)
git remote add github git@github.com:<YOUR_ORG>/agent-toolkit.git

# 4.2 — push main (this becomes the GitHub default branch)
git push github master:main --force-with-lease

# 4.3 — push the latest release-line branch as well
git push github 1.0

# 4.4 — push tags so GitHub Releases populates
git push github --tags
```

After step 4.2 + 4.3, update the README CI badge URL:

```bash
# Replace the placeholder in README.md with your actual GitHub org/user
sed -i "s|GITHUB_OWNER_PLACEHOLDER|<YOUR_ORG>|g" README.md
git add README.md
git commit -m "docs(readme): wire CI badge to <YOUR_ORG>/agent-toolkit"
git push github master:main
```

> **Caveat — `--force-with-lease`**: This rewrites the GitHub `main`
> branch. Only do this on the *initial* mirror or when intentionally
> realigning the mirror with GitLab. Never force-push to a `main` that
> has external contributors / open PRs.

---

## 5. Cut a tagged release

```bash
# 5.1 — verify CI is green on both remotes before tagging
git fetch --all
make rebuild     # final local sanity check

# 5.2 — bump version in two places (must match)
#   - lib/installer.py: __version__ = '0.21.0'
#   - CHANGELOG.md: new top section "## [0.21.0] — YYYY-MM-DD"
# Then commit:
git add lib/installer.py CHANGELOG.md
git commit -m "release: bump to v0.21.0"

# 5.3 — annotated tag
git tag -a v0.21.0 -m "v0.21.0 — see CHANGELOG.md"

# 5.4 — push tag to both remotes
git push origin v0.21.0
git push github v0.21.0   # if mirror exists

# 5.5 — create GitHub Release with notes
# Web UI: https://github.com/<YOUR_ORG>/agent-toolkit/releases/new
# Or via gh CLI:
gh release create v0.21.0 --notes-file CHANGELOG.md
```

---

## 6. Post-release smoke

After tagging, verify a fresh consumer install still works:

```bash
# Fresh clone in a temp dir
TMP=$(mktemp -d)
cd "$TMP"
git clone <github-url> agent-toolkit-fresh
cd agent-toolkit-fresh
git checkout v0.21.0
make rebuild     # must end with REBUILD GREEN
```

If `make rebuild` fails on a freshly-cloned tag, **delete the tag** and
investigate. Never publish a tag that doesn't pass `make rebuild` on a
clean machine.

```bash
# Rollback bad tag
git push origin :refs/tags/v0.21.0
git push github :refs/tags/v0.21.0
git tag -d v0.21.0
```

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `make rebuild` fails at `coverage` with "below 70%" | `setup.py` not being imported by `tests/test_setup.py` due to Python version weirdness | Check `.coveragerc` — `source =` line must list `setup` (module name), not `setup.py` (literal path) |
| GitHub Actions matrix red on every cell | `--cov-fail-under` accidentally re-added to `pytest.ini` default `addopts` | Remove from `pytest.ini`; the dedicated `coverage` job in `test.yml` handles the gate |
| GitHub `main` branch shows only README ("Initial commit") | Forgot step 4.2 (push master to main) | Run `git push github master:main --force-with-lease` |
| `make rebuild` PASS but CI fail with same error | Different Python version on CI vs local | Run `make PYTHON=python3.10 rebuild` locally to reproduce |
| `make install` fails on Windows | Path/permission issue with `python -m pip install --upgrade pip` | Run as admin OR use `make PYTHON=$(which python) install` |
| Stale `.bak.*` files cluttering repo | Older toolkit version without A3 fix | `git clean -X` (cleans gitignored files); `setup.py update` v0.21+ + the consumer-side `.gitignore` snippet handle this automatically |

---

## 8. What "100% rebuild" means

A "100% rebuild" promise means:

1. **Same input** — committed tree at tag `v0.21.0`.
2. **Same environment** — Python 3.8/3.10/3.12 + pytest + pytest-cov + ruff at the versions resolved by `make install`.
3. **Same output** — `make rebuild` ends with `REBUILD GREEN`; CI matrix all green; tests all PASS (~1018 at v0.32.0); coverage ≥ 70% on the gated cell.

Any drift between local `make rebuild` and CI is a **bug**, not "flaky tests". File it, fix it, re-tag.

---

## 9. Files touched by this rebuild contract

```
.github/workflows/test.yml   ← matrix tests + lint + coverage gate
.gitlab-ci.yml               ← mirror (test + lint + coverage)
Makefile                     ← one-command targets
pytest.ini                   ← no cov gate in default addopts (F7)
.coveragerc                  ← source = setup (F1)
lib/installer.py             ← __version__ (bump on release)
CHANGELOG.md                 ← release notes
README.md                    ← CI badge URL (step 4)
```

Everything in this list must stay aligned at release time. If you edit
one, audit the others.
