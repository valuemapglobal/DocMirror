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


def test_apply_domain_contract_validation_adds_warnings():
    payload = {
        "edition": "community",
        "plugin": {"name": "bank_statement"},
        "data": {"fields": {}, "records": [{"normalized": {"date": "2023-01-01", "amount": 1.0}}]},
        "status": {"success": True, "warnings": [], "errors": []},
        "metadata": {},
    }
    report = apply_domain_contract_validation(payload, "bank_statement")

    assert report.status == "partial"
    assert any("partial_missing_required" in w for w in payload["status"]["warnings"])
    assert payload["validation"]["domain_contract"]["status"] == "partial"


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
