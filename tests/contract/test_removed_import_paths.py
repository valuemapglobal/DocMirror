# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Contract tests for removed pre-refactor import paths."""

from __future__ import annotations

import importlib.util


def test_removed_pre_refactor_import_paths_do_not_resolve():
    removed = [
        "docmirror.core",
        "docmirror.structure",
        "docmirror.adapters",
        "docmirror.middlewares",
        "docmirror.exporters",
        "docmirror.integration",
        "docmirror.deployment",
        "docmirror.di",
        "docmirror.plugins.runner",
        "docmirror.plugins.licensing",
        "docmirror.plugins.post_extract",
    ]

    for module in removed:
        assert importlib.util.find_spec(module) is None, module


def test_canonical_replacements_resolve():
    replacements = [
        "docmirror.layout",
        "docmirror.input.adapters",
        "docmirror.framework.middlewares",
        "docmirror.output.exporters",
        "docmirror.sdk.integration",
        "docmirror.framework.di",
        "docmirror.plugins._runtime.runner",
        "docmirror.plugins._runtime.licensing",
        "docmirror.plugins._runtime.post_extract",
    ]

    for module in replacements:
        assert importlib.util.find_spec(module) is not None, module
