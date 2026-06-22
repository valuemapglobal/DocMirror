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

def pytest_sessionstart(session):
    """Fail fast when MEP catalog YAML is inconsistent."""
    from docmirror.configs.middleware.catalog import validate_catalog
    from docmirror.plugins.post_extract.catalog import load_post_extract_catalog

    errors = validate_catalog()
    if errors:
        msg = "MEP catalog validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        pytest.exit(msg, returncode=1)

    try:
        load_post_extract_catalog()
    except Exception as exc:
        pytest.exit(f"post_extract catalog load failed: {exc}", returncode=1)

    # TQG manifest validation (Design 10)
    gates_dir = Path(PROJECT_ROOT) / "docmirror" / "configs" / "yaml" / "test" / "gates"
    if gates_dir.is_dir():
        from scripts.validate.validate_test_manifest import validate_manifest_file

        manifest_errors: list[str] = []
        for path in sorted(gates_dir.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            manifest_errors.extend(validate_manifest_file(path))
        if manifest_errors:
            msg = "TQG manifest validation failed:\n" + "\n".join(f"  - {e}" for e in manifest_errors)
            pytest.exit(msg, returncode=1)


@pytest.fixture
def fixtures_dir():
    """Return the path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def tqg_report_dir():
    """TQG GateReport JSON output directory (shared by regression + integration shims)."""
    path = Path(os.environ.get("TQG_REPORT_DIR", PROJECT_ROOT + "/artifacts/tqg"))
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