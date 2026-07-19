# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enterprise bank statement quality / validation module tests."""

from __future__ import annotations

import pytest

pytest.importorskip("docmirror_enterprise", reason="enterprise package is not available in OSS CI")

from docmirror_enterprise.plugins.bank_statement.quality import compute_quality
from docmirror_enterprise.plugins.bank_statement.validation import run_validation


def test_run_validation_balance_chain_passes():
    records = [
        {
            "date": "2024-01-01",
            "timestamp": "2024-01-01",
            "amount": 100.0,
            "direction": "income",
            "balance": 100.0,
            "summary": "a",
        },
        {
            "date": "2024-01-02",
            "timestamp": "2024-01-02",
            "amount": 50.0,
            "direction": "expense",
            "balance": 50.0,
            "summary": "b",
        },
    ]
    summary = {"total_income": 100.0, "total_expense": 50.0}
    result = run_validation(records, summary)
    balance_rule = next(r for r in result["rules"] if r["rule_code"] == "BALANCE_CHAIN_CHECK")
    assert balance_rule["status"] == "passed"


def test_compute_quality_short_statement_uses_geo_mean_only():
    records = [
        {
            "row_index": 1,
            "normalized": {
                "date": "2024-01-01",
                "timestamp": "2024-01-01",
                "amount": 1.0,
                "summary": "x",
                "direction": "income",
            },
        },
    ]
    raw = {"transactions": [{"date": "2024-01-01", "amount": "1", "summary": "x"}]}
    quality = compute_quality(raw, [records[0]["normalized"]], records, [])
    assert quality["overall_score"] >= 0.8
