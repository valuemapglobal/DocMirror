# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for DGAC domain contract validation."""

from __future__ import annotations

from docmirror.models.schemas.domain_contract_validator import (
    apply_domain_contract_validation,
    validate_domain_schema,
)


def test_validate_bank_statement_missing_identity_fields():
    payload = {
        "edition": "community",
        "plugin": {"name": "bank_statement"},
        "data": {
            "fields": {},
            "records": [
                {
                    "row_index": 1,
                    "raw": {"收入金额": "1.00"},
                    "normalized": {"date": "2023-01-01", "amount": 1.0},
                }
            ],
        },
        "status": {"success": True, "warnings": [], "errors": []},
    }
    report = validate_domain_schema(payload, "bank_statement")

    assert report.required_records_passed is True
    assert report.required_fields_passed is False
    assert any("required_any" in item for item in report.missing_fields)


def test_apply_domain_contract_validation_uses_validation_as_single_source():
    payload = {
        "edition": "community",
        "plugin": {"name": "bank_statement"},
        "data": {"fields": {}, "records": [{"normalized": {"date": "2023-01-01", "amount": 1.0}}]},
        "status": {"success": True, "warnings": [], "errors": []},
        "metadata": {},
    }
    report = apply_domain_contract_validation(payload, "bank_statement")

    assert report.status == "partial"
    assert payload["status"]["warnings"] == []
    assert payload["validation"]["domain_contract"]["status"] == "partial"
    assert "domain_contract_validation" not in payload["metadata"]


def test_apply_domain_contract_strips_stale_identity_warnings():
    payload = {
        "edition": "community",
        "plugin": {"name": "bank_statement"},
        "data": {
            "fields": {"bank_name": {"normalized_value": "中国农业银行"}},
            "records": [{"normalized": {"transaction_date": "2023-01-01", "amount": 1.0}}],
        },
        "status": {
            "success": True,
            "warnings": [
                "missing_identity_field:account_holder",
                "missing_identity_field:currency",
            ],
            "errors": [],
        },
        "metadata": {},
    }
    report = apply_domain_contract_validation(payload, "bank_statement")

    assert report.required_fields_passed is True
    assert not any(w.startswith("missing_identity_field:") for w in payload["status"]["warnings"])


def test_bank_domain_contract_accepts_normalized_amount():
    payload = {
        "edition": "community",
        "plugin": {"name": "bank_statement"},
        "data": {
            "fields": {"account_number": {"normalized_value": "6222000000000000"}},
            "records": [
                {"raw": {"收入金额": "100.00", "支出金额": "0"}, "normalized": {"date": "2023-01-01", "amount": 100.0}},
                {"raw": {"收入金额": "0", "支出金额": "50.00"}, "normalized": {"date": "2023-01-02", "amount": 50.0}},
            ],
        },
        "status": {"success": True, "warnings": [], "errors": []},
    }

    report = validate_domain_schema(payload, "bank_statement")
    assert report.required_records_passed is True


def test_vat_contract_allows_digital_invoice_without_invoice_code():
    payload = {
        "edition": "community",
        "plugin": {"name": "vat_invoice"},
        "data": {
            "fields": {
                "invoice_number": "12345678901234567890",
                "total_amount": "113.00",
            },
            "records": [],
        },
        "status": {"success": True, "warnings": [], "errors": []},
    }

    report = validate_domain_schema(payload, "vat_invoice")

    assert report.required_fields_passed is True
    assert "invoice_code" not in report.missing_fields


def test_credit_contract_accepts_person_or_enterprise_identifier() -> None:
    personal = {
        "data": {
            "fields": {"subject_name": "张三", "id_number": "11010519491231002X"},
            "credit_accounts": [],
            "credit_lines": [],
            "overdue_records": [],
            "inquiry_records": [],
            "credit_extraction_audit": {},
        },
        "status": {"success": True},
    }
    enterprise = {
        "data": {
            "fields": {
                "subject_name": "示例科技股份有限公司",
                "unified_social_credit_code": "91310000MA1FL6NCX7",
                "report_subtype": "enterprise",
            },
            "credit_accounts": [],
            "credit_lines": [],
            "overdue_records": [],
            "public_records": [],
            "credit_extraction_audit": {},
        },
        "status": {"success": True},
    }

    assert validate_domain_schema(personal, "credit_report").required_fields_passed is True
    assert validate_domain_schema(enterprise, "credit_report").required_fields_passed is True


def test_credit_contract_rejects_subject_without_any_identifier() -> None:
    payload = {"data": {"fields": {"subject_name": "张三"}}, "status": {"success": True}}

    report = validate_domain_schema(payload, "credit_report")

    assert report.required_fields_passed is False
    assert report.missing_fields == ["required_any:id_number,unified_social_credit_code,zhongzheng_code"]


def test_credit_v3_contract_checks_profile_collections_and_audit() -> None:
    payload = {
        "data": {
            "fields": {
                "subject_name": "张三",
                "id_number": "11010519491231002X",
                "report_subtype": "personal_detail",
            },
            "credit_accounts": [],
            "overdue_records": [],
        },
        "status": {"success": True},
    }

    report = validate_domain_schema(payload, "credit_report")

    assert report.contract_id == "credit_report.community.v3"
    assert report.required_records_passed is False
    assert report.missing_collections == ["repayment_records", "credit_extraction_audit"]
