# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Focused tests for the conservative Community precision upgrade."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins._base.base_table_parser import _is_summary_row
from docmirror.plugins._runtime.post_extract.hooks.community_business import _quality_summary
from docmirror.plugins._runtime.post_extract.hooks.community_precision import CommunityPrecisionHook


def _output(
    domain: str,
    *,
    fields: dict | None = None,
    records: list | None = None,
    extra_data: dict | None = None,
    warnings: list[str] | None = None,
) -> dict:
    data = {
        "fields": fields or {},
        "records": records or [],
        **(extra_data or {}),
    }
    return {
        "edition": "community",
        "plugin": {"name": domain},
        "status": {"success": True, "warnings": list(warnings or []), "errors": []},
        "data": data,
    }


def _record(*, trade_no: str = "T123456", timestamp: str = "2026-01-02T03:04:05", amount=10.5) -> dict:
    return {
        "raw": {},
        "normalized": {
            "trade_no": trade_no,
            "timestamp": timestamp,
            "amount": amount,
        },
    }


def _apply(output: dict, *, text: str = "", document_type: str | None = None) -> None:
    CommunityPrecisionHook().apply(
        SimpleNamespace(full_text=text),
        extracted=output,
        edition="community",
        document_type=document_type or output["plugin"]["name"],
    )


def test_summary_filter_preserves_payment_direction_rows() -> None:
    assert not _is_summary_row(["收入", "2026-01-02 03:04:05", "T1234567890123456", "10.00"])
    assert not _is_summary_row(["支出", "2026-01-02", "10.00"])
    assert _is_summary_row(["本页收入合计", "100.00"])
    assert _is_summary_row(["收入", "合计 100.00"])


def test_clean_payment_is_unchanged_and_hook_is_idempotent() -> None:
    output = _output("wechat_payment", records=[_record(), _record(trade_no="T654321")])
    data_before = deepcopy(output["data"])

    _apply(output)
    _apply(output)

    assert output["data"] == data_before
    assert not [warning for warning in output["status"]["warnings"] if warning.startswith("precision:")]


def test_payment_flags_missing_normalization_and_duplicate_trade_number() -> None:
    output = _output(
        "alipay_payment",
        records=[
            _record(trade_no="ORDER123", timestamp="bad-time", amount="10.00"),
            _record(trade_no="ORDER123", timestamp="", amount=None),
        ],
    )

    _apply(output)

    warnings = output["status"]["warnings"]
    assert "precision:normalization_failed:timestamp" in warnings
    assert "precision:normalization_failed:amount" in warnings
    assert "precision:duplicate_record:alipay_payment:trade_no" in warnings
    assert any("missing_required_record_field:timestamp" in warning for warning in warnings)


def test_bank_invariant_is_promoted_to_precision_warning_without_record_loss() -> None:
    records = [{"normalized": {"date": "2026-01-01", "amount": 10.0}}]
    output = _output(
        "bank_statement",
        records=records,
        warnings=["bank_invariant_failed:balance_chain:1/3"],
    )

    _apply(output)

    assert output["data"]["records"] == records
    assert "precision:invariant_failed:bank_invariant_failed:balance_chain:1/3" in output["status"]["warnings"]


def test_business_license_invalid_uscc_requires_review() -> None:
    output = _output(
        "business_license",
        fields={"unified_social_credit_code": "INVALIDCODE1234567"},
    )

    _apply(output)

    assert "precision:invalid_format:unified_social_credit_code" in output["status"]["warnings"]


def test_vat_checks_conditional_code_and_amount_equation() -> None:
    output = _output(
        "vat_invoice",
        fields={
            "invoice_number": "12345678",
            "amount_without_tax": "100.00",
            "tax_amount": "13.00",
            "total_amount": "120.00",
        },
    )

    _apply(output, text="增值税发票 发票代码")

    assert "precision:missing_required:invoice_code" in output["status"]["warnings"]
    assert "precision:invariant_failed:vat_amount_equation" in output["status"]["warnings"]


def test_vat_without_code_label_does_not_require_invoice_code() -> None:
    output = _output(
        "vat_invoice",
        fields={"invoice_number": "12345678901234567890", "total_amount": "113.00"},
    )

    _apply(output, text="全面数字化电子发票")

    assert "precision:missing_required:invoice_code" not in output["status"]["warnings"]


def test_credit_flags_invalid_month_and_conflicting_duplicate() -> None:
    output = _output(
        "credit_report",
        fields={"subject_name": "张三", "id_number": "11010519491231002X"},
        extra_data={
            "repayment_records": [
                {
                    "year": 2026,
                    "month": 13,
                    "status": "N",
                    "source_cell_refs": [{"grid_id": "grid-1"}],
                },
                {
                    "year": 2026,
                    "month": 13,
                    "status": "1",
                    "source_cell_refs": [{"grid_id": "grid-1"}],
                },
            ]
        },
    )

    _apply(output)

    assert "precision:invalid_format:repayment_month" in output["status"]["warnings"]
    assert "precision:duplicate_record:conflicting_repayment_status" in output["status"]["warnings"]


def test_precision_warning_forces_review_readiness() -> None:
    result = SimpleNamespace(confidence=1.0, parser_info=None, trust=None, pages=[])
    output = _output(
        "business_license",
        fields={"company_name": "示例公司"},
        warnings=["precision:invalid_format:unified_social_credit_code"],
    )

    quality = _quality_summary(
        result,
        output,
        contract_status="pass",
        missing_fields=[],
        missing_records=[],
    )

    assert quality["score"] >= 0.8
    assert quality["readiness"] == "review"
    assert quality["needs_review"] is True


def test_non_community_output_is_untouched() -> None:
    output = _output("wechat_payment", records=[])
    before = deepcopy(output)

    CommunityPrecisionHook().apply(
        ParseResult(),
        extracted=output,
        edition="enterprise",
        document_type="wechat_payment",
    )

    assert output == before
