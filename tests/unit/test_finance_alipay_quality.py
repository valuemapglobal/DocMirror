# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Finance Alipay quality metrics — coverage vs confidence consistency."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("docmirror_finance")

from docmirror_finance.plugins.alipay_payment.plugin import (
    AlipayPaymentFinancePlugin,
    _is_valid_timestamp,
)
from tests.contract.test_edition_schema_conformance import check_finance

pytestmark = pytest.mark.unit


def _sample_records(count: int = 3) -> tuple[list[dict], list[dict]]:
    """Return (normalized records, records_built with row_index)."""
    built = []
    for i in range(1, count + 1):
        norm = {
            "direction": "income",
            "counter_party": f"party-{i}",
            "description": f"desc-{i}",
            "payment_method": "余额",
            "amount": 100.0 + i,
            "trade_no": f"T{i:04d}",
            "merchant_no": f"M{i:04d}",
            "timestamp": f"2022-09-2{i}T10:30:39",
        }
        built.append({"row_index": i, "raw": {}, "normalized": norm})
    records = [b["normalized"] for b in built]
    return records, built


def _pages(*page_numbers: int, with_tables: bool = True) -> SimpleNamespace:
    tables = [SimpleNamespace()] if with_tables else []
    return SimpleNamespace(
        pages=[
            SimpleNamespace(page_number=n, tables=list(tables))
            for n in page_numbers
        ]
    )


def _minimal_finance_output(quality: dict, validation: dict) -> dict:
    """Minimal finance envelope for check_finance quality/validation rules."""
    return {
        "schema_version": "3.0",
        "edition": "finance",
        "scenario": {
            "business_type": "consumer_lending",
            "stage": "underwriting",
            "institution_type": "bank",
            "analysis_purpose": "credit_assessment",
        },
        "subject": {"subject_type": "individual", "subject_name": "测试主体"},
        "document_package": {
            "package_id": "pkg-1",
            "documents": [{"document_id": "doc-1", "document_type": "alipay_payment"}],
        },
        "quality_gate": {
            "passed": True,
            "minimum_quality_score": 0.7,
            "actual_quality_score": quality.get("overall_score", 0.9),
            "warnings": [],
        },
        "entity_graph": {"subjects": [], "accounts": []},
        "financial_indicators": {"cashflow": {"income": {}, "expense": {}}},
        "risk_signals": [],
        "fraud_signals": [],
        "cross_validation": {"enabled": True, "checks": []},
        "assessment": {"manual_review_required": False, "decision_strength": "normal"},
        "recommendation": {
            "suggested_action": "normal_review",
            "action_confidence": 0.9,
            "manual_review_required": False,
        },
        "explainability": {"decision_path": [], "evidence_chain": []},
        "report": {"summary": "", "risk_level": "low", "decision": "approve", "generated_at": ""},
        "quality": quality,
        "validation": validation,
        "security": {
            "sensitivity_level": "S3",
            "pii_detected": False,
            "sensitive_fields": [],
            "masking_required": False,
            "access_policy": "internal",
            "export_policy": "internal",
        },
        "review": {"required": False, "reason": [], "review_items": []},
        "output": {
            "json_available": True,
            "csv_available": True,
            "excel_available": True,
            "markdown_available": True,
            "report_available": True,
        },
        "audit": {
            "operation_logs": [{"action": "extract"}],
            "export_logs": [{"action": "export"}],
        },
        "metadata": {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "parser": "test",
            "parser_version": "3.0.0",
            "task_id": "t1",
            "file_id": "001",
        },
        "plugins": {"support_level": "F1"},
        "document": {
            "document_type": "alipay_payment",
            "page_count": len(quality.get("page_quality", [])) or 1,
        },
        "source": {
            "file_name": "test.pdf",
            "page_count": len(quality.get("page_quality", [])) or 1,
        },
        "processing": {
            "task_id": "t1",
            "batch_id": "",
            "status": "completed",
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:01+00:00",
            "duration_ms": 1000,
        },
        "classification": {"matched": True, "matched_document_type": "alipay_payment"},
        "extraction": {"records": []},
        "normalization": {"standard_records": []},
    }


