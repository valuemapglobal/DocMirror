# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Test suite for docmirror package.

Test structure:
    tests/
    ├── conftest.py          # Shared fixtures
    ├── fixtures/            # Test sample files (PDFs, images, etc.)
    ├── smoke/               # Import / settings / plugin smoke tests
    ├── contract/            # MOC / PEC / DEC boundary invariants
    └── unit/                # Component tests
"""
import os
import sys
from pathlib import Path

import pytest

# ── Fixture availability check ──
# tests/fixtures/ is gitignored (contains private/sensitive test data).
# Community contributors running minimal tests should use tier_smoke or tier_unit markers.
_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_FIXTURES_AVAILABLE = _FIXTURES_DIR.is_dir() and any(_FIXTURES_DIR.iterdir())


def _check_fixtures_available() -> None:
    """Exit pytest with a clear message if private fixtures are missing.

    Only triggers for tests that actually require fixtures (not tier_smoke or tier_unit).
    """
    if _FIXTURES_AVAILABLE:
        return
    msg = (
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  Test fixtures not found: tests/fixtures/ is empty or missing.\n"
        "  \n"
        "  This directory contains private/sensitive test data and is gitignored.\n"
        "  \n"
        "  To run tests WITHOUT fixtures (imports, settings, models, etc.):\n"
        "    $ make test-smoke          # tier_smoke only\n"
        "    $ pytest tests/smoke/ -q   # smoke tests (no fixtures needed)\n"
        "    $ pytest tests/unit/ -q -m \"not tier_slow\"  # most unit tests\n"
        "  \n"
        "  To get full test data, contact the DocMirror team or request access.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    pytest.exit(msg, returncode=0)

PROJECT_ROOT = Path(__file__).parent.parent.absolute()

def pytest_sessionstart(session):
    """Check fixture availability, then validate MEP/post-extract/TQG catalogs."""
    _check_fixtures_available()

    """Fail fast when MEP catalog YAML is inconsistent."""
    from docmirror.configs.middleware.catalog import validate_catalog
    from docmirror.plugins._runtime.post_extract.catalog import load_post_extract_catalog

    errors = validate_catalog()
    if errors:
        msg = "MEP catalog validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        pytest.exit(msg, returncode=1)

    try:
        load_post_extract_catalog()
    except Exception as exc:
        pytest.exit(f"post_extract catalog load failed: {exc}", returncode=1)

    # TQG manifest validation (Design 10) — non-blocking warning
    gates_dir = Path(PROJECT_ROOT) / "docmirror" / "configs" / "yaml" / "test" / "gates"
    if gates_dir.is_dir():
        try:
            from scripts.validate.validate_test_manifest import validate_manifest_file

            manifest_errors: list[str] = []
            for path in sorted(gates_dir.glob("*.yaml")):
                if path.name.startswith("_"):
                    continue
                manifest_errors.extend(validate_manifest_file(path))
            if manifest_errors:
                import logging
                logging.getLogger(__name__).warning(
                    "TQG manifest has %d validation issues (non-blocking). "
                    "Run `scripts/validate/validate_test_manifest.py` to see details.",
                    len(manifest_errors),
                )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "TQG manifest validation error (non-blocking): %s", exc
            )


@pytest.fixture
def fixtures_dir():
    """Return the path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def tqg_report_dir():
    """TQG GateReport JSON output directory (shared by regression + integration shims)."""
    default_report_dir = PROJECT_ROOT / "artifacts" / "tqg"
    path = Path(os.environ.get("TQG_REPORT_DIR", str(default_report_dir)))
    path.mkdir(parents=True, exist_ok=True)
    return path


def pytest_collection_modifyitems(config, items):
    """Apply TQG tier/track markers to parametrized case tests (regression + integration shims)."""
    from docmirror.eval.tqg.manifest import TQGCase

    for item in items:
        case = None
        if hasattr(item, "callspec") and item.callspec is not None:
            case = item.callspec.params.get("case")
        if not isinstance(case, TQGCase):
            continue
        item.add_marker(pytest.mark.tier_regression)
        item.add_marker(pytest.mark.integration)
        if case.is_slow:
            item.add_marker(pytest.mark.tier_slow)
            item.add_marker(pytest.mark.slow)
        track_marker = f"track_{case.track}"
        if hasattr(pytest.mark, track_marker):
            item.add_marker(getattr(pytest.mark, track_marker))
