# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the additive Community document reading view."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from docmirror.models.entities.parse_result import PageContent, TextBlock, TextLevel
from docmirror.plugins._base.community_reading_view import (
    assemble_reading_view,
    finalize_community_reading_view,
)
from docmirror.plugins._runtime.post_extract.hooks.community_business import _build_dataset_catalog
from docmirror.plugins.credit_report.reading_view import build_credit_report_reading_view


def test_common_reading_view_orders_references_without_copying_values() -> None:
    parse_result = SimpleNamespace(
        pages=[
            PageContent(page_number=1, source_page_number=7),
            PageContent(page_number=2, source_page_number=8),
        ]
    )
    view = assemble_reading_view(
        parse_result,
        fields={"report_number": "R-001", "derived_value": "not displayed"},
        field_keys=["report_number"],
        sections=[
            {"id": "section:details", "title": "明细", "page_start": 2},
            {"id": "section:header", "title": "报告信息", "page_start": 1},
        ],
        tables=[
            {
                "id": "table:accounts",
                "section_id": "section:details",
                "title": "账户明细",
                "data_ref": {"type": "collection", "path": "/data/credit_accounts"},
            }
        ],
        notes=[
            {
                "id": "note:notice",
                "section_id": "section:details",
                "content": "说明：数据仅供参考。",
                "source_refs": [{"logical_page": 2, "source_page": 8}],
            }
        ],
    )

    assert [section["id"] for section in view["sections"]] == ["section:header", "section:details"]
    assert view["sections"][0]["source_page_start"] == 7
    assert view["sections"][1]["source_page_start"] == 8
    assert view["document_flow"] == [
        {"order": 1, "kind": "section", "ref_id": "section:header"},
        {"order": 2, "kind": "field_group", "field_keys": ["report_number"]},
        {"order": 3, "kind": "section", "ref_id": "section:details"},
        {"order": 4, "kind": "table", "ref_id": "table:accounts"},
        {"order": 5, "kind": "note", "ref_id": "note:notice"},
    ]
    assert "R-001" not in str(view["document_flow"])
    assert "credit_accounts" not in str(view["document_flow"])


def test_credit_reading_view_references_business_collections_and_extracts_notes() -> None:
    parse_result = SimpleNamespace(
        pages=[
            PageContent(
                page_number=1,
                source_page_number=1,
                texts=[
                    TextBlock(content="个人信用报告", level=TextLevel.H1),
                    TextBlock(
                        content="说明：本报告仅供被查询人了解本人信用状况。",
                        evidence_ids=["ev:note:1"],
                    ),
                ],
            ),
            PageContent(page_number=2, source_page_number=2),
        ]
    )
    data = {
        "fields": {
            "subject_name": "张三",
            "report_number": "R-001",
            "report_subtype": "personal_brief",
        },
        "sections": [
            {"id": "section:header", "title": "个人信用报告", "page_start": 1},
            {"id": "section:summary", "title": "信息概要", "page_start": 1},
            {"id": "section:credit", "title": "信贷记录", "page_start": 2},
        ],
        "tables": [],
        "credit_summary": {"account_count": 1},
        "credit_accounts": [
            {
                "account_id": "credit_account:1",
                "normalized": {"account_id": "credit_account:1", "status": "正常"},
                "source_refs": [{"page": 2, "source": "native_text"}],
            }
        ],
        "credit_lines": [],
        "repayment_records": [],
        "overdue_records": [],
        "inquiry_records": [],
        "public_records": [],
    }

    view = build_credit_report_reading_view(parse_result, data)

    tables = {table["id"]: table for table in view["tables"]}
    assert tables["table:credit_summary"]["data_ref"] == {
        "type": "object",
        "path": "/data/credit_summary",
    }
    assert tables["table:credit_accounts"]["data_ref"] == {
        "type": "collection",
        "path": "/data/credit_accounts",
    }
    assert "rows" not in tables["table:credit_accounts"]
    assert view["notes"][0]["content"] == "说明：本报告仅供被查询人了解本人信用状况。"
    assert view["notes"][0]["source_refs"] == [{"logical_page": 1, "source_page": 1, "evidence_ids": ["ev:note:1"]}]
    flow_refs = [item.get("ref_id") for item in view["document_flow"]]
    assert "table:credit_summary" in flow_refs
    assert "table:credit_accounts" in flow_refs
    assert view["notes"][0]["id"] in flow_refs
    assert "credit_account:1" not in str(view["document_flow"])


def test_reading_view_indexes_are_not_published_as_business_datasets() -> None:
    data = {
        "credit_accounts": [{"account_id": "credit_account:1"}],
        "notes": [{"id": "note:1", "content": "说明：测试"}],
        "document_flow": [{"order": 1, "kind": "note", "ref_id": "note:1"}],
    }

    datasets = _build_dataset_catalog(data, "credit_report")

    assert [dataset["id"] for dataset in datasets] == ["credit_accounts"]


