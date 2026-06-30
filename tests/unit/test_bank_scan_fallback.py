# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Bank statement canonical style path tests (replaces raw scan-fallback detector tests)."""

from __future__ import annotations

from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin


def test_style_registry_extracts_from_valid_table_despite_noisy_full_text():
    text = (
        "中国工商银行\n个人客户交易明细\n"
        "2024-01-01工资入账5000.000.008000.00\n"
        "2024-01-02转账支出0.00200.007800.00\n"
        "2024-01-03消费0.0050.007750.00\n"
    )
    tables = [[
        ["交易日期", "摘要", "收入", "支出", "余额"],
        ["2024-01-01", "工资入账", "5000.00", "0.00", "8000.00"],
        ["2024-01-02", "转账支出", "0.00", "200.00", "7800.00"],
        ["2024-01-03", "消费", "0.00", "50.00", "7750.00"],
    ]]
    ctx = StyleContext(tables=tables, full_text=text, institution=None, page_count=1)
    detection = BankStyleDetector().detect(ctx)
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) >= 3
