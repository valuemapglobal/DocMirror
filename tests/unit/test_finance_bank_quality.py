# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for bank statement finance quality helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("docmirror_finance")

from docmirror_finance.plugins.bank_statement.plugin import BankStatementFinancePlugin


@pytest.fixture
def plugin():
    return BankStatementFinancePlugin()


def test_finance_plugin_is_full_not_baseline(plugin):
    assert plugin.edition == "finance"
    assert plugin.domain_name == "bank_statement"
    assert hasattr(plugin, "extract")


def test_quality_fields_exclude_empty_counterparty(plugin):
    from docmirror_finance.plugins.bank_statement import plugin as mod

    assert "counter_account" not in mod._QUALITY_FIELDS
    assert "date" in mod._QUALITY_FIELDS
    assert "amount" in mod._QUALITY_FIELDS


def test_field_coverage_uses_normalized_timestamp(plugin):
    records = [
        {"date": "2025-01-01", "timestamp": "2025-01-01 10:00:00", "summary": "x", "amount": 1.0, "balance": 1.0, "counter_party": "", "direction": "income"},
        {"date": "", "timestamp": "", "summary": "y", "amount": None, "balance": None, "counter_party": "", "direction": "other"},
    ]
    records_built = [{"row_index": i + 1, "raw": {}, "normalized": r} for i, r in enumerate(records)]
    quality, _, _ = plugin._compute_quality_bundle(records, records_built, parse_result=None)
    assert quality["field_coverage"]["timestamp"] == 0.5
    assert quality["field_confidence"]["timestamp"] <= quality["field_coverage"]["timestamp"]


def test_record_confidence_uses_row_index(plugin):
    records_built = [
        {"row_index": 1, "normalized": {"date": "2025-01-01", "amount": 1.0, "direction": "income", "timestamp": "2025-01-01"}},
        {"row_index": 2, "normalized": {"date": "2025-01-02", "amount": 2.0, "direction": "expense", "timestamp": "2025-01-02"}},
    ]
    records = [r["normalized"] for r in records_built]
    quality, _, _ = plugin._compute_quality_bundle(records, records_built, parse_result=None)
    indices = [item["index"] for item in quality["record_confidence"]]
    assert indices == [1, 2]


def test_validation_format_check_passes_valid_records(plugin):
    records = [
        {"date": "2025-01-01", "timestamp": "2025-01-01 10:00:00", "summary": "结息", "amount": 0.04, "balance": 100.0, "direction": "income"},
    ]
    summary = {"total_income": 0.04, "total_expense": 0.0, "total_rows": 1}
    validation = plugin._run_validation(records, summary)
    fmt = next(r for r in validation["rules"] if r["rule_code"] == "FORMAT_CHECK")
    assert fmt["status"] == "passed"


def test_cashflow_uses_direction(plugin):
    records = [
        {"date": "2025-01-01", "amount": 100.0, "direction": "income", "timestamp": "2025-01-01"},
        {"date": "2025-01-02", "amount": 40.0, "direction": "expense", "timestamp": "2025-01-02"},
    ]
    cashflow = plugin._analyze_cashflow(records)
    assert cashflow["income"]["total"] == 100.0
    assert cashflow["expense"]["total"] == 40.0


def test_finance_boc_pipe_text_quality_gate(plugin):
    from docmirror.plugins.bank_statement.extract_pipeline import run_bank_statement_extract
    from tests.unit.test_pipe_text_table_builder import _synthetic_boc_text

    rows = []
    for i in range(2, 76):
        rows.append(
            f"| {i:2d} |220401|220401|网上支付|    |ref{i}|        100.00|                  |"
            f"           {1000 + i}.00|ref |商户{i} |"
        )
    text = _synthetic_boc_text(rows)
    result = run_bank_statement_extract(None, text, plugin)
    records = [r["normalized"] for r in result.records]
    records_built = result.records
    quality, _, _ = plugin._compute_quality_bundle(
        records, records_built, parse_result=None, style_meta=result.style_meta,
    )
    assert quality["field_confidence"]["counter_party"] >= 0.95
    assert quality["overall_score"] >= 0.85


def test_income_classification_from_summary(plugin):
    records = [{"summary": "结息", "amount": 0.04, "direction": "income"}]
    cashflow = plugin._analyze_cashflow(records)
    assert cashflow["income"]["total"] == pytest.approx(0.04)