class TestFinanceAlipayQualityBundle:
    def test_field_coverage_and_confidence_differ_for_bad_timestamp(self):
        records, built = _sample_records(2)
        records[0]["timestamp"] = "not-a-date"
        built[0]["normalized"]["timestamp"] = records[0]["timestamp"]

        quality, _, _ = AlipayPaymentFinancePlugin._compute_quality_bundle(
            records, built, _pages(1),
        )

        assert quality["field_coverage"]["timestamp"] == 1.0
        assert quality["field_confidence"]["timestamp"] == 0.5
        assert any(item["field"] == "timestamp" for item in quality["low_confidence_items"])

    def test_field_confidence_high_when_timestamps_valid(self):
        records, built = _sample_records(5)
        quality, _, _ = AlipayPaymentFinancePlugin._compute_quality_bundle(
            records, built, _pages(1, 2),
        )

        assert quality["field_coverage"]["timestamp"] == 1.0
        assert quality["field_confidence"]["timestamp"] == 1.0
        assert quality["overall_score"] >= 0.9
        assert quality["validation_passed"] is True

    def test_record_confidence_uses_row_index(self):
        records, built = _sample_records(5)
        _, record_confidence, _ = AlipayPaymentFinancePlugin._compute_quality_bundle(
            records, built, _pages(1),
        )

        indices = [item["index"] for item in record_confidence]
        assert indices == [1, 2, 3, 4, 5]
        assert all(item["confidence"] > 0.9 for item in record_confidence)

    def test_page_quality_includes_all_pages(self):
        records, built = _sample_records(2)
        _, _, page_quality = AlipayPaymentFinancePlugin._compute_quality_bundle(
            records, built, _pages(1, 2, 3),
        )

        assert len(page_quality) == 3
        assert all(p["score"] == 1.0 for p in page_quality)
        assert [p["page"] for p in page_quality] == [1, 2, 3]

    def test_page_without_tables_scores_zero(self):
        records, built = _sample_records(2)
        _, _, page_quality = AlipayPaymentFinancePlugin._compute_quality_bundle(
            records, built, _pages(1, 2, with_tables=False),
        )

        assert len(page_quality) == 2
        assert all(p["score"] == 0.0 for p in page_quality)
        assert all(p["issues"] == ["no_tables"] for p in page_quality)

    def test_quality_bundle_passes_schema_quality_checks(self):
        records, built = _sample_records(5)
        quality, _, _ = AlipayPaymentFinancePlugin._compute_quality_bundle(
            records, built, _pages(1, 2),
        )
        validation = AlipayPaymentFinancePlugin._run_validation(
            records, {"total_income": 500.0, "total_expense": 0.0},
        )
        envelope = _minimal_finance_output(quality, validation)
        errors = check_finance(envelope)
        quality_errors = [e for e in errors if e.startswith("[F3")]
        assert not quality_errors, quality_errors


class TestFinanceAlipayValidation:
    def test_format_check_accepts_normalized_timestamp(self):
        records, _ = _sample_records(2)
        records[0]["timestamp"] = "2022-09-2810:30:39"
        assert _is_valid_timestamp(records[0]["timestamp"])

        validation = AlipayPaymentFinancePlugin._run_validation(
            records, {"total_income": 200.0, "total_expense": 0.0},
        )
        fmt = next(r for r in validation["rules"] if r["rule_code"] == "FORMAT_CHECK")
        assert fmt["status"] == "passed"
        assert fmt["evidence"][0]["value"] == 0

    def test_time_order_check_fails_when_timestamps_unparseable(self):
        records = [
            {"timestamp": "bad-ts-1", "amount": 1.0, "direction": "income", "trade_no": "A"},
            {"timestamp": "bad-ts-2", "amount": 2.0, "direction": "income", "trade_no": "B"},
        ]
        validation = AlipayPaymentFinancePlugin._run_validation(
            records, {"total_income": 3.0, "total_expense": 0.0},
        )
        time_rule = next(r for r in validation["rules"] if r["rule_code"] == "TIME_ORDER_CHECK")
        assert time_rule["status"] == "failed"
        assert "parseable" in time_rule["message"]
        assert validation["passed"] is False

    def test_time_order_check_passes_with_valid_timestamps(self):
        records = [
            {"timestamp": "2022-09-28T10:30:39", "amount": 1.0, "direction": "income", "trade_no": "A"},
            {"timestamp": "2022-09-29T10:30:39", "amount": 2.0, "direction": "income", "trade_no": "B"},
        ]
        validation = AlipayPaymentFinancePlugin._run_validation(
            records, {"total_income": 3.0, "total_expense": 0.0},
        )
        time_rule = next(r for r in validation["rules"] if r["rule_code"] == "TIME_ORDER_CHECK")
        assert time_rule["status"] == "passed"
