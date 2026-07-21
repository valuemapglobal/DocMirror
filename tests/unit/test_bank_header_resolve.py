# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for unified bank header resolution."""

from __future__ import annotations

from docmirror.plugins.bank_statement.community_plugin import BANK_COLUMN_REGISTRY
from docmirror.plugins.bank_statement.header_resolve import (
    detect_headers,
    normalize_header_cell,
    registry_strict_header_match_count,
)

OCR_HEADERS = ["值日", "交易说明", "发生金额", "账面余领"]
CLEAN_HEADERS = ["交易日期", "摘要", "借方发生额", "贷方发生额", "余额"]


def test_normalize_header_cell_maps_ocr_variants():
    assert normalize_header_cell("值日") == "交易日期"
    assert normalize_header_cell("账面余领") == "余额"


def test_registry_strict_fails_on_ocr_aliases():
    table = [[OCR_HEADERS]]
    assert registry_strict_header_match_count(table, BANK_COLUMN_REGISTRY) < 3


def test_detect_headers_succeeds_on_ocr_aliases():
    table = [[OCR_HEADERS]]
    header = detect_headers(table, BANK_COLUMN_REGISTRY, prefer_strict=True)
    assert header is not None
    assert len(header.col_map) >= 3


def test_compact_date_row_detection():
    from docmirror.plugins.bank_statement.row_extract import row_has_transaction_data

    row = ["20220505", "152713", "代付", "+800.00", "805.72", "财付通", "电子商务", ""]
    assert row_has_transaction_data(row) is True


def test_unicode_header_normalization():
    assert normalize_header_cell("交易⽇期") == "交易日期"
    assert normalize_header_cell("本次余额") == "余额"

    table = [[CLEAN_HEADERS]]
    header = detect_headers(table, BANK_COLUMN_REGISTRY, prefer_strict=True)
    assert header is not None
    assert header.mode == "strict"
    assert len(header.col_map) >= 3
