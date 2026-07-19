# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

from docmirror.models.entities.parse_result import PageContent, TextBlock
from docmirror.plugins.credit_report.business_records import (
    derive_overdue_records,
    extract_native_credit_business,
)


def _result(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        pages=[PageContent(page_number=1, texts=[TextBlock(content=text)])],
    )


def test_personal_brief_extracts_narrative_accounts_and_inquiry_ledger() -> None:
    text = """
    个人信用报告 信贷记录
    2022年01月02日示例银行信用卡中心发放的贷记卡（人民币账户，卡片尾号：1234）。
    截至2024年11月，信用额度100,000，余额2,000，当前无逾期。
    最近5年内有1个月处于逾期状态，没有发生过90天以上逾期。
    2023年02月03日示例商业银行发放的300,000元（人民币）个人经营性贷款，
    2026年02月03日到期。截至2024年11月，余额200,000，从未发生过逾期。
    2024年03月04日示例商业银行为个人经营性贷款授信，额度有效期至2027年03月04日，
    可循环使用。截至2024年11月，信用额度500,000元（人民币），余额为120,000，当前无逾期。
    机构查询记录明细
    编号 查询日期 查询机构 查询原因
    1 2024年10月01日 示例商业银行 贷款审批
    2 2024年11月02日 示例商业银行 贷后管理
    个人查询记录明细
    1 2024年12月03日 本人查询（互联网个人信用信息服务平台）
    """

    business = extract_native_credit_business(
        _result(text),
        text,
        report_subtype="personal_brief",
        content_mode="native_text",
    )

    assert len(business["credit_accounts"]) == 3
    assert len({item["account_id"] for item in business["credit_accounts"]}) == 3
    assert business["credit_accounts"][1]["loan_amount"] == 300000
    assert business["credit_lines"][0]["total_limit"] == 500000
    assert business["credit_lines"][0]["used_limit"] == 120000
    assert business["overdue_records"][0]["overdue_months"] == 1
    assert len(business["inquiry_records"]) == 3
    assert business["credit_summary"]["institution_inquiry_count"] == 2
    assert business["credit_summary"]["personal_inquiry_count"] == 1


def test_personal_brief_keeps_indistinguishable_masked_accounts() -> None:
    text = """
    个人信用报告 信贷记录
    2020年01月01日示例银行信用卡中心发放的贷记卡（人民币账户）。截至2024年11月，余额0。
    2020年01月01日示例银行信用卡中心发放的贷记卡（人民币账户）。截至2024年11月，余额0。
    """

    business = extract_native_credit_business(
        _result(text),
        text,
        report_subtype="personal_brief",
        content_mode="native_text",
    )

    assert len(business["credit_accounts"]) == 2
    assert len({item["account_id"] for item in business["credit_accounts"]}) == 2


def test_enterprise_extracts_summary_facilities_accounts_and_public_records() -> None:
    text = """
    企业信用报告 信息概要
    首次有信贷交易的年份 发生信贷交易的机构数 当前有未结清信贷交易的机构数
    首次有相关还款责任的年份
    2019 3 2 2024
    借贷交易 担保交易 余额 37311.68 余额 6000 其中：被追偿余额 0
    非信贷交易账户数 欠税记录条数 民事判决记录条数 强制执行记录条数 行政处罚记录条数
    0 0 0 0 0
    非循环信用额度 循环信用额度
    总额 已用额度 剩余可用额度 总额 已用额度 剩余可用额度
    3000 2500 500 4900 4000 900
    责任类型
    公共记录明细 获得许可记录
    许可部门 许可类型 许可日期 截止日期 许可内容
    示例市生态环境
    局 普通 2023-05-25 2028-07-21 排污
    许可
    认证部门 认证类型 认证日期 截止日期 认证内容
    国家税务总局 纳税信用A级纳税人 -- 2028-12-31 2022年度纳税信用A级纳税人
    附件1：信用记录补充信息
    1.未结清账户编号：G10323310H000123456789
    授信机构：示例商业银行股份有限公司
    业务种类：流动资金贷款
    信息报告日期 余额 五级分类
    """

    business = extract_native_credit_business(
        _result(text),
        text,
        report_subtype="enterprise",
        content_mode="native_text",
    )

    assert business["credit_summary"]["first_credit_year"] == 2019
    assert business["credit_summary"]["active_credit_institution_count"] == 2
    assert business["credit_summary"]["credit_balance"] == 37311.68
    assert len(business["credit_lines"]) == 2
    assert business["credit_lines"][0]["available_limit"] == 500
    assert len(business["credit_accounts"]) == 1
    assert business["credit_accounts"][0]["account_status"] == "active"
    assert {item["record_type"] for item in business["public_records"]} == {
        "license",
        "certification",
    }
    license_record = next(item for item in business["public_records"] if item["record_type"] == "license")
    assert license_record["authority"] == "示例市生态环境局"
    assert license_record["content"] == "排污许可"


def test_enterprise_public_records_support_one_cell_per_text_line() -> None:
    text = """
    企业信用报告（自主查询版）
    公共记录明细
    许可部门
    许可类型
    许可日期
    截止日期
    许可内容
    示例市生态环境局
    普通
    2024-01-02
    2025-01-02
    排污许可
    示例省示例市市场
    监督管理局
    普通
    2024-03-04
    2026-03-04
    热食类食品制售
    认证部门
    认证类型
    认证日期
    截止日期
    认证内容
    国家税务总局
    纳税信用A级纳税人
    --
    2025-12-31
    2024年度纳税信
    用A级纳税人
    附件1：信用记录补充信息
    """

    business = extract_native_credit_business(
        _result(text),
        text,
        report_subtype="enterprise",
        content_mode="native_text",
    )

    records = business["public_records"]
    assert len(records) == 3
    assert records[1]["authority"] == "示例省示例市市场监督管理局"
    assert records[2]["content"] == "2024年度纳税信用A级纳税人"


def test_derive_overdue_records_from_scanned_account_and_repayment_month() -> None:
    records = derive_overdue_records(
        [
            {
                "source_structure_id": "account-1",
                "account_status": {"normalized_value": "逾期"},
                "overdue_amount": {"normalized_value": "1,200"},
                "confidence": 0.91,
            }
        ],
        [
            {
                "grid_id": "grid-1",
                "year": 2024,
                "month": 8,
                "status": "2",
                "confidence": 0.88,
                "source_cell_refs": [{"cell_id": "status-8"}],
            }
        ],
    )

    assert len(records) == 2
    assert records[0]["period_scope"] == "account_snapshot"
    assert records[0]["overdue_amount"] == 1200
    assert records[1]["period_scope"] == "month"
    assert records[1]["overdue_level"] == 2
