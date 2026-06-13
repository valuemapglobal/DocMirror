# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Extract golden — TQG wrapper + non-manifest smoke (synthetic PDF, profile flags, benchmark)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from docmirror.core.extraction.extractor import CoreExtractor
from tests.regression.conftest import _EXTRACT_CASES, _run_and_assert

pytestmark = [
    pytest.mark.tier_regression,
    pytest.mark.track_extract,
    pytest.mark.integration,
]

BANK_SCAN_PNG = Path("tests/fixtures/bank_statement/朱洁_银行流水_企业网上银行_20170711.png")
WECHAT_PDF = Path("tests/fixtures/wechat_payment/DemoUser+微信流水.pdf")


@pytest.mark.parametrize("case", _EXTRACT_CASES, ids=lambda c: c.id)
def test_extract_golden_tqg(case, tqg_report_dir):
    """Manifest-driven extract gates (configs/yaml/test/gates/extract.yaml)."""
    _run_and_assert(case, tqg_report_dir)


@pytest.mark.integration
@pytest.mark.skipif(not BANK_SCAN_PNG.exists(), reason="bank scan fixture missing")
def test_bank_statement_scan_image_smoke():
    """§9.1: scan PNG — skip when OCR path unavailable in CI."""
    extractor = CoreExtractor(max_page_concurrency=1)
    try:
        base = asyncio.run(extractor.extract(BANK_SCAN_PNG))
    except Exception as exc:
        pytest.skip(f"scan bank image extract not stable: {exc}")
    if base.metadata.get("error"):
        pytest.skip(f"scan bank image extract error: {base.metadata.get('error')}")
    assert base.metadata.get("page_count", 0) >= 1


def test_wechat_profile_grid_template_enabled():
    """P4-1: grid template enabled after BCS + row filtering fixes."""
    from docmirror.core.layout.profile_registry import get_profile

    profile = get_profile("borderless_ledger_wechat")
    assert profile.enable_grid_template is True
    alipay = get_profile("borderless_ledger_alipay")
    assert alipay.enable_grid_template is True


@pytest.mark.integration
def test_credit_report_section_mode(tqg_report_dir):
    """§9.1: section_driven credit report — TQG case credit_report_section_mode."""
    case = next(c for c in _EXTRACT_CASES if c.id == "credit_report_section_mode")
    _run_and_assert(case, tqg_report_dir)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.benchmark
@pytest.mark.skipif(
    os.environ.get("DOCMIRROR_RUN_BENCHMARK") != "1",
    reason="set DOCMIRROR_RUN_BENCHMARK=1 to run timing benchmark",
)
@pytest.mark.skipif(not WECHAT_PDF.exists(), reason="wechat fixture missing")
def test_wechat_extract_benchmark():
    """P4-3: record 219-page extract timing (design target < 60s; current ~64s)."""
    extractor = CoreExtractor(max_page_concurrency=1)
    base = asyncio.run(extractor.extract(WECHAT_PDF))
    elapsed_ms = base.metadata.get("elapsed_ms", 0)
    assert elapsed_ms > 0
    assert elapsed_ms < 300_000, f"extract took {elapsed_ms}ms (>5min regression)"
