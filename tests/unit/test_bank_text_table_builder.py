# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for OCR text → synthetic table builder."""

from __future__ import annotations

from docmirror.plugins.bank_statement.text_table_builder import (
    build_tables_from_ocr_text,
    looks_like_bank_ocr_text,
)

SAMPLE_OCR = """
交易明细清单
客户账号：6236030100000354601 客户姓名：于鑫日
交易日期 交易金额月收/支 账户余额 摘要
20220402支出 3.00 1070.13 POS消费
20220325收入-50.0084.13网络收款
20220403支出 18.90 1051.23 网络付款 美团支付
"""


def test_looks_like_bank_ocr_text():
    assert looks_like_bank_ocr_text(SAMPLE_OCR) is True
    assert looks_like_bank_ocr_text("random invoice text") is False


def test_build_tables_from_ccb_ocr_line():
    line = "6228480120270090963王街电子汇出20210219455-14,300.00电子汇出415,708.06"
    tables = build_tables_from_ocr_text(
        "中国建设银行个人活期账户交易明细\n" + line
    )
    assert len(tables) == 1
    row = tables[0][1]
    assert row[0] == "2021-02-19"
    assert row[2].startswith("-")


def test_build_tables_from_ocr_text():
    tables = build_tables_from_ocr_text(SAMPLE_OCR)
    assert len(tables) == 1
    assert len(tables[0]) >= 4
    headers = tables[0][0]
    assert "交易日期" in headers
    row = tables[0][1]
    assert row[0] == "2022-04-02"
    assert row[2].startswith("-")
