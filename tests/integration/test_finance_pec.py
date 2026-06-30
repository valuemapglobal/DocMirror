# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Finance PEC integration — runs when docmirror_finance is installed."""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.plugins._runtime.runner import run_plugin_extract_sync

pytest.importorskip("docmirror_finance")

pytestmark = [pytest.mark.integration]


def test_finance_package_importable():
    assert importlib.import_module("docmirror_finance") is not None


def test_finance_alipay_extract_smoke():
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type="alipay_payment")

    with patch("docmirror.plugins._runtime.runner._is_edition_plugin_licensed", return_value=True):
        out = run_plugin_extract_sync(pr, edition="finance")

    if out is None:
        pytest.skip("finance plugin returned None (may need mirror tables/text)")
    assert out.get("edition") == "finance"
