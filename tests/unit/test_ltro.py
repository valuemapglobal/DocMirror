# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Logical Table Reconstruction Orchestrator (LTRO)."""

from __future__ import annotations

from docmirror.plugins.bank_statement.ltro import reconstruct_tables
from tests.unit.test_pipe_text_table_builder import BOC_ROW1, _synthetic_boc_text

SAMPLE_OCR = """
交易明细清单
客户账号：6236030100000354601 客户姓名：于鑫日
交易日期 交易金额月收/支 账户余额 摘要
20220402支出 3.00 1070.13 POS消费
"""


def test_mirror_table_short_circuit():
    mirror = [[["日期", "金额"], ["2024-01-01", "1.00"]]]
    tables, meta = reconstruct_tables(mirror, "ignored")
    assert meta.source == "mirror_table"
    assert tables == mirror


def test_pipe_before_spaced_ocr():
    text = _synthetic_boc_text()
    tables, meta = reconstruct_tables([], text, page_count=1)
    assert meta.source == "pipe_text"
    assert len(tables[0]) >= 2


def test_pipe_fail_no_spaced_fallback():
    text = _synthetic_boc_text().split(BOC_ROW1)[0]
    tables, meta = reconstruct_tables([], text)
    assert tables == []
    assert meta.pipe_header_detected is True
    assert meta.pipe_parse_failed is True
    assert meta.source == "none"


def test_spaced_ocr_when_no_pipe():
    tables, meta = reconstruct_tables([], SAMPLE_OCR)
    assert meta.source == "spaced_ocr"
    assert len(tables[0]) >= 2
