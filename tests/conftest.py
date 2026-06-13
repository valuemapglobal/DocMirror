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
    ├── test_imports.py      # Import smoke tests
    ├── test_settings.py     # Configuration tests
    └── test_dispatcher.py   # Dispatcher routing tests
"""
import os
import sys
from pathlib import Path

import pytest

# Ensure the project root is on sys.path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


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


@pytest.fixture
def fixtures_dir():
    """Return the path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"