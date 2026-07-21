# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Institution column maps + grid_standard / split_debit_credit integration."""

from __future__ import annotations

from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.institution import match_institution, normalize_table_headers
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
from docmirror.plugins.bank_statement.styles.grid_standard import normalize_split_debit_credit


def test_match_institution_ccb():
    variant = match_institution("中国建设银行账户明细信息")
    assert variant is not None
    assert variant.id == "ccb"
    assert variant.column_map.get("交易日期") == "交易时间"


def test_normalize_table_headers_ccb_alias():
    variant = match_institution("中国建设银行")
    tables = [[["交易日期", "摘要", "余额"], ["2024-01-01", "转账", "100.00"]]]
    normalized = normalize_table_headers(tables, variant=variant)
    assert normalized[0][0][0] == "交易时间"


def test_split_debit_credit_style_detection():
    ctx = StyleContext(
        tables=[[
            ["交易日期", "摘要", "收入", "支出", "余额"],
            ["2024-01-01", "工资入账", "5000.00", "0.00", "8000.00"],
        ]],
        full_text="中国工商银行 个人客户交易明细",
        institution=None,
        page_count=1,
    )
    result = BankStyleDetector().detect(ctx)
    assert result.primary_style == "split_debit_credit"


def test_style_registry_icbc_split_columns():
    ctx = StyleContext(
        tables=[[
            ["交易日期", "摘要", "收入", "支出", "余额"],
            ["2024-01-01", "工资入账", "5000.00", "0.00", "8000.00"],
            ["2024-01-02", "转账支出", "0.00", "200.00", "7800.00"],
            ["2024-01-03", "消费", "0.00", "50.00", "7750.00"],
        ]],
        full_text="中国工商银行\n个人客户交易明细\n户名：张三",
        institution=None,
        page_count=1,
    )
    detection = BankStyleDetector().detect(ctx)
    plugin = BankStatementCommunityPlugin()
    records, _identity = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) >= 3
    directions = {r["normalized"].get("direction") for r in records}
    assert "income" in directions
    assert "expense" in directions


def test_normalize_split_debit_credit_direct():
    plugin = BankStatementCommunityPlugin()
    norm = normalize_split_debit_credit(
        {
            "交易日期": "2024-01-02",
            "摘要": "转账支出",
            "收入": "0.00",
            "支出": "200.00",
            "余额": "7800.00",
        },
        plugin,
    )
    assert norm is not None
    assert norm["amount"] == 200.0
    assert norm["direction"] == "expense"
