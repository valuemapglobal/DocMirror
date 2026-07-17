# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Community 6+1 consumer-facing business projection tests."""

from __future__ import annotations

from copy import deepcopy

import pytest

from docmirror.models.edition_serializer import EditionContext, edition_serializer
from docmirror.models.entities.domain_result import DomainExtractionResult, DomainQuality
from docmirror.models.entities.parse_result import (
    CellValue,
    DocumentEntities,
    KeyValuePair,
    PageContent,
    ParseResult,
    ResultStatus,
    TableBlock,
    TableRow,
    TextBlock,
    TextLevel,
)
from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.plugins._runtime.runner import clear_run_cache, run_plugin_extract_sync
from docmirror.quality.field_details import compact_community_field_projection
from docmirror.server.output_builder import build_community_output


def _resolve_pointer(payload: object, pointer: str):
    current = payload
    for token in pointer.lstrip("/").split("/") if pointer else []:
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        else:
            current = current[token]
    return current


def _mirror(document_type: str) -> ParseResult:
    return ParseResult(
        status=ResultStatus.SUCCESS,
        entities=DocumentEntities(document_type=document_type),
    )


@pytest.mark.parametrize(
    "domain",
    (
        "bank_statement",
        "wechat_payment",
        "alipay_payment",
        "vat_invoice",
        "business_license",
        "credit_report",
    ),
)
def test_six_core_plugins_emit_consistent_business_layer(domain: str):
    clear_run_cache()
    out = run_plugin_extract_sync(_mirror(domain), edition="community")
    assert out is not None
    assert out["schema_version"] == "2.2"
    assert "plugins" not in out
    assert out["business"]["version"] == "community.business.v1"
    assert out["business"]["summary"]
    assert out["quality"]["readiness"] in {"ready", "review", "insufficient"}
    assert "data_dictionary" in out["data"]
    assert "field_details" in out["data"]
    assert "datasets" in out["data"]
    assert "domain_contract" in out["validation"]


def test_generic_fallback_recovers_text_kv_tables_outline_and_sources():
    page = PageContent(
        page_number=1,
        key_values=[
            KeyValuePair(
                key="客户名称",
                value="上海示例科技有限公司",
                confidence=0.98,
                bbox=[10, 20, 200, 40],
                evidence_ids=["ev:kv:1"],
            )
        ],
        texts=[TextBlock(content="费用明细", level=TextLevel.H1, bbox=[10, 60, 200, 80])],
        tables=[
            TableBlock(
                table_id="p1_expenses",
                headers=["日期", "金额", "用途"],
                rows=[
                    TableRow(
                        cells=[
                            CellValue(text="2026-07-01"),
                            CellValue(text="1,280.50"),
                            CellValue(text="差旅费"),
                        ]
                    )
                ],
            )
        ],
    )
    result = ParseResult(
        status=ResultStatus.SUCCESS,
        pages=[page],
        entities=DocumentEntities(document_type="expense_report"),
    )

    out = build_community_output(result, "报销单号：BX-20260701\n部门：销售部")

    assert out is not None
    data = out["data"]
    assert data["fields"]["报销单号"] == "BX-20260701"
    assert data["fields"]["部门"] == "销售部"
    assert data["field_details"]["部门"]["value_ref"] == "/data/fields/部门"
    assert "normalized" not in data["field_details"]["部门"]
    assert "raw" not in data["field_details"]["部门"]
    assert data["field_details"]["客户名称"]["source_refs"][0]["evidence_ids"] == ["ev:kv:1"]
    for legacy_key in ("normalized_fields", "field_schema", "field_metadata", "identities"):
        assert legacy_key not in data
    assert data["tables"][0]["table_id"] == "p1_expenses"
    assert data["sections"][0]["title"] == "费用明细"
    assert data["columns"]["日期"]["type"] == "date"
    assert data["records"][0]["normalized"]["金额"]["value"] == 1280.5
    assert out["business"]["dimensions"]["adaptive_profile"]["document_shape"] == "mixed_document"
    assert out["quality"]["evidence"]["field_source_coverage"] > 0
    assert data["datasets"] == [
        {
            "id": "records",
            "label": "结构化记录",
            "kind": "generic_record",
            "role": "primary",
            "data_ref": "/data/records",
            "row_count": 1,
            "columns_ref": "/data/data_dictionary/record_columns",
        }
    ]
    assert _resolve_pointer(out, data["datasets"][0]["data_ref"]) is data["records"]
    assert "rows" not in data["datasets"][0]

    legacy = deepcopy(out)
    legacy["schema_version"] = "2.1"
    legacy["plugins"] = {
        legacy["classification"]["matched_document_type"]: {
            "display_name": legacy["plugin"]["display_name"],
            "edition": "community",
        }
    }
    legacy["business"]["metric_cards"] = []
    legacy["business"]["readiness"] = legacy["quality"]["readiness"]
    for key, detail in legacy["data"]["field_details"].items():
        value = legacy["data"]["fields"][key]
        legacy["data"]["field_details"][key] = {
            "raw": str(value),
            "normalized": value,
            "normalizer": detail["normalizer"],
            "confidence": detail["confidence"],
            "source_refs": detail["source_refs"],
            "review": detail["review"],
        }
    validation = validate_projection_payload("community", legacy)
    assert validation.valid, validation.errors


