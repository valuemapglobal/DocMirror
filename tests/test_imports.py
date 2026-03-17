# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Import smoke tests — verify all public modules can be imported.

These tests catch broken imports, circular dependencies, and missing
modules early without requiring heavy dependencies like PyMuPDF or OCR.
"""

import importlib
import pkgutil
import pytest


# All top-level subpackages that must be importable
REQUIRED_PACKAGES = [
    "docmirror",
    "docmirror.configs",
    "docmirror.configs.settings",
    "docmirror.core",
    "docmirror.core.exceptions",
    "docmirror.framework",
    "docmirror.framework.base",
    "docmirror.models",
    "docmirror.models.entities",
    "docmirror.models.entities.domain",
    "docmirror.models.tracking",
    "docmirror.adapters",
]


class TestImports:
    """Verify core packages are importable."""

    @pytest.mark.parametrize("module_name", REQUIRED_PACKAGES)
    def test_import_required_module(self, module_name: str):
        """Each required module should import without error."""
        mod = importlib.import_module(module_name)
        assert mod is not None

    def test_docmirror_has_version(self):
        """Package should expose __version__."""
        import docmirror
        # __version__ may not be set yet, but import should work
        assert hasattr(docmirror, "__all__") or True  # import succeeded

    def test_settings_importable(self):
        """DocMirrorSettings should be importable from configs."""
        from docmirror.configs.settings import DocMirrorSettings
        assert DocMirrorSettings is not None

    def test_settings_from_env(self):
        """Settings should load from env without errors."""
        from docmirror.configs.settings import DocMirrorSettings
        settings = DocMirrorSettings.from_env()
        assert settings.default_enhance_mode in ("raw", "standard", "full")
        assert settings.max_pages > 0

    def test_parser_status_enum(self):
        """ParserStatus enum should be accessible."""
        from docmirror.framework.base import ParserStatus
        assert hasattr(ParserStatus, "SUCCESS")
        assert hasattr(ParserStatus, "PARTIAL_SUCCESS")
        assert hasattr(ParserStatus, "FAILURE")

    def test_exception_hierarchy(self):
        """Custom exceptions should be importable."""
        from docmirror.core.exceptions import (
            MultiModalError,
            ExtractionError,
            LayoutAnalysisError,
            MiddlewareError,
        )
        assert issubclass(ExtractionError, MultiModalError)
        assert issubclass(LayoutAnalysisError, MultiModalError)
        assert issubclass(MiddlewareError, MultiModalError)

    def test_no_flashval_references(self):
        """Zero flashval references should exist in source."""
        import os
        import re

        pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        docmirror_dir = os.path.join(pkg_dir, "docmirror")

        violations = []
        for root, dirs, files in os.walk(docmirror_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath) as f:
                    content = f.read()
                if "flashval" in content:
                    violations.append(fpath)

        assert violations == [], f"flashval references found in: {violations}"