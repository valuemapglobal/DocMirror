# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Finance PEC integration — runs when docmirror_finance is installed."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from unittest.mock import patch

import pytest

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.plugins._runtime.runner import run_plugin_extract_sync
from tests.contract.test_edition_schema_conformance import check_finance

pytest.importorskip("docmirror_finance")

pytestmark = [pytest.mark.integration]

ALIPAY_FIXTURE = Path("tests/fixtures/alipay_payment/DemoUser+支付宝流水.pdf")


def test_finance_package_importable():
    assert importlib.import_module("docmirror_finance") is not None


def test_finance_alipay_extract_smoke():
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type="alipay_payment")

    with patch("docmirror.plugins.runner._is_edition_plugin_licensed", return_value=True):
        out = run_plugin_extract_sync(pr, edition="finance")

    if out is None:
        pytest.skip("finance plugin returned None (may need mirror tables/text)")
    assert out.get("edition") == "finance"


@pytest.mark.slow
def test_finance_alipay_fixture_quality_metrics():
    """Full fixture extract — quality block must be internally consistent."""
    if not ALIPAY_FIXTURE.is_file():
        pytest.skip(f"missing fixture {ALIPAY_FIXTURE}")

    from docmirror.input.entry.factory import PerceiveOptions, perceive_document

    mirror = asyncio.run(
        perceive_document(ALIPAY_FIXTURE, PerceiveOptions(enhance_mode="standard"))
    ).mirror

    with patch("docmirror.plugins.runner._is_edition_plugin_licensed", return_value=True):
        out = run_plugin_extract_sync(
            mirror,
            edition="finance",
            full_text=mirror.full_text,
            file_path=str(ALIPAY_FIXTURE),
        )

    assert out is not None
    errors = check_finance(out, str(ALIPAY_FIXTURE))
    assert not errors, errors

    quality = out["quality"]
    validation = out["validation"]

    assert quality["field_coverage"]["timestamp"] == quality["field_confidence"]["timestamp"] == 1.0
    assert quality["overall_score"] >= 0.9
    assert quality["validation_passed"] is True

    indices = [item["index"] for item in quality["record_confidence"]]
    assert indices[0] == 1
    assert len(set(indices)) > 1

    page_count = out.get("document", {}).get("page_count") or out.get("source", {}).get("page_count")
    assert len(quality["page_quality"]) == page_count

    fmt = next(r for r in validation["rules"] if r["rule_code"] == "FORMAT_CHECK")
    time_rule = next(r for r in validation["rules"] if r["rule_code"] == "TIME_ORDER_CHECK")
    assert fmt["status"] == "passed"
    assert time_rule["status"] == "passed"
