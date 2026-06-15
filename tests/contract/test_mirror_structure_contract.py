# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests — parser_info.structure / SPE (ADR-M13-02)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytestmark = [pytest.mark.tier_contract]

from docmirror.core.bridge.parse_result_bridge import ParseResultBridge
from docmirror.core.extraction.extractor import CoreExtractor

BOC = Path("tests/fixtures/bank_statement/中国银行-南京创沃电气设备有限公司_1.pdf")
CREDIT = Path("tests/fixtures/synthetic/credit_report_section_smoke.pdf")

_REQUIRED_SPE_KEYS = frozenset({
    "primary",
    "competitors",
    "table_extraction",
    "sso_version",
})


def _assert_spe_shape(spe: dict) -> None:
    assert isinstance(spe, dict)
    missing = _REQUIRED_SPE_KEYS - set(spe.keys())
    assert not missing, f"SPE missing keys: {missing}"
    assert isinstance(spe["competitors"], dict)
    assert "H_pipe_grid" in spe["competitors"]


@pytest.mark.integration
def test_base_result_metadata_contains_structure():
    if not BOC.is_file():
        pytest.skip("missing BOC fixture")
    base = asyncio.run(CoreExtractor(max_page_concurrency=1).extract(BOC))
    spe = base.metadata.get("structure")
    _assert_spe_shape(spe)
    assert spe["primary"] in ("table_led", "section_led", "mixed")
    assert float(spe["competitors"]["H_pipe_grid"]) >= 0.85
    assert spe.get("table_extraction_skipped_reason") != "route_section_dominant_mismatch"


@pytest.mark.integration
def test_parse_result_bridge_preserves_structure():
    if not BOC.is_file():
        pytest.skip("missing BOC fixture")
    base = asyncio.run(CoreExtractor(max_page_concurrency=1).extract(BOC))
    pr = ParseResultBridge.from_base_result(base)
    assert pr.parser_info.structure is not None
    _assert_spe_shape(pr.parser_info.structure)


@pytest.mark.integration
def test_credit_report_section_spe_not_mismatch():
    if not CREDIT.is_file():
        pytest.skip("missing credit_report fixture")
    base = asyncio.run(CoreExtractor(max_page_concurrency=1).extract(CREDIT))
    spe = base.metadata.get("structure")
    _assert_spe_shape(spe)
    assert spe["primary"] == "section_led"
    assert spe.get("table_extraction_skipped_reason") != "route_section_dominant_mismatch"


@pytest.mark.integration
def test_api_meta_exports_structure():
    if not BOC.is_file():
        pytest.skip("missing BOC fixture")
    base = asyncio.run(CoreExtractor(max_page_concurrency=1).extract(BOC))
    pr = ParseResultBridge.from_base_result(base)
    api = pr.to_api_dict()
    assert "structure" in api.get("meta", {})