def test_compact_field_details_keep_only_materially_different_raw_value():
    fields, details = compact_community_field_projection(
        {
            "fields": {
                "金额/元": {
                    "raw_value": "1,280.50",
                    "normalized_value": 1280.5,
                    "normalizer": "amount.cny.v1",
                    "confidence": 0.98,
                    "source_refs": [{"page": 1}],
                }
            }
        }
    )

    assert fields == {"金额/元": 1280.5}
    assert details["金额/元"]["value_ref"] == "/data/fields/金额~1元"
    assert details["金额/元"]["raw"] == "1,280.50"
    assert "normalized" not in details["金额/元"]


def test_serializer_preserves_domain_structured_extensions():
    dec = DomainExtractionResult(
        document_type="generic",
        entities={"name": "张三"},
        structured_data={
            "records": [],
            "columns": {"金额": {"type": "amount"}},
            "identities": {"name": {"value": "张三"}},
            "custom_records": [{"id": 1}],
        },
        quality=DomainQuality(validation_passed=True),
    )
    out = edition_serializer(dec, context=EditionContext(document_name="sample.pdf"))
    assert out["data"]["columns"]["金额"]["type"] == "amount"
    assert out["data"]["identities"]["name"]["value"] == "张三"
    assert out["data"]["custom_records"] == [{"id": 1}]


def test_generic_fallback_recovers_repeated_date_led_rows_without_table_geometry():
    result = _mirror("generic")
    text = "\n".join(
        [
            "日期",
            "摘要",
            "金额",
            "余额",
            "2026-07-01",
            "工资",
            "1000.00",
            "1200.00",
            "2026-07-02",
            "餐费",
            "50.00",
            "1150.00",
            "2026-07-03",
            "交通",
            "20.00",
            "1130.00",
        ]
    )
    clear_run_cache()
    out = build_community_output(result, text)
    assert out is not None
    assert len(out["data"]["records"]) == 3
    assert out["data"]["tables"][0]["recovery_method"] == "repeated_date_anchor"
    assert out["data"]["columns"]["日期"]["type"] == "date"
    assert out["data"]["records"][0]["normalized"]["金额"]["value"] == 1000.0


def test_business_license_text_fallback_handles_word_per_line_layout():
    from docmirror.plugins._base.kv_community_extract import _recover_identity_fields_from_text
    from docmirror.plugins.business_license.community_plugin import plugin

    text = """
    Business\nLicense\nUnified\nSocial\nCredit\nCode:\n91310000MA1FL6NCX7
    Company\nName:\nShanghai\nDongfang\nTechnology\nCo.,\nLtd.
    Company\nType:\nLimited\nLiability\nCompany
    Legal\nRepresentative:\nWang\nFang
    Registered\nCapital:\nCNY\n10,000,000
    Establishment\nDate:\n2018-03-15
    """
    fields = _recover_identity_fields_from_text(text, plugin.identity_fields)
    assert fields["unified_social_credit_code"] == "91310000MA1FL6NCX7"
    assert fields["company_name"] == "Shanghai Dongfang Technology Co., Ltd."
    assert fields["registered_capital"] == "CNY 10,000,000"
    assert fields["date_of_establishment"] == "2018-03-15"


def test_cashflow_business_summary_is_descriptive_and_typed():
    result = _mirror("bank_statement")
    output = {
        "schema_version": "2.0",
        "edition": "community",
        "document": {"document_type": "bank_statement"},
        "plugin": {"name": "bank_statement"},
        "status": {"success": True, "warnings": [], "errors": []},
        "data": {
            "fields": {"account_holder": "张三"},
            "records": [
                {
                    "row_index": 1,
                    "raw": {},
                    "normalized": {
                        "date": "2026-07-01",
                        "direction": "income",
                        "amount": 1000.0,
                        "counter_party": "甲公司",
                    },
                },
                {
                    "row_index": 2,
                    "raw": {},
                    "normalized": {
                        "date": "2026-07-02",
                        "direction": "expense",
                        "amount": 200.0,
                        "counter_party": "乙公司",
                    },
                },
            ],
            "sections": [],
            "tables": [],
            "line_items": [],
            "summary": {"total_rows": 2},
        },
        "metadata": {},
    }
    from docmirror.plugins._runtime.post_extract.hooks.community_business import (
        CommunityBusinessProjectionHook,
    )

    CommunityBusinessProjectionHook().apply(
        result,
        extracted=output,
        edition="community",
        document_type="bank_statement",
    )
    assert output["business"]["key_metrics"]["net_flow"] == 800.0
    assert output["business"]["dimensions"]["period"] == {
        "start": "2026-07-01",
        "end": "2026-07-02",
    }
    assert output["business"]["dimensions"]["top_counterparties"][0]["total_amount"] == 1000.0
    assert output["schema_version"] == "2.2"
    assert output["data"]["datasets"][0]["kind"] == "transaction"
    assert "metric_cards" not in output["business"]
    assert "readiness" not in output["business"]


