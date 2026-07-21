# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from docmirror.models.entities.parse_result import (
    CellValue,
    DocumentEntities,
    PageContent,
    ParseResult,
    TableBlock,
    TableRow,
    TextBlock,
)
from docmirror.plugins.credit_report.scanned_business import (
    extract_scanned_credit_accounts,
    extract_scanned_credit_business,
    link_repayment_records_to_accounts,
)


def _table(table_id: str, rows: list[list[str]]) -> TableBlock:
    return TableBlock(
        table_id=table_id,
        headers=rows[0],
        rows=[TableRow(cells=[CellValue(text=value) for value in row]) for row in rows[1:]],
        metadata={"raw_rows": rows},
        confidence=0.94,
    )


def test_scanned_business_extracts_profile_and_query_rows_with_provenance() -> None:
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                source_page_number=1,
                texts=[TextBlock(content="个人基本信息 查询记录")],
                tables=[
                    _table(
                        "profile",
                        [
                            ["性别", "出生日期", "婚姻状况"],
                            ["男", "2002.08.03", "未婚"],
                        ],
                    ),
                    _table(
                        "queries",
                        [
                            ["编号", "查询日期", "查询操作员", "查询原因"],
                            ["1", "2025.11.05", "本人", "本人查询"],
                            ["2", "2025.10.09", "某银行", "贷后管理"],
                        ],
                    ),
                ],
            )
        ]
    )

    actual = extract_scanned_credit_business(result, "账户1 查询记录")

    assert actual["subject_profile"]["gender"]["value"] == "男"
    assert actual["subject_profile"]["birth_date"]["value"] == "2002-08-03"
    assert actual["subject_profile"]["marital_status"]["value"] == "未婚"
    assert len(actual["inquiry_records"]) == 2
    assert actual["inquiry_records"][0]["source_refs"][0]["table_id"] == "queries"
    assert actual["credit_summary"]["reported_account_count"] == 1


def test_scanned_business_merges_cross_page_residence_and_stacked_employment_tables() -> None:
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                source_page_number=1,
                texts=[
                    TextBlock(content="性别 出生日期 婚姻状况 就业状况"),
                    TextBlock(content="男 2002.08.03 未婚 职员"),
                    TextBlock(content="学历 学位 国赣 电子邮箱"),
                    TextBlock(content="大专 光 中国(含港澳台) sample@example.com"),
                    TextBlock(content="编号 手机号码 信息更新日期"),
                    TextBlock(content="1 15260467509 2025.08.03"),
                ],
                tables=[
                    _table(
                        "residence-head",
                        [
                            ["编号", "聚 居住地址", "住宅电话", "居住状况", "信息更新日期"],
                            ["1", "地址一", "—", "租房", "2025.05.15"],
                            ["2", "地址二", "“", "租房", "2024.07.17"],
                            ["3", "地址三", "=", "亲属楼宇", "2022.11.29"],
                        ],
                    )
                ],
            ),
            PageContent(
                page_number=2,
                source_page_number=1,
                texts=[TextBlock(content="职业信息")],
                tables=[
                    _table(
                        "residence-tail",
                        [
                            ["4", '2022.11.12 福建省南安市石井镇地址46号 " "'],
                            ["5", "2022.08.09 福建省厦门市思明区地址1801 **"],
                        ],
                    ),
                    _table(
                        "employment",
                        [
                            ["编号", "工作单位", "单位性质 个体私营企业", "单位地址", "单位电话"],
                            ["1", "单位一", "", "地址一", "0592 12345678"],
                            ["子 2 2", "单位二", "个体、私营企业", "地址二", "0592 87654321"],
                            ["3", "单位三", "其他", "地址三", ""],
                            ["编号", "行业 职业", "", "进入本单位年份 职称 职务", "信息更新日期"],
                            ["1", "商业、服务业人员", "", "2024 一般员工", "2025.05.15"],
                            ["2", "批发和零售业 办事人员和有关人员", "", "一般员工", "2024.07.17"],
                            ["3", "不便分类的其他从业人员", "", "无", "2022.11.14"],
                            ["编号", "", "", "数据发生机构名称", ""],
                            ["1", "", "", "某银行", ""],
                        ],
                    ),
                ],
            ),
        ]
    )

    actual = extract_scanned_credit_business(result, "合计 8")

    assert actual["subject_profile"]["mobile_phone"]["value"] == "15260467509"
    assert actual["subject_profile"]["employment_status"]["value"] == "职员"
    assert len(actual["residence_records"]) == 5
    assert "住宅电话" not in actual["residence_records"][0]["values"]
    assert actual["residence_records"][-1]["values"]["居住地址"] == "福建省厦门市思明区地址1801"
    assert actual["residence_records"][-1]["audit"]["cross_page_continuation"] is True
    assert len(actual["employment_records"]) == 3
    assert actual["employment_records"][0]["values"]["单位性质"] == "个体私营企业"
    assert actual["employment_records"][1]["values"]["行业"] == "批发和零售业"
    assert actual["employment_records"][1]["values"]["职业"] == "办事人员和有关人员"
    assert actual["employment_records"][2]["values"]["职称"] == "无"


