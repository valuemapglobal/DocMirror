# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parameterized bank statement style integration tests."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_style_matrix_synthetic_split_debit_credit():
    from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
    from docmirror.plugins.bank_statement.context import StyleContext
    from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
    from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry

    ctx = StyleContext(
        tables=[[
            ["交易日期", "摘要", "收入", "支出", "余额"],
            ["2024-01-01", "工资入账", "5000.00", "0.00", "8000.00"],
            ["2024-01-02", "转账支出", "0.00", "200.00", "7800.00"],
        ]],
        full_text="中国工商银行 个人客户交易明细",
        institution=None,
        page_count=1,
    )
    detection = BankStyleDetector().detect(ctx)
    assert detection.primary_style == "split_debit_credit"
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) >= 2
    assert records[0]["normalized"]["direction"] == "income"


@pytest.mark.integration
def test_style_matrix_synthetic_signed_amount():
    from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
    from docmirror.plugins.bank_statement.context import StyleContext
    from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
    from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
    from tests.unit.test_bank_styles_signed_amount import SIGNED_TABLE

    ctx = StyleContext(
        tables=SIGNED_TABLE,
        full_text="符号金额银行流水",
        institution=None,
        page_count=1,
    )
    detection = BankStyleDetector().detect(ctx)
    assert detection.primary_style == "signed_amount"
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) == 3
    assert records[0]["normalized"]["direction"] == "income"


@pytest.mark.integration
def test_style_matrix_synthetic_borderless_ocr():
    from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
    from docmirror.plugins.bank_statement.context import StyleContext
    from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
    from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
    from tests.unit.test_bank_styles_borderless_ocr import OCR_BORDERLESS_TABLE

    ctx = StyleContext(
        tables=OCR_BORDERLESS_TABLE,
        full_text="个人客户交易明细 中国工商银行",
        institution=None,
        page_count=1,
    )
    detection = BankStyleDetector().detect(ctx)
    assert detection.primary_style == "borderless_ocr"
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) >= 3
