# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for premium L2 KV enrich helpers."""

from __future__ import annotations

from types import SimpleNamespace

from docmirror.plugins._base.kv_community_enrich import (
    build_credit_sections_light,
    enrich_business_license_output,
    enrich_credit_report_output,
    enrich_vat_invoice_output,
    normalize_vat_fields,
    validate_uscc,
)


def test_normalize_vat_invoice_number_ocr():
    fields, warnings = normalize_vat_fields({"invoice_number": "12O3456"})
    assert fields["invoice_number"] == "1203456"
    assert any("vat_ocr_corrected" in w for w in warnings)


def test_validate_uscc_valid_sample():
    assert validate_uscc("91110000100000000R") is True


def test_validate_uscc_rejects_short_code():
    assert validate_uscc("123456") is False


def test_enrich_business_license_uscc_invalid():
    out = enrich_business_license_output(
        {"data": {"fields": {"unified_social_credit_code": "INVALIDCODE1234567"}}, "status": {"warnings": []}},
        parse_result=object(),
    )
    assert out["data"]["fields"]["uscc_valid"] is False
    assert "uscc_checksum_invalid" in out["status"]["warnings"]


def test_enrich_business_license_recovers_one_checksum_valid_uscc():
    out = enrich_business_license_output(
        {
            "data": {"fields": {"unified_social_credit_code": "代码：91 110000 100000000 R"}},
            "status": {"warnings": []},
        },
        parse_result=object(),
        full_text="统一社会信用代码 91110000100000000R",
    )
    assert out["data"]["fields"]["unified_social_credit_code"] == "91110000100000000R"
    assert out["data"]["fields"]["uscc_valid"] is True
    detail = out["data"]["field_details"]["unified_social_credit_code"]
    assert detail["raw"] == "代码：91 110000 100000000 R"
    assert detail["normalizer"] == "uscc.checksum.v1"


def test_enrich_business_license_business_scope_section():
    out = enrich_business_license_output(
        {
            "data": {"fields": {"business_scope": "软件开发"}},
            "status": {"warnings": []},
        },
        parse_result=object(),
    )
    sections = out["data"]["sections"]
    assert sections[0]["title"] == "经营范围"
    assert sections[0]["content"] == "软件开发"


def test_enrich_business_license_cleans_template_fields_and_restores_standard_notice():
    out = enrich_business_license_output(
        {
            "data": {
                "fields": {
                    "date_of_establishment": "2016年07月25日 后续OCR噪声",
                    "address": "深圳市测试路1号 大厦2层",
                    "registration_authority": "号 ★ OCR噪声",
                    "annual_inspection": "认证",
                }
            },
            "status": {"warnings": []},
        },
        parse_result=object(),
        full_text=(
            "重要提示 经营范围由章程确定 网址http://www.zcredit.com.cn 或扫描执照的二维码查询 "
            "商事主体须于每年1月1日-6月30日提交年度报告 登记机关 茶 场监 鑫 2016年 07月 日"
        ),
    )

    fields = out["data"]["fields"]
    assert fields["date_of_establishment"] == "2016-07-25"
    assert fields["address"] == "深圳市测试路1号大厦2层"
    assert fields["registration_authority"] == "深圳市市场监督管理局"
    assert fields["registration_date"] == "2016-07"
    assert fields["document_title"] == "营业执照"
    assert "annual_inspection" not in fields
    assert "企业信息公示暂行条例" in fields["important_notice"]
    assert out["data"]["sections"][0]["id"] == "important_notice"


def test_enrich_vat_adds_table_meta_when_records():
    out = enrich_vat_invoice_output(
        {
            "data": {"fields": {"invoice_number": "123"}, "records": [{"row_index": 1}]},
            "status": {"warnings": []},
        }
    )
    assert out["data"]["tables"][0]["row_count"] == 1
    assert out["data"]["line_items"] == [{"row_index": 1}]
    assert out["data"]["records"] == []


def test_build_credit_sections_from_markers():
    sections = build_credit_sections_light(object(), "个人基本信息 信息概要 查询记录")
    titles = {s["title"] for s in sections}
    assert "个人基本信息" in titles
    assert "查询记录" in titles


def test_enrich_credit_report_recovers_subject_identity_from_query_table_atoms():
    atoms = [
        {
            "id": "name-label",
            "page_id": "page:0001",
            "text": "被查询者姓名",
            "bbox": [43.0, 160.0, 101.0, 173.0],
        },
        {
            "id": "id-label-value",
            "page_id": "page:0001",
            "text": "被查询者证件号码 123456789012345 678",
            "bbox": [158.0, 160.0, 216.0, 192.0],
        },
        {
            "id": "name-value",
            "page_id": "page:0001",
            "text": "张三丰",
            "bbox": [43.0, 173.0, 101.0, 192.0],
        },
    ]
    result = SimpleNamespace(
        sections=[],
        pages=[],
        entities=SimpleNamespace(domain_specific={}),
        _runtime_mirror_cache={"evidence": {"text_atoms": atoms}},
    )

    output = enrich_credit_report_output({"data": {}}, parse_result=result)

    assert output["data"]["fields"]["subject_name"] == "张三丰"
    assert output["data"]["fields"]["id_number"] == "123456789012345678"
    assert output["data"]["field_details"]["subject_name"]["source"] == "mirror_text_atoms"