def test_repayment_records_link_to_nearest_preceding_account() -> None:
    records = [{"year": 2025, "month": 1, "source_cell_refs": [{"grid_id": "grid-1", "page": 3}]}]
    accounts = [
        {"account_id": "a1", "page": 3, "bbox": [20, 100, 500, 200]},
        {"account_id": "a2", "page": 3, "bbox": [20, 300, 500, 400]},
    ]
    grids = [{"grid_id": "grid-1", "page": 3, "bbox": [20, 420, 500, 600]}]

    actual = link_repayment_records_to_accounts(records, accounts, grids)

    assert actual[0]["account_id"] == "a2"


def test_report_explanations_are_not_emitted_as_subject_statements() -> None:
    result = ParseResult(
        pages=[
            PageContent(
                page_number=10,
                source_page_number=6,
                texts=[
                    TextBlock(content="报告说明"),
                    TextBlock(content="16.本人声明是信息主体对信用报告中的信息所附注的简要说明。"),
                    TextBlock(content="17.异议标注是征信中心添加的说明。"),
                ],
            )
        ]
    )

    actual = extract_scanned_credit_business(result, "")

    assert actual["statements"] == []
    assert actual["annotations"] == []


def test_scanned_query_lines_and_summary_table_override_merged_table_artifacts() -> None:
    bundles = [
        {
            "page": 2,
            "source_page_number": 1,
            "local_structure_evidence": {
                "lines": [
                    {"text": "2024.10.28 招商银行股份有限公司信用卡中心 贷后管理"},
                    {"text": "13 2024.07.17 华夏银行股份有限公司信用卡中心 信用卡审批"},
                ]
            },
        }
    ]
    result = ParseResult(
        pages=[
            PageContent(
                page_number=2,
                source_page_number=1,
                tables=[
                    _table(
                        "credit-summary",
                        [
                            ["业务类型", "账户数"],
                            ["其他类贷款", "5"],
                            ["贷记卡", "3"],
                            ["合计", "8"],
                        ],
                    ),
                    _table(
                        "merged-query",
                        [
                            ["查询日期", "查询机构", "查询原因"],
                            [
                                "2024.10.28 2024.07.17",
                                "招商银行股份有限公司信用卡中心 华夏银行股份有限公司信用卡中心",
                                "贷后管理 信用卡审批",
                            ],
                        ],
                    ),
                ],
            )
        ],
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific={"_page_evidence_bundles": bundles},
        ),
    )

    actual = extract_scanned_credit_business(result, "合计 4")

    assert len(actual["inquiry_records"]) == 2
    assert actual["inquiry_records"][0]["source"] == "scanned_query_text_line"
    assert actual["credit_summary"]["reported_account_count"] == 8


def test_scanned_account_cards_are_segmented_across_pages_without_false_summary_accounts() -> None:
    def line(text: str, y: float) -> dict:
        return {"text": text, "bbox": [20, y, 500, y + 12], "confidence": 0.98, "evidence_ids": [text]}

    bundles = [
        {
            "page": 1,
            "source_page_number": 1,
            "local_structure_evidence": {"lines": [line("账户数 合计 3", 20)]},
        },
        {
            "page": 2,
            "source_page_number": 1,
            "local_structure_evidence": {
                "lines": [
                    line("(一)非循环贷账户", 20),
                    line("账户(授信协议标识:A12345678)", 40),
                    line("管理机构 账户标识 开立日期 到期日期 借款金额 账户币种", 60),
                    line("示例银行股份有限公司 A12345678 2022.01.01 2030.01.01 6,500 人民币元", 80),
                    line("账户状态 五级分类 余额", 100),
                    line("正常 正常 5,000", 120),
                ]
            },
        },
        {
            "page": 3,
            "source_page_number": 2,
            "local_structure_evidence": {
                "lines": [
                    line("(三)贷记卡账户", 20),
                    line("账户1(授信协议标识:CARD0001)", 40),
                    line("发卡机构 账户标识 开立日期 账户授信额度 币种 业务种类", 60),
                    line(
                        "示例银行股份有限公司 大额 专项 分期 厦门市分行 CARD0001 2024.01.01 12,000 人民币元 贷记卡",
                        80,
                    ),
                    line("截至2025年10月31日", 100),
                    line("账户状态 余额 已用额度", 120),
                    line("正常 0 0", 140),
                    line("(四)授信协议信息", 160),
                ]
            },
        },
    ]
    result = ParseResult(
        entities=DocumentEntities(
            document_type="credit_report",
            domain_specific={"_page_evidence_bundles": bundles},
        )
    )

    accounts = extract_scanned_credit_accounts(result)

    assert [item["account_id"] for item in accounts] == [
        "credit_account:non_revolving_loan:1",
        "credit_account:credit_card:1",
    ]
    assert accounts[0]["loan_amount"] == 6500
    assert accounts[0]["balance"] == 5000
    assert accounts[1]["credit_limit"] == 12000
    assert accounts[1]["management_institution"] == "示例银行股份有限公司厦门市分行"
    assert accounts[1]["audit"]["projection_completeness"] == "raw_and_semantic_core_complete"
