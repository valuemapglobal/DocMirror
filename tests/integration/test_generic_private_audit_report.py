# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Private full-document regression for the Generic audit-report fallback."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import ExecutionControl, ParseControl, normalize_parse_control
from docmirror.plugins._runtime.runner import clear_run_cache
from docmirror.server.output_builder import build_community_output
from tests._community_reading import assert_community_reading_view
from tests.contract.test_edition_schema_conformance import check_community

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.tier_slow,
    pytest.mark.track_e2e,
]

FIXTURE = Path("tests/fixtures-private/2.杭州华英新塘2024年度审计报告_cleaned.pdf")
SCANNED_FIXTURE = Path("tests/fixtures-private/2.杭州华英新塘2023年度审计报告.pdf")

EXPECTED_TOP_LEVEL_KEYS = {
    "$schema",
    "business",
    "classification",
    "composition",
    "data",
    "document",
    "edition",
    "metadata",
    "plugin",
    "projection_lineage",
    "quality",
    "schema_version",
    "status",
    "validation",
}
EXPECTED_DATA_KEYS = {
    "columns",
    "data_dictionary",
    "datasets",
    "field_details",
    "fields",
    "line_items",
    "notes",
    "records",
    "sections",
    "summary",
    "tables",
    "document_flow",
}


def _is_non_contiguous(pages: list[int]) -> bool:
    unique_pages = sorted(set(pages))
    return bool(unique_pages) and unique_pages != list(range(unique_pages[0], unique_pages[-1] + 1))


def test_generic_private_audit_report_precision_and_contract():
    if not FIXTURE.exists():
        pytest.skip("private Generic audit-report fixture is unavailable")

    clear_run_cache()
    control = ParseControl(
        mode="balanced",
        execution=ExecutionControl(cache_policy="off", ocr="off"),
    )
    result = asyncio.run(perceive_document(FIXTURE, PerceiveOptions(control=control)))
    output = build_community_output(
        result,
        result.full_text or "",
        file_path=str(FIXTURE),
    )

    assert output is not None
    assert set(output) == EXPECTED_TOP_LEVEL_KEYS
    assert set(output["data"]) == EXPECTED_DATA_KEYS
    assert not check_community(output)
    assert output["schema_version"] == "2.2"
    assert output["plugin"]["name"] == "generic"
    assert output["classification"]["matched_document_type"] == "audit_report"
    assert_community_reading_view(output["data"])

    fields = output["data"]["fields"]
    assert fields == {
        "法定代表人": "许水均",
        "统一社会信用代码": "91330109MA27XQ7P70",
        "注册地址": "杭州市萧山区新塘街道霞江村",
        "经营范围": "一般项目:羽毛(绒)及制品制造;家用纺织制成品制造;家居用品制造",
    }
    assert all(len(key) >= 2 and "|" not in key for key in fields)

    section_titles = {section["title"] for section in output["data"]["sections"]}
    assert {
        "一、审计意见",
        "二、形成审计意见的基础",
        "三、管理层和治理层对财务报表的责任",
        "四、注册会计师对财务报表审计的责任",
        "六、合并财务报表项目注释",
        "1、货币资金",
        "2、应收账款",
        "4、预付款项",
        "6、存货",
        "10、使用权资产",
        "13、递延所得税资产/递延所得税负债",
        "15、所有权或使用权受到限制的资产",
        "16、短期借款",
        "32、营业收入和营业成本",
        "46、外币货币性项目",
        "七、合并范围的变更",
        "十二、母公司财务报表主要项目注释",
    } <= section_titles
    ordered_titles = [section["title"] for section in output["data"]["sections"]]
    note_titles = ordered_titles[
        ordered_titles.index("六、合并财务报表项目注释") : ordered_titles.index("七、合并范围的变更")
    ]
    note_numbers = {
        int(prefix)
        for title in note_titles
        for prefix, separator, _rest in [title.partition("、")]
        if separator and prefix.isdigit()
    }
    assert note_numbers == set(range(1, 47))
    assert {
        "3、本年减少金额",
        "4、年末余额",
        "四、账面价值",
        "1、年末账面价值",
        "2、年初账面价值",
        "一、账面原值",
        "3、本期减少金额",
        "四、一年内到期",
        "6、短期带薪缺勤",
        "7、短期利润分享计划",
    }.isdisjoint(section_titles)

    unsafe_logical_tables = [
        table
        for table in output["data"]["tables"]
        if table.get("kind") == "logical_table"
        and float(table.get("merge_confidence") or 0.0) < 0.75
        and _is_non_contiguous(table.get("source_pages") or [])
    ]
    assert not unsafe_logical_tables

    bank_deposit = next(
        record
        for record in output["data"]["records"]
        if record.get("raw", {}).get("项目") == "银行存款" and record.get("raw", {}).get("年末余额") == "64,822,045.96"
    )
    assert bank_deposit["normalized"]["年末余额"] == {
        "value": 64822045.96,
        "currency": "CNY",
    }
    assert bank_deposit["normalized"]["年初余额"] == {
        "value": 18410772.82,
        "currency": "CNY",
    }
    assert bank_deposit["source"] == {
        "table_id": "pt_49_0",
        "table_row_index": 1,
        "page": 49,
        "physical_table_id": "pt_49_0",
    }

    warnings = output["status"]["warnings"]
    assert not any("generic_currency_unknown" in warning for warning in warnings)
    assert output["business"]["document_label"] == "审计报告（通用处理）"
    assert output["quality"]["score"] < 0.9
    assert output["quality"]["grade"] == "good"
    assert output["quality"]["readiness"] == "review"


