.PHONY: help install lint format test test-smoke test-contract test-regression test-golden coverage clean

help:
	@echo "Available commands:"
	@echo "  make install   - Install dependencies for development"
	@echo "  make format    - Format code using ruff"
	@echo "  make lint      - Run static analysis using ruff and mypy"
	@echo "  make test      - Run tests with pytest (PR tier matrix)"
	@echo "  make test-smoke     - Tier SMOKE only"
	@echo "  make test-contract  - Tier CONTRACT only"
	@echo "  make test-regression- Tier REGRESSION (not slow)"
	@echo "  make test-golden    - Tier slow / nightly golden"
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

coverage:
	coverage run -m pytest
	coverage report --fail-under=80
	coverage html
	@echo "HTML report: htmlcov/index.html"

clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .ruff_cache/ .mypy_cache/ htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
