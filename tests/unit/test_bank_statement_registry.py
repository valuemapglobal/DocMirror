# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Bank statement template registry and synthetic golden integration."""

from __future__ import annotations

import pytest
import os

from docmirror_enterprise.plugins.bank_statement.configs.registry import ensure_builtin_templates, get_registry, reset_registry


def test_builtin_templates_registered():
    reset_registry()
    reg = ensure_builtin_templates()
    ids = {t["template_id"] for t in reg.list_templates()}
    assert "generic" in ids
    assert "icbc_personal_v2022" in ids
    assert reg.template_count >= 3


def test_detector_extracts_three_transactions_from_clean_table():
    from docmirror_enterprise.plugins.bank_statement.configs.registry import ensure_builtin_templates, reset_registry
    from docmirror_enterprise.plugins.bank_statement.detectors.template_detector import BankStatementDetector

    reset_registry()
    ensure_builtin_templates()
    result = BankStatementDetector().detect(
        {
            "full_text": "中国工商银行\n个人客户交易明细\n户名：张三",
            "tables": [
                {
                    "headers": ["交易日期", "摘要", "收入", "支出", "余额"],
                    "rows": [
                        ["2024-01-01", "工资入账", "5000.00", "0.00", "8000.00"],
                        ["2024-01-02", "转账支出", "0.00", "200.00", "7800.00"],
                        ["2024-01-03", "消费", "0.00", "50.00", "7750.00"],
                    ],
                }
            ],
        }
    )
    assert result.get("template_id") in ("generic", "icbc_personal_v2022", "icbc_personal_v2020")
    assert len(result.get("transactions") or []) >= 3


def test_detector_extracts_from_compact_full_text_lines():
    from docmirror_enterprise.plugins.bank_statement.detectors.template_detector import BankStatementDetector

    result = BankStatementDetector().detect(
        {
            "full_text": (
                "中国工商银行\n个人客户交易明细\n"
                "2024-01-01\t工资入账\t5000.00\t0.00\t8000.00\n"
                "2024-01-02\t转账支出\t0.00\t200.00\t7800.00\n"
                "2024-01-03\t消费\t0.00\t50.00\t7750.00"
            ),
            "tables": [],
        }
    )
    assert len(result.get("transactions") or []) >= 3


@pytest.mark.skipif(
    not os.environ.get("DOCMIRROR_RUN_SYNTHETIC_TESTS"),
    reason="Synthetic PDF OCR test requires DOCMIRROR_RUN_SYNTHETIC_TESTS=1",
)
@pytest.mark.asyncio
async def test_bank_synthetic_extracts_transactions():
    from scripts.generate_synthetic_golden_pdfs import ensure_bank_synthetic
    from tests.golden.test_golden_matrix_benchmark import _parse_case

    pdf = ensure_bank_synthetic()
    pr = await _parse_case(pdf)
    assert pr.entities.document_type == "bank_statement"
    assert len(pr.extractor_full_text or pr.full_text) > 50

    structured = (pr.entities.domain_specific or {}).get("structured_data") or {}
    assert structured.get("template_id") in ("generic", "icbc_personal_v2022", "icbc_personal_v2020")
    assert int(structured.get("transaction_count") or 0) >= 3

    api = pr.to_api_dict()
    doc = api["data"]["document"]
    assert len(doc.get("pages") or []) >= 1
    pages = doc["pages"]
    has_table = any(p.get("tables") for p in pages)
    assert has_table, "expected ledger table in API pages"

    from docmirror.core.table.table_column_utils import effective_table_column_count

    tables = [t for p in pr.pages for t in p.tables]
    assert tables, "expected at least one table block"
    max_cols = max(effective_table_column_count(t) for t in tables)
    assert max_cols >= 5, f"expected native multi-column table, got max_cols={max_cols}"
    methods = {getattr(t, "method", "") for t in tables}
    assert "bank_statement_rebuild" not in methods or max_cols >= 5
