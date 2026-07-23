# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Finance provider integration — runs when docmirror_finance is installed."""

from __future__ import annotations

import importlib

import pytest

pytest.importorskip("docmirror_finance")
pytestmark = [pytest.mark.integration]


def test_finance_package_registers_projectors_through_provider_registry() -> None:
    assert importlib.import_module("docmirror_finance") is not None

    from docmirror.plugins._runtime.plugin_registry import registry

    projectors = registry.list_projectors("finance")
    assert projectors
    assert all(projector.edition == "finance" for projector in projectors)
