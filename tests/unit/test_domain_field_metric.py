# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""domain_field_f1 metric tests (EFPA §5.2 domain plugin gate)."""

from __future__ import annotations

from docmirror.core.evaluation.metrics import (
    compute_metrics,
    domain_field_f1,
    extract_domain_fields,
)
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult


def test_domain_field_f1_perfect_match():
    expected = {"total_loan_balance": 0, "total_active_accounts": 5}
    actual = {"total_loan_balance": 0, "total_active_accounts": 5}
    assert domain_field_f1(expected, actual) == 1.0


def test_domain_field_f1_partial_match():
    expected = {"total_loan_balance": 0, "total_active_accounts": 5}
    actual = {"total_loan_balance": 0, "total_active_accounts": 3}
    score = domain_field_f1(expected, actual)
    assert score == 0.5


def test_domain_field_f1_extra_actual_fields_do_not_penalize():
    expected = {"报告编号": "202401010001", "被查询人姓名": "李四"}
    actual = {**expected, "逾期记录": "有"}
    assert domain_field_f1(expected, actual) == 1.0


def test_extract_domain_fields_from_structured_data():
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific={
                "structured_data": {
                    "derived_variables": {
                        "total_loan_balance": 100,
                        "total_card_balance": 0,
                    }
                }
            },
        ),
    )
    fields = extract_domain_fields(pr)
    assert fields["total_loan_balance"] == 100
    assert fields["total_card_balance"] == 0


def test_extract_domain_fields_from_top_level_entities():
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific={
                "报告编号": "202401010001",
                "被查询人姓名": "李四",
                "layout_profile": "credit_report_section_dominant",
            },
        ),
    )
    fields = extract_domain_fields(pr)
    assert fields["报告编号"] == "202401010001"
    assert "layout_profile" not in fields


def test_compute_metrics_includes_domain_field_f1():
    pr = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific={"derived_variables": {"total_loan_balance": 0}},
        ),
    )
    metrics = compute_metrics(
        pr,
        expected_domain_fields={"total_loan_balance": 0},
    )
    assert metrics["domain_field_f1"] == 1.0
