# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public cross-document precision benchmark for the Generic fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.server.output_builder import build_community_output
from tests.contract.test_edition_schema_conformance import check_community

pytestmark = [
    pytest.mark.integration,
    pytest.mark.tier_regression,
    pytest.mark.track_edition,
]

FIXTURE_DIR = Path("tests/fixtures/text_samples")

EXPECTED_FIELDS = {
    "insurance_policy": {
        "保险单号": "P20260101001",
        "被保险人": "赵六",
        "保险人": "某某人寿保险股份有限公司",
        "保险期间": "2026-01-01 至 2027-01-01",
        "保费": 5000.0,
    },
    "household_registration": {
        "户号": "012345678",
        "户主姓名": "王五",
        "与户主关系": "本人",
        "户口登记机关": "某某派出所",
        "登记日期": "2010-01-01",
    },
    "loan_contract": {
        "合同编号": "LN20260101001",
        "借款人": "吴九",
        "贷款金额": 500000.0,
        "贷款期限": "36个月",
    },
    "drivers_license": {
        "驾驶证号": "420106198801011234",
        "准驾车型": "C1",
        "初领日期": "2010-05-01",
        "有效期限": "2020-05-01 至 2030-05-01",
    },
    "real_estate_certificate": {
        "权利人": "周八",
        "坐落": "上海市浦东新区某某路100号",
        "不动产单元号": "310115001001GB00001",
        "用途": "住宅",
    },
    "mortgage_contract": {
        "抵押权人": "某某银行股份有限公司",
        "抵押人": "郑十",
        "被担保债权数额": 800000.0,
        "抵押物": "位于某某市某某区某某路200号的房产",
    },
    "tax_certificate": {
        "税务机关": "国家税务总局",
        "纳税人识别号": "91310000MA1K12345X",
        "税种": "增值税",
        "税款所属期": "2025年12月",
    },
    "fiscal_invoice": {
        "票据代码": "310001",
        "票据号码": "0001234567",
        "开票日期": "2026-01-01",
        "收款单位": "某某财政局",
    },
    "payroll_slip": {
        "员工姓名": "钱十一",
        "实发工资": 15000.0,
    },
    "passport": {
        "护照号码": "E12345678",
        "姓名": "李四",
        "国籍": "中国",
    },
    "social_security_proof": {
        "参保单位": "某某科技有限公司",
        "参保人": "孙七",
    },
    "social_security_card": {
        "社会保障号码": "110101199001011234",
        "发卡机构": "人力资源和社会保障部",
    },
}


@pytest.mark.parametrize("document_type", EXPECTED_FIELDS)
def test_generic_public_text_sample_precision(document_type: str):
    fixture = FIXTURE_DIR / f"{document_type}.txt"
    full_text = fixture.read_text(encoding="utf-8")
    result = ParseResult(
        status=ResultStatus.SUCCESS,
        entities=DocumentEntities(document_type=document_type),
    )

    output = build_community_output(
        result,
        full_text,
        file_path=str(fixture),
    )

    assert output is not None
    assert output["plugin"]["name"] == "generic"
    assert output["classification"]["matched_document_type"] == document_type
    assert output["data"]["fields"] == EXPECTED_FIELDS[document_type]
    assert output["schema_version"] == "2.2"
    assert not check_community(output)
