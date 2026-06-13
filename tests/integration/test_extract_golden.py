# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for extract-layer row fidelity (EPO golden gates)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from docmirror.core.evaluation.gates import GATE_PROFILES, extract_row_preservation_check
from docmirror.core.extraction.extractor import CoreExtractor
from docmirror.core.table.table_access import get_logical_tables
from docmirror.models.construction.parse_result_bridge import ParseResultBridge


WECHAT_PDF = Path("tests/fixtures/wechat_payment/DemoUser+微信流水.pdf")
ALIPAY_PDF = Path("tests/fixtures/alipay_payment/DemoUser+支付宝流水.pdf")


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(not WECHAT_PDF.exists(), reason="wechat fixture missing")
def test_wechat_logical_rows_gate():
    """WeChat 219-page ledger: logical rows must match script oracle (5111)."""
    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(WECHAT_PDF))
    result = ParseResultBridge.from_base_result(base)
    logical = get_logical_tables(result)
    primary_rows = max((lt.row_count for lt in logical), default=0)
    gate = extract_row_preservation_check(
        result,
        profile=GATE_PROFILES["wechat_payment"],
    )
    assert primary_rows == 5111, (
        f"primary_logical_rows={primary_rows}, total={sum(lt.row_count for lt in logical)}, "
        f"gate={gate.failures}"
    )
    assert gate.checks.get("min_logical_rows", False)
    assert gate.checks.get("max_logical_rows", False)


@pytest.mark.integration
@pytest.mark.skipif(not ALIPAY_PDF.exists(), reason="alipay fixture missing")
def test_alipay_logical_rows_regression():
    """Alipay 44-page ledger: logical rows ≥ 1400."""
    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(ALIPAY_PDF))
    result = ParseResultBridge.from_base_result(base)
    logical = get_logical_tables(result)
    logical_rows = sum(lt.row_count for lt in logical)
    gate = extract_row_preservation_check(
        result,
        profile=GATE_PROFILES["alipay_payment"],
    )
    assert logical_rows >= 1400, f"logical_rows={logical_rows}"
    assert gate.passed or gate.checks.get("min_logical_rows", False)


@pytest.mark.integration
@pytest.mark.skipif(not WECHAT_PDF.exists(), reason="wechat fixture missing")
def test_wechat_first_pages_row_count_smoke():
    """Smoke: first 5 pages extract with profile audit metadata."""
    import os

    os.environ["DOCMIRROR_MAX_PAGES"] = "5"
    try:
        extractor = CoreExtractor(max_page_concurrency=1)
        base = asyncio.run(extractor.extract(WECHAT_PDF))
        perf = base.metadata.get("perf_breakdown") or {}
        audit = perf.get("extraction_audit")
        assert audit is None or audit.get("profile_id") == "borderless_ledger_wechat"
        table_rows = sum(
            len(b.raw_content)
            for pg in base.pages
            for b in pg.blocks
            if b.block_type == "table" and isinstance(b.raw_content, list)
        )
        assert table_rows >= 80
    finally:
        os.environ.pop("DOCMIRROR_MAX_PAGES", None)
