# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Contract tests for removed pre-refactor import paths."""

from __future__ import annotations

import importlib.util

from scripts.code_hygiene.clean_manifest import load_clean_manifest


def _find_spec(module: str):
    """Return no spec when any parent in an already-removed path is absent."""
    try:
        return importlib.util.find_spec(module)
    except (AttributeError, ModuleNotFoundError):
        return None


def test_removed_pre_refactor_import_paths_do_not_resolve():
    removed = sorted(load_clean_manifest().removed_modules)

    for module in removed:
        assert _find_spec(module) is None, module


def test_canonical_replacements_resolve():
    replacements = [
        "docmirror.layout",
        "docmirror.input.adapters",
        "docmirror.framework.middlewares",
        "docmirror.output.exporters",
        "docmirror.sdk.integration",
        "docmirror.framework.di",
        "docmirror.framework.middlewares.extraction.community_fact_recognizer",
        "docmirror.plugins._runtime.licensing",
        "docmirror.plugin_api",
    ]

    for module in replacements:
        assert _find_spec(module) is not None, module