@pytest.mark.parametrize("domain", ["bank_statement", "wechat_payment", "alipay_payment"])
def test_cashflow_plugins_share_one_reading_view_contract(domain: str) -> None:
    parse_result = SimpleNamespace(
        pages=[PageContent(page_number=1), PageContent(page_number=2)],
    )
    data = {
        "fields": {"account_holder": "张三", "account_number": "尾号1234", "currency": "CNY"},
        "records": [
            {
                "row_index": 1,
                "raw": {"金额": "10.00"},
                "normalized": {"date": "2026-07-01", "amount": 10.0},
                "source": {"page": 2},
            }
        ],
        "summary": {"total_rows": 1, "total_income": 10.0, "total_expense": 0.0, "net_flow": 10.0},
        "sections": [],
        "tables": [],
    }

    finalize_community_reading_view(parse_result, data, domain)

    assert data["tables"][0]["data_ref"] == {"type": "collection", "path": "/data/records"}
    assert "record_ids" not in data["tables"][0]
    assert data["tables"][0]["row_count"] == 1
    assert data["tables"][1]["data_ref"] == {"type": "object", "path": "/data/summary"}
    assert [item["order"] for item in data["document_flow"]] == list(range(1, 7))
    assert data["document_flow"][-1] == {
        "order": 6,
        "kind": "table",
        "ref_id": "table:transaction_summary",
    }


def test_vat_reading_view_points_to_line_items_without_copying_rows() -> None:
    parse_result = SimpleNamespace(pages=[PageContent(page_number=1)])
    data = {
        "fields": {
            "invoice_number": "001",
            "buyer_name": "购买方",
            "seller_name": "销售方",
            "total_amount": 106.0,
        },
        "line_items": [{"name": "服务", "amount": 100.0, "tax": 6.0}],
        "sections": [],
        "tables": [{"table_id": "vat_invoice_line_items", "title": "发票明细", "row_count": 1}],
    }

    finalize_community_reading_view(parse_result, data, "vat_invoice")

    table = data["tables"][0]
    assert table["id"] == "table:line_items"
    assert table["data_ref"] == {"type": "collection", "path": "/data/line_items"}
    assert "rows" not in table
    assert "服务" not in str(data["document_flow"])


def test_business_license_uses_content_ref_and_preserves_legacy_sections() -> None:
    parse_result = SimpleNamespace(pages=[PageContent(page_number=1)])
    data = {
        "fields": {
            "company_name": "示例公司",
            "business_scope": "软件开发",
            "important_notice": "重要提示正文",
        },
        "sections": [
            {"id": "important_notice", "title": "重要提示", "content": "重要提示正文"},
            {"id": "business_scope", "title": "经营范围", "content": "软件开发"},
        ],
        "tables": [],
    }

    finalize_community_reading_view(parse_result, data, "business_license")

    sections = {section["id"]: section for section in data["sections"]}
    assert sections["business_scope"]["content"] == "软件开发"
    assert sections["important_notice"]["content"] == "重要提示正文"
    assert data["notes"] == [
        {
            "id": "note:important_notice",
            "section_id": "important_notice",
            "content_ref": "/data/fields/important_notice",
            "source_refs": [],
            "order": 1,
        }
    ]
    assert "重要提示正文" not in str(data["document_flow"])


def test_generic_tables_reference_only_their_own_stable_record_ids() -> None:
    parse_result = SimpleNamespace(
        pages=[PageContent(page_number=1), PageContent(page_number=2), PageContent(page_number=3)]
    )
    data = {
        "fields": {"报告名称": "测试报告"},
        "records": [
            {"row_index": 1, "raw": {"值": "A"}, "normalized": {}, "source": {"table_id": "t1", "page": 2}},
            {"row_index": 2, "raw": {"值": "B"}, "normalized": {}, "source": {"table_id": "t2", "page": 3}},
        ],
        "sections": [
            {"id": "section:t1", "title": "第一表", "page_start": 2},
            {"id": "section:t2", "title": "第二表", "page_start": 3},
        ],
        "tables": [
            {"table_id": "t1", "headers": ["值"], "source_pages": [2], "row_count": 1},
            {"table_id": "t2", "headers": ["值"], "source_pages": [3], "row_count": 1},
        ],
    }

    finalize_community_reading_view(parse_result, data, "generic")

    tables = {table["id"]: table for table in data["tables"]}
    first_id, second_id = [record["id"] for record in data["records"]]
    assert tables["t1"]["record_ids"] == [first_id]
    assert tables["t2"]["record_ids"] == [second_id]
    assert tables["t1"]["section_id"] == "section:t1"
    assert tables["t2"]["section_id"] == "section:t2"
    assert data["document_flow"][0]["ref_id"] == "section:document_fields"
