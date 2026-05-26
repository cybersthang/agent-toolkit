# agent-toolkit — Makefile
#
# One-command operations for development, CI parity, and deterministic
# rebuild from a fresh GitHub/GitLab clone. Mirror the steps GitHub
# Actions / GitLab CI run (see .github/workflows/test.yml +
# .gitlab-ci.yml) so `make rebuild` locally == green CI.
#
# Required: Python >= 3.8 on PATH as `python` or `python3`. Override via
#   `make PYTHON=/path/to/venv/bin/python <target>`.

PYTHON ?= python3
PIP    ?= $(PYTHON) -m pip
PYTEST ?= $(PYTHON) -m pytest
RUFF   ?= $(PYTHON) -m ruff
SMOKE_DIR ?= /tmp/agent-toolkit-smoke

.PHONY: help install test test-no-cov smoke dry-run lint coverage rebuild clean check-python check-deps

help:
	@echo "agent-toolkit — common make targets"
	@echo ""
	@echo "  make install      Install dev dependencies (pytest, pytest-cov, ruff)"
	@echo "  make test         Run full pytest suite (coverage shown, NOT gated)"
	@echo "  make test-no-cov  Run pytest WITHOUT coverage (faster, pre-commit-style)"
	@echo "  make coverage     Run pytest with --cov-fail-under=70 gate (CI parity)"
	@echo "  make smoke        Run setup.py --version + list-presets"
	@echo "  make dry-run      Run setup.py init --dry-run into $(SMOKE_DIR)"
	@echo "  make lint         Run ruff check on setup.py + lib/ + tests/"
	@echo "  make rebuild      Full CI-equivalent run: install + lint + test + coverage + smoke + dry-run"
	@echo "  make clean        Remove caches (.pytest_cache, .ruff_cache, __pycache__, .coverage)"
	@echo ""
	@echo "Override Python: make PYTHON=/path/to/venv/bin/python rebuild"

check-python:
	@$(PYTHON) -c "import sys; assert sys.version_info >= (3, 8), 'Python 3.8+ required, got %s' % sys.version" \
	    || (echo "ERROR: Python 3.8+ required (got $$($(PYTHON) --version 2>&1))"; exit 1)

check-deps: check-python
	@$(PYTHON) -c "import pytest" 2>/dev/null \
	    || (echo "ERROR: pytest not installed. Run: make install"; exit 1)

install: check-python
	# pytest-cov: no pin needed. The `.coveragerc` now uses
	# parallel + concurrency=multiprocessing, and the `coverage` target
	# below exports COVERAGE_PROCESS_START so pytest-cov 7.x's
	# `a1_coverage.pth` activates subprocess tracking. Verified on both
	# pytest-cov 5.x and 7.x — see F7 in docs/AUDIT_HISTORY.md.
	$(PIP) install --upgrade pip pytest pytest-cov ruff

test: check-deps
	$(PYTEST) tests/ -v

test-no-cov: check-deps
	$(PYTEST) tests/ --no-cov -q

coverage: check-deps
	# COVERAGE_PROCESS_START activates pytest-cov 7.x's `a1_coverage.pth`
	# subprocess-tracking shim. Together with parallel + concurrency in
	# `.coveragerc`, this captures coverage from `test_e2e.py` subprocess
	# setup.py runs (without it, setup.py reads 17% on 7.x vs 85% on 5.x).
	COVERAGE_PROCESS_START=$(CURDIR)/.coveragerc $(PYTEST) tests/ --cov --cov-report=term-missing --cov-fail-under=70

smoke: check-python
	$(PYTHON) setup.py --version
	$(PYTHON) setup.py list-presets

dry-run: check-python
	mkdir -p $(SMOKE_DIR)
	$(PYTHON) setup.py init $(SMOKE_DIR) --preset generic --yes --dry-run

lint: check-python
	$(RUFF) check setup.py lib/ tests/

# Full CI parity run — matches .github/workflows/test.yml + the new
# coverage job. `rebuild` is the single command DEV / CI executes on a
# fresh clone to verify the workspace is in a publishable state.
rebuild: install lint test smoke dry-run coverage
	@echo ""
	@echo "============================================================"
	@echo "  REBUILD GREEN — workspace ready"
	@echo "============================================================"

clean:
	rm -rf .pytest_cache .ruff_cache .coverage .coverage_html
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Caches cleaned."