@pytest.mark.skipif(
    os.environ.get("DOCMIRROR_RUN_REAL_OCR") != "1",
    reason="set DOCMIRROR_RUN_REAL_OCR=1 to run the full scanned Generic audit gate",
)
def test_generic_private_scanned_audit_report_precision_and_contract():
    if not SCANNED_FIXTURE.exists():
        pytest.skip("private scanned Generic audit-report fixture is unavailable")

    clear_run_cache()
    control = normalize_parse_control(
        mode="accurate",
        ocr="force",
        ocr_language="zh",
        ocr_locale="zh-CN",
        ocr_correction="safe",
        page_split="auto",
        cache_policy="off",
    )
    result = asyncio.run(perceive_document(SCANNED_FIXTURE, PerceiveOptions(control=control)))
    output = build_community_output(
        result,
        result.full_text or "",
        file_path=str(SCANNED_FIXTURE),
    )

    assert output is not None
    assert set(output) == EXPECTED_TOP_LEVEL_KEYS
    assert set(output["data"]) == EXPECTED_DATA_KEYS
    assert not check_community(output)
    assert output["document"]["page_count"] == 87
    assert output["plugin"]["name"] == "generic"
    assert output["classification"]["matched_document_type"] == "audit_report"
    assert_community_reading_view(output["data"])

    fields = output["data"]["fields"]
    assert fields["统一社会信用代码"] == "91330109MA27XQ7P70"
    assert fields["注册地址"] == "杭州市萧山区新塘街道霞江村"
    assert "智能机器人的研发" in fields["经营范围"]
    assert {
        "单位",
        "调整年初未分配利润明细",
        "调整后年初未分配利润 加",
        "3年末现金及现金等价物余额 其中",
    }.isdisjoint(fields)

    ordered_titles = [section["title"] for section in output["data"]["sections"]]
    section_titles = set(ordered_titles)
    assert {"6、存货", "30、盈余公积", "31、未分配利润"} <= section_titles
    assert {
        "六、其他综合收益",
        "二、投资活动产生的现金流量",
        "1、工资、奖金、津贴和补贴",
    }.isdisjoint(section_titles)
    note_titles = ordered_titles[
        ordered_titles.index("六、合并财务报表项目注释") : ordered_titles.index("七、合并范围的变更")
    ]
    note_numbers = [
        int(prefix)
        for title in note_titles
        for prefix, separator, _rest in [title.partition("、")]
        if separator and prefix.isdigit()
    ]
    assert note_numbers == list(range(1, 46))
    assert "4、营业收入和营业成本" in section_titles

    expected_inventory = {
        "原材料": "1,297,676.15",
        "在产品、半成品": "276,543,901.56",
        "库存商品": "63,019,766.24",
        "发出商品": "148,995,015.18",
    }
    inventory = {
        record["raw"]["项目"]: record
        for record in output["data"]["records"]
        if record.get("raw", {}).get("项目") in expected_inventory and "年末余额/账面余额" in record.get("raw", {})
    }
    assert set(inventory) == set(expected_inventory)
    for item, amount in expected_inventory.items():
        assert inventory[item]["raw"]["年末余额/账面余额"] == amount
        assert inventory[item]["raw"]["年末余额/账面价值"] == amount
        assert inventory[item]["source"]["page"] == 55
    assert not any("generic_page_reference_mismatch" in warning for warning in output["status"]["warnings"])
