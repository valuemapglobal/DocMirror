# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for canonical credit-report business assembly and audit."""

from __future__ import annotations

from types import SimpleNamespace

from docmirror.models.entities.parse_result import PageContent, ParserInfo
from docmirror.plugins.credit_report.business_assembly import assemble_credit_report_business


def _result(*, parsed_pages: int = 1, source_pages: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        pages=[PageContent(page_number=index, source_page_number=index) for index in range(1, parsed_pages + 1)],
        parser_info=ParserInfo(structure={"source_page_count": source_pages}),
        provenance=None,
        file_path="",
    )


def test_assembly_adds_normalized_view_without_removing_legacy_fields() -> None:
    account = {
        "source_structure_id": "account-1",
        "management_institution": {"normalized_value": "示例银行"},
        "account_status": {"normalized_value": "正常"},
        "open_date": {"normalized_value": "2024/1/2"},
        "loan_amount": {"normalized_value": "1,200.50"},
        "source": "scanned_local_structure",
        "page": 1,
        "confidence": 0.91,
    }

    assembled = assemble_credit_report_business(
        _result(),
        "个人信用报告（本人版）",
        report_subtype="personal_detail",
        content_mode="scanned_ocr",
        existing_collections={"credit_accounts": [account]},
    )

    actual = assembled["credit_accounts"][0]
    assert actual["management_institution"] == {"normalized_value": "示例银行"}
    assert actual["normalized"]["institution"] == "示例银行"
    assert actual["normalized"]["open_date"] == "2024-01-02"
    assert actual["normalized"]["loan_amount"] == 1200.5
    assert actual["source_refs"][0]["structure_id"] == "account-1"
    assert actual["extraction_status"] == "accepted"


def test_assembly_merges_same_natural_account_and_audits_conflict() -> None:
    existing = {
        "account_id": "scanned-id",
        "account_identifier": "ACC-001",
        "account_status": "正常",
        "source": "scanned_local_structure",
        "source_refs": [{"source": "local_structure_field_grid", "page": 2}],
        "confidence": 0.88,
    }
    incoming = {
        "account_id": "native-id",
        "account_identifier": "ACC001",
        "account_status": "逾期",
        "source": "native_text_narrative",
        "source_refs": [{"source": "native_text_narrative", "page": 2}],
        "confidence": 0.99,
    }

    # Inject the second adapter-shaped candidate through the existing list: the
    # merge rules are source-based and independent of which adapter supplied it.
    first = assemble_credit_report_business(
        _result(),
        "",
        report_subtype="personal_detail",
        content_mode="scanned_ocr",
        existing_collections={"credit_accounts": [existing, incoming]},
    )
    second = assemble_credit_report_business(
        _result(),
        "",
        report_subtype="personal_detail",
        content_mode="scanned_ocr",
        existing_collections={"credit_accounts": [existing, incoming]},
    )

    assert first == second
    assert len(first["credit_accounts"]) == 1
    assert first["credit_accounts"][0]["account_status"] == "正常"
    conflict = first["credit_extraction_audit"]["conflicts"][0]
    assert conflict["field"] in {"account_id", "account_status"}
    assert first["credit_extraction_audit"]["status"] == "review"


def test_assembly_normalizes_repayment_and_derives_overdue() -> None:
    repayment = {
        "year": "2024",
        "month": "8",
        "status": "2",
        "overdue_amount": "300.00",
        "source_cell_refs": [{"grid_id": "grid-1", "row": 1, "col": 8}],
        "confidence": 0.86,
    }

    assembled = assemble_credit_report_business(
        _result(),
        "",
        report_subtype="personal_detail",
        content_mode="scanned_ocr",
        existing_collections={"repayment_records": [repayment]},
    )

    actual = assembled["repayment_records"][0]
    assert actual["repayment_id"].startswith("credit_repayment:")
    assert actual["normalized"]["year"] == 2024
    assert actual["normalized"]["month"] == 8
    assert actual["normalized"]["overdue_amount"] == 300
    assert actual["source_refs"][0]["source"] == "repayment_micro_grid"
    assert assembled["overdue_records"][0]["normalized"]["overdue_level"] == 2


def test_assembly_marks_truncated_document_for_review() -> None:
    assembled = assemble_credit_report_business(
        _result(parsed_pages=2, source_pages=28),
        "个人信用报告（本人版）",
        report_subtype="personal_detail",
        content_mode="scanned_ocr",
    )

    audit = assembled["credit_extraction_audit"]
    assert audit["document_complete"] is False
    assert audit["parsed_source_page_count"] == 2
    assert audit["source_page_count"] == 28
    assert "document_truncated" in audit["issues"]
    assert audit["status"] == "review"


def test_assembly_reports_collection_evidence_coverage() -> None:
    assembled = assemble_credit_report_business(
        _result(),
        "",
        report_subtype="personal_detail",
        content_mode="scanned_ocr",
        existing_collections={
            "public_records": [
                {
                    "public_record_id": "public-1",
                    "record_type": "judgment",
                    "authority": "示例法院",
                    "confidence": 0.9,
                }
            ]
        },
    )

    audit = assembled["credit_extraction_audit"]
    assert audit["collections"]["public_records"]["count"] == 1
    assert audit["collections"]["public_records"]["evidence_coverage"] == 0.0
    assert "missing_evidence:public_records" in audit["issues"]
