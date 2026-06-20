# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for premium L2 KV enrich helpers."""

from __future__ import annotations

from docmirror.plugins._base.kv_community_enrich import (
    build_credit_sections_light,
    enrich_business_license_output,
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
        _parse_result=object(),
    )
    assert out["data"]["fields"]["uscc_valid"] is False
    assert "uscc_checksum_invalid" in out["status"]["warnings"]


def test_enrich_business_license_business_scope_section():
    out = enrich_business_license_output(
        {
            "data": {"fields": {"business_scope": "软件开发"}},
            "status": {"warnings": []},
        },
        _parse_result=object(),
    )
    sections = out["data"]["sections"]
    assert sections[0]["title"] == "经营范围"
    assert sections[0]["content"] == "软件开发"


def test_enrich_vat_adds_table_meta_when_records():
    out = enrich_vat_invoice_output(
        {
            "data": {"fields": {"invoice_number": "123"}, "records": [{"row_index": 1}]},
            "status": {"warnings": []},
        }
    )
    assert out["data"]["tables"][0]["row_count"] == 1


def test_build_credit_sections_from_markers():
    sections = build_credit_sections_light(object(), "个人基本信息 信息概要 查询记录")
    titles = {s["title"] for s in sections}
    assert "个人基本信息" in titles
    assert "查询记录" in titles
