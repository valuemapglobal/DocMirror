"""Synthetic golden PDF fixture helpers.

The real synthetic fixture generator is optional and environment-gated by the
tests that use it. This module keeps the import path stable for skipped tests
and local developer workflows.
"""

from __future__ import annotations

from pathlib import Path


def ensure_bank_synthetic() -> Path:
    """Return the bank-statement synthetic PDF fixture if it exists."""
    candidates = (
        Path("tests/fixtures/synthetic/bank_statement.pdf"),
        Path("tests/golden/fixtures/bank_statement.pdf"),
        Path("tests/fixtures/bank_statement.pdf"),
    )
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "Synthetic bank statement fixture is not available. "
        "Set up a local fixture before enabling DOCMIRROR_RUN_SYNTHETIC_TESTS=1."
    )