def test_vat_uses_line_items_as_single_consumer_dataset():
    result = _mirror("vat_invoice")
    output = {
        "schema_version": "2.0",
        "edition": "community",
        "document": {"document_type": "vat_invoice", "document_name": "invoice.pdf"},
        "plugin": {"name": "vat_invoice"},
        "status": {"success": True, "warnings": [], "errors": []},
        "data": {
            "fields": {
                "invoice_code": "123",
                "invoice_number": "456",
                "invoice_date": "2026-07-01",
                "issue_date": "2026-07-01",
                "total_amount": 10.6,
            },
            "records": [
                {
                    "row_index": 1,
                    "raw": {"名称": "服务"},
                    "normalized": {"name": "服务", "amount": 10.0, "tax": 0.6},
                }
            ],
            "line_items": [{"name": "服务", "amount": 10.0, "tax": 0.6}],
            "sections": [],
            "tables": [],
            "summary": {"total_rows": 1},
            "field_metadata": {
                "invoice_code": {"source": "ocr", "page": 1},
                "issue_date": {"source": "ocr", "page": 1},
            },
        },
        "metadata": {
            "field_provenance": {
                "invoice_code": {"source": "ocr", "page": 1},
                "issue_date": {"source": "ocr", "page": 1},
            }
        },
    }
    from docmirror.plugins._runtime.post_extract.hooks.community_business import CommunityBusinessProjectionHook

    CommunityBusinessProjectionHook().apply(
        result,
        extracted=output,
        edition="community",
        document_type="vat_invoice",
    )

    assert [item["id"] for item in output["data"]["datasets"]] == ["line_items"]
    assert _resolve_pointer(output, output["data"]["datasets"][0]["data_ref"]) is output["data"]["line_items"]
    assert output["data"]["records"] == []
    assert output["data"]["data_dictionary"]["record_count"] == 1
    assert "issue_date" not in output["data"]["fields"]
    assert output["data"]["field_details"]["invoice_code"]["source_refs"] == [
        {"source": "ocr", "page": 1}
    ]
    assert "field_metadata" not in output["data"]
    assert "field_provenance" not in output["metadata"]


def test_credit_repayments_only_live_under_data():
    from docmirror.plugins._base.kv_community_enrich import enrich_credit_report_output

    result = ParseResult(
        status=ResultStatus.SUCCESS,
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific={"credit_repayment_records": [{"year": 2026, "month": 1, "status": "N"}]},
        ),
    )
    output = {"data": {}}

    enrich_credit_report_output(output, parse_result=result)

    assert output["data"]["repayment_records"] == [{"year": 2026, "month": 1, "status": "N"}]
    assert "repayment_records" not in output


def test_sensitive_field_dictionary_is_reference_only_and_mask_aware():
    result = _mirror("generic")
    out = {
        "schema_version": "2.0",
        "edition": "community",
        "document": {"document_type": "generic", "document_name": "identity.pdf"},
        "plugin": {"name": "generic"},
        "status": {"success": True, "warnings": [], "errors": []},
        "data": {
            "fields": {"id_number": "110101199001011234"},
            "records": [],
            "sections": [],
            "tables": [],
            "line_items": [],
            "summary": {"total_rows": 0},
        },
        "metadata": {},
    }
    from docmirror.plugins._runtime.post_extract.hooks.community_business import CommunityBusinessProjectionHook

    CommunityBusinessProjectionHook().apply(
        result,
        extracted=out,
        edition="community",
        document_type="generic",
    )

    schema = out["data"]["data_dictionary"]["fields"]["id_number"]
    assert schema["sensitive"] is True
    assert schema["mask"] == "keep_first_3_last_4"
    assert schema["value_ref"] == "/data/fields/id_number"
    assert _resolve_pointer(out, schema["value_ref"]) == "110101199001011234"
    assert "value" not in schema
