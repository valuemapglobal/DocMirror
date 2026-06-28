.PHONY: help install lint format validate-clean test test-smoke test-contract test-regression test-golden test-udtr-golden test-udtr-cross-format-matrix coverage clean

help:
	@echo "Available commands:"
	@echo "  make install   - Install dependencies for development"
	@echo "  make format    - Format code using ruff"
	@echo "  make lint      - Run static analysis using ruff and mypy"
	@echo "  make validate-clean - Validate clean architecture manifest and stale path refs"
	@echo "  make test      - Run tests with pytest (PR tier matrix)"
	@echo "  make test-smoke     - Tier SMOKE only"
	@echo "  make test-contract  - Tier CONTRACT only"
	@echo "  make test-regression- Tier REGRESSION (not slow)"
	@echo "  make test-golden    - Tier slow / nightly golden"
	@echo "  make test-udtr-golden - UDTR metadata-only golden manifest"
	@echo "  make test-udtr-cross-format-matrix - UDTR real cross-format matrix (skips missing private samples)"
	@echo "  make coverage  - Run tests with coverage report"
	@echo "  make clean     - Remove build artifacts and cache directories"

install:
	pip install -e ".[all,dev,docs]"
	pre-commit install

format:
	ruff format .
	ruff check --fix .

lint:
	ruff check .
	mypy docmirror/
	$(MAKE) validate-clean

validate-clean:
	python3 scripts/validate/generate_import_linter.py --check
	python3 scripts/validate/validate_clean_manifest.py
	python3 scripts/validate/report_clean_quarantine.py --fail-overdue
	lint-imports --config .importlinter

test:
	pytest tests/unit/ -q
	pytest tests/ --ignore=tests/unit -m "tier_smoke or tier_contract or (tier_regression and not tier_slow)" -q

test-smoke:
	pytest -m "tier_smoke" tests/ -q

test-contract:
	pytest -m "tier_contract" tests/ -q

test-regression:
	pytest -m "tier_regression and not tier_slow" tests/ -q

test-golden:
	pytest -m "tier_slow" tests/regression/ -v

test-udtr-golden:
	python3 scripts/validate/validate_udtr_golden.py tests/golden/udtr/manifest.example.json

test-udtr-cross-format-matrix:
	python3 scripts/validate/run_udtr_cross_format_matrix.py tests/golden/udtr/cross_format_real_manifest.example.json

coverage:
	coverage run -m pytest
	coverage report --fail-under=80
	coverage html
	@echo "HTML report: htmlcov/index.html"

clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .ruff_cache/ .mypy_cache/ htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
