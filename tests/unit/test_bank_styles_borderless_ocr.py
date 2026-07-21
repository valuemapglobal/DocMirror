# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for borderless_ocr bank statement style."""

from __future__ import annotations

import pytest

from docmirror.models.entities.parse_result import ExtractionMethod, ParserInfo
from docmirror.plugins.bank_statement.community_plugin import BANK_COLUMN_REGISTRY, BankStatementCommunityPlugin
from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
from docmirror.plugins.bank_statement.styles.borderless_ocr import (
    detect_headers_relaxed,
    is_ocr_dominant,
    strict_header_match_count,
    table_is_borderless_ocr,
)

OCR_BORDERLESS_TABLE = [[
    ["个人客户交易明细", "", "", ""],
    ["账号", "6217001234567890", "", ""],
    ["值日", "交易说明", "发生金额", "账面余领"],
    ["2024-01-01", "工资入账", "5000.00", "8000.00"],
    ["2024-01-02", "转账支出", "200.00", "7800.00"],
    ["2024-01-03", "消费", "50.00", "7750.00"],
]]

CLEAN_GRID_TABLE = [[
    ["交易日期", "摘要", "借方发生额", "贷方发生额", "余额"],
    ["2024-01-01", "工资", "0.00", "5000.00", "8000.00"],
]]


class _ParseResultStub:
    def __init__(self, extraction_method: ExtractionMethod):
        self.parser_info = ParserInfo(extraction_method=extraction_method)


def test_strict_header_match_fails_on_ocr_aliases():
    assert strict_header_match_count(OCR_BORDERLESS_TABLE, BANK_COLUMN_REGISTRY) < 3


def test_relaxed_header_detection_finds_columns():
    idx, headers, col_map = detect_headers_relaxed(OCR_BORDERLESS_TABLE, BANK_COLUMN_REGISTRY)
    assert idx == 2
    assert len(col_map) >= 2
    assert "date" in col_map
    assert headers


def test_table_is_borderless_ocr_shape():
    ctx = StyleContext(
        tables=OCR_BORDERLESS_TABLE,
        full_text="个人客户交易明细 中国工商银行",
        institution=None,
        page_count=1,
    )
    assert table_is_borderless_ocr(ctx) is True


def test_table_is_borderless_ocr_rejects_clean_grid():
    ctx = StyleContext(
        tables=CLEAN_GRID_TABLE,
        full_text="中国建设银行账户明细",
        institution="中国建设银行",
        page_count=1,
    )
    assert table_is_borderless_ocr(ctx) is False


def test_is_ocr_dominant_from_parse_result():
    ctx = StyleContext(
        tables=OCR_BORDERLESS_TABLE,
        full_text="",
        institution=None,
        page_count=1,
        parse_result=_ParseResultStub(ExtractionMethod.OCR),
    )
    assert is_ocr_dominant(ctx) is True


def test_detector_borderless_ocr_style():
    ctx = StyleContext(
        tables=OCR_BORDERLESS_TABLE,
        full_text="个人客户交易明细",
        institution=None,
        page_count=1,
    )
    result = BankStyleDetector().detect(ctx)
    assert result.primary_style == "borderless_ocr"
    assert "borderless_ocr" in result.parser_chain


def test_registry_borderless_ocr_records():
    ctx = StyleContext(
        tables=OCR_BORDERLESS_TABLE,
        full_text="个人客户交易明细",
        institution=None,
        page_count=1,
    )
    detection = BankStyleDetector().detect(ctx)
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) >= 3
    assert records[0]["normalized"].get("date") == "2024-01-01"
    assert records[0]["normalized"].get("amount") == pytest.approx(5000.0)
