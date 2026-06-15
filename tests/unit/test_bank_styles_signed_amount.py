# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for signed_amount bank statement style."""

from __future__ import annotations

import pytest

from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
from docmirror.plugins.bank_statement.styles.signed_amount import (
    parse_signed_amount,
    table_has_signed_amount_cells,
)
from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin

SIGNED_TABLE = [[
    ["交易日期", "摘要", "交易金额", "余额"],
    ["2024-01-01", "工资入账", "+5000.00", "5000.00"],
    ["2024-01-02", "消费", "-200.00", "4800.00"],
    ["2024-01-03", "转账", "-50.00", "4750.00"],
]]


def test_parse_signed_amount_income_and_expense():
    amount, direction = parse_signed_amount("+5000.00")
    assert amount == 5000.0
    assert direction == "income"

    amount, direction = parse_signed_amount("-200.00")
    assert amount == 200.0
    assert direction == "expense"


def test_table_has_signed_amount_cells():
    assert table_has_signed_amount_cells(SIGNED_TABLE) is True
    split_table = [[
        ["交易日期", "摘要", "收入", "支出", "余额"],
        ["2024-01-01", "工资", "5000.00", "0.00", "5000.00"],
    ]]
    assert table_has_signed_amount_cells(split_table) is False


def test_detector_signed_amount_style():
    ctx = StyleContext(
        tables=SIGNED_TABLE,
        full_text="某银行交易明细",
        institution=None,
        page_count=1,
    )
    result = BankStyleDetector().detect(ctx)
    assert result.primary_style == "signed_amount"


def test_registry_signed_amount_records():
    ctx = StyleContext(
        tables=SIGNED_TABLE,
        full_text="某银行交易明细",
        institution=None,
        page_count=1,
    )
    detection = BankStyleDetector().detect(ctx)
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) == 3
    assert records[0]["normalized"]["direction"] == "income"
    assert records[0]["normalized"]["amount"] == pytest.approx(5000.0)
    assert records[1]["normalized"]["direction"] == "expense"
    assert records[1]["normalized"]["amount"] == pytest.approx(200.0)
