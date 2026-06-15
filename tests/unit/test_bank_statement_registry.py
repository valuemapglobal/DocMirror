# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Bank statement template registry and canonical style integration."""

from __future__ import annotations

import os

import pytest

from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
from docmirror_enterprise.plugins.bank_statement.configs.registry import ensure_builtin_templates, reset_registry


def test_builtin_templates_registered():
    reset_registry()
    reg = ensure_builtin_templates()
    ids = {t["template_id"] for t in reg.list_templates()}
    assert "generic" in ids
    assert "icbc_personal_v2022" in ids
    assert reg.template_count >= 3


def test_style_registry_extracts_three_transactions_from_clean_table():
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
    assert detection.primary_style == "split_debit_credit"
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) >= 3


def test_legacy_detector_removed():
    with pytest.raises(ImportError):
        from docmirror_enterprise.plugins.bank_statement.detectors.template_detector import (  # noqa: F401
            BankStatementDetector,
        )


@pytest.mark.skipif(
    not os.environ.get("DOCMIRROR_RUN_SYNTHETIC_TESTS"),
    reason="Synthetic PDF OCR test requires DOCMIRROR_RUN_SYNTHETIC_TESTS=1",
)
@pytest.mark.asyncio
async def test_bank_synthetic_extracts_transactions():
    from docmirror.plugins.bank_statement.context import collect_tables_from_parse_result
    from scripts.generate_synthetic_golden_pdfs import ensure_bank_synthetic
    from tests.golden.test_golden_matrix_benchmark import _parse_case

    pdf = ensure_bank_synthetic()
    pr = await _parse_case(pdf)
    assert pr.entities.document_type == "bank_statement"
    assert len(pr.extractor_full_text or pr.full_text) > 50

    ctx = StyleContext(
        tables=collect_tables_from_parse_result(pr),
        full_text=pr.full_text or "",
        institution=None,
        page_count=len(pr.pages or []),
        parse_result=pr,
    )
    detection = BankStyleDetector().detect(ctx)
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) >= 3

    api = pr.to_api_dict()
    doc = api["data"]["document"]
    assert len(doc.get("pages") or []) >= 1
