# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Bank statement detector scan-fallback tests."""

from __future__ import annotations

from docmirror_enterprise.plugins.bank_statement.detectors.template_detector import BankStatementDetector


def test_detector_prefers_full_text_when_table_yields_fewer_rows():
    text = (
        "中国工商银行\n个人客户交易明细\n"
        "2024-01-01工资入账5000.000.008000.00\n"
        "2024-01-02转账支出0.00200.007800.00\n"
        "2024-01-03消费0.0050.007750.00\n"
    )
    # Junk single-row table (scan OCR artifact)
    tables = [
        {
            "headers": ["col"],
            "rows": [["2024-01-03消费0.0050.007750.00"]],
        }
    ]
    result = BankStatementDetector().detect({"full_text": text, "tables": tables})
    assert len(result.get("transactions") or []) >= 3
