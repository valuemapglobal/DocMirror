.PHONY: help install lint format test coverage clean

help:
	@echo "Available commands:"
	@echo "  make install   - Install dependencies for development"
	@echo "  make format    - Format code using ruff"
	@echo "  make lint      - Run static analysis using ruff and mypy"
	@echo "  make test      - Run tests with pytest"
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
	pytest

coverage:
	coverage run -m pytest
	coverage report --fail-under=80
	coverage html
	@echo "HTML report: htmlcov/index.html"

clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .ruff_cache/ .mypy_cache/ htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
