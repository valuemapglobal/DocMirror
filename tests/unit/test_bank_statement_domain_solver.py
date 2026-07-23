# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace

from docmirror.plugins.bank_statement.extract_pipeline import enrich_identity_fields
from docmirror.plugins.bank_statement.institution import detect_registered_institution
from docmirror.plugins.bank_statement.institution_authority import (
    extract_identity_from_header,
    resolve_institution_from_context,
)
from docmirror.plugins.bank_statement.semantic_solver import BankStatementSemanticSolver
from docmirror.plugins.bank_statement.wide_table_recovery import (
    audit_bank_statement_invariants,
    count_expected_rows_from_bank_footer,
)

VERTICAL_LEDGER_TEXT = """
江苏银行对公账户对账单
账户名称：测试有限公司
账号：70650188000156836
起始日期：2022-01-01 终止日期：2022-01-31
借方笔数：2
借方发生总额：12.00
贷方笔数：1
贷方发生总额：5.00
合计笔数：3
1
2022-01-01
09:00:00
往来款
10.00
90.00
1104010309000388824
张三有限公司
2
2022-01-02
10:00:00
货款
5.00
95.00
2204010309000388825
李四有限公司
3
2022-01-03
11:00:00
收费
2.00
93.00
70650107360000033
企业电子渠道跨行转账手续费收入
""".strip()


def test_bank_statement_solver_reconciles_vertical_debit_credit_ledger() -> None:
    solution = BankStatementSemanticSolver().solve(full_text=VERTICAL_LEDGER_TEXT)

    assert solution.success
    assert {item["id"]: item["status"] for item in solution.invariant_results} == {
        "bank.row_count_reconciliation": "pass",
        "bank.debit_credit_count_reconciliation": "pass",
        "bank.debit_credit_total_reconciliation": "pass",
        "bank.balance_chain_consistency": "pass",
    }

    model = solution.canonical_model
    records = model["records"]
    assert [record["direction"] for record in records] == ["expense", "income", "expense"]
    assert [record["amount"] for record in records] == [-10.0, 5.0, -2.0]
    assert records[0]["timestamp"] == "2022-01-01T09:00:00"
    assert records[0]["counter_account"] == "1104010309000388824"
    assert records[0]["counter_party"] == "张三有限公司"
    assert model["identity"]["account_holder"] == "测试有限公司"
    assert model["identity"]["query_period"] == "2022-01-01 ~ 2022-01-31"

    split_table = model["split_table"]
    assert split_table[0] == [
        "序号",
        "交易日期",
        "交易时间",
        "摘要",
        "借方发生额",
        "贷方发生额",
        "余额",
        "对方账户",
        "对方户名",
    ]
    assert split_table[1][4] == "10.00"
    assert split_table[2][5] == "5.00"
    assert split_table[3][4] == "2.00"


def test_bank_statement_solver_does_not_take_over_without_debit_credit_header() -> None:
    solution = BankStatementSemanticSolver().solve(
        full_text="""
        交易明细
        2024-01-01 支付宝 10.00 支出 90.00
        2024-01-02 工资 20.00 收入 110.00
        """,
    )

    assert not solution.success
    assert solution.status == "failed"
    assert solution.diagnostics == ({"reason": "missing_debit_credit_header_totals"},)


def test_vertical_header_identity_overrides_weak_transaction_summary_identity() -> None:
    text = """
    江苏银行对公账户对账单（本对账单仅供参考）
    起始日期：2022-06-01
    2022-08-31
    终止日期：
    镇江一生一世好游戏有限公司
    账户名称：
    70650188000156836
    账号：
    借方笔数：61
    贷方笔数：30
    序号
    摘要
    往来款
    """.strip()

    assert extract_identity_from_header(text) == {
        "account_holder": "镇江一生一世好游戏有限公司",
        "account_number": "70650188000156836",
        "query_period": "2022-06-01 ~ 2022-08-31",
    }

    fields = enrich_identity_fields(
        {
            "account_holder": {
                "raw_name": "account_holder",
                "raw_value": "往来款",
                "normalized_value": "往来款",
                "data_type": "string",
            },
        },
        text,
    )

    assert fields["account_holder"]["normalized_value"] == "镇江一生一世好游戏有限公司"
    assert fields["account_number"]["normalized_value"] == "70650188000156836"
    assert fields["currency"]["normalized_value"] == "CNY"


def test_horizontal_header_identity_for_wide_bank_statement() -> None:
    text = """
    交通银行
    交通银行宁夏回族自治区分行明细对账单
    开户机构：交通银行银川开发区支行
    币种：人民币
    年份：2025
    月份：11
    账号： 641301106013000859983 户名： 重庆正大华日软件有限公司银川分公司
    序号 会计日期 交易日期 交易名称 借方发生额 贷方发生额 余额
    """.strip()

    identity = extract_identity_from_header(text)

    assert identity["account_holder"] == "重庆正大华日软件有限公司银川分公司"
    assert identity["account_number"] == "641301106013000859983"
    assert identity["bank_name"] == "交通银行银川开发区支行"
    assert identity["currency"] == "CNY"
    assert identity["query_period"] == "2025-11-01 ~ 2025-11-30"


def test_label_block_header_identity_for_wide_bank_statement() -> None:
    text = """
    交通银行宁夏回族自治区分行明细对账单
    户名：
    页码：
    年份：
    币种：
    账号：
    开户机构：交通银行银川开发区支行
    641301106013000859983
    重庆正大华日软件有限公司银川分公司
    本月第1份-第1页
    2025
    人民币
    88B8563F
    交通银行
    11
    月份：
    借方发生额
    """.strip()

    identity = extract_identity_from_header(text)

    assert identity["account_holder"] == "重庆正大华日软件有限公司银川分公司"
    assert identity["account_number"] == "641301106013000859983"
    assert identity["bank_name"] == "交通银行银川开发区支行"
    assert identity["currency"] == "CNY"
    assert identity["query_period"] == "2025-11-01 ~ 2025-11-30"


def test_ccb_header_totals_and_query_period_are_supported() -> None:
    text = """
    账号： 13355000000062937 账户名称： 镇江海翔机械制造有限公司
    查询日期： 2023-10-01至2023-12-31
    收入总金额： 308361.39 收入总笔数： 21
    支出总金额： 310212.14 支出总笔数： 42
    """.strip()

    assert count_expected_rows_from_bank_footer(text) == 63
    identity = extract_identity_from_header(text)
    assert identity["account_holder"] == "镇江海翔机械制造有限公司"
    assert identity["account_number"] == "13355000000062937"
    assert identity["query_period"] == "2023-10-01 ~ 2023-12-31"


def test_reverse_order_balance_chain_passes_when_totals_close() -> None:
    text = "收入总金额： 100.00 收入总笔数： 1 支出总金额： 20.00 支出总笔数： 1"
    records = [
        {"normalized": {"date": "2023-01-02", "amount": 100.0, "direction": "income", "balance": 180.0}},
        {"normalized": {"date": "2023-01-01", "amount": 20.0, "direction": "expense", "balance": 80.0}},
    ]

    assert audit_bank_statement_invariants(records, text) == []


def test_balance_chain_gap_reports_review_only_missing_row_candidate() -> None:
    records = [
        {"normalized": {"date": "2022-06-24", "amount": 2.0, "direction": "expense", "balance": 89.60}},
        {"normalized": {"date": "2022-07-01", "amount": 16.99, "direction": "expense", "balance": 44.82}},
    ]

    failures = audit_bank_statement_invariants(records, "")

    assert "bank_invariant_failed:balance_chain:1/1" in failures
    assert (
        "bank_review:balance_chain_gap:"
        "row=2:date=2022-07-01:direction=expense:amount=16.99:"
        "prev_balance=89.60:expected_balance=72.61:actual_balance=44.82:"
        "delta=-27.79"
    ) in failures
    assert (
        "bank_review:missing_row_candidate:"
        "before_row=2:date_range=2022-06-24..2022-07-01:"
        "direction=expense:amount=27.79:balance=61.81:"
        "evidence=balance_chain_only:action=manual_review:not_auto_adopted"
    ) in failures
    assert (
        "bank_review:repair_request:"
        "id=bank-ledger-balance-gap-before-row-2:"
        "kind=missing_ledger_row_local_ocr:"
        "can_render=false:"
        "action=manual_review:"
        "reason=missing_page_bbox"
    ) in failures


def test_transaction_channel_is_not_institution() -> None:
    parse_result = SimpleNamespace(
        entities=SimpleNamespace(organization="网上银行", domain_specific={}),
        file_path="/tmp/银行流水_中国建设银行_20231228.pdf",
    )

    assert resolve_institution_from_context(parse_result, "网上银行 网银结算") == ("中国建设银行", "filename.token")


def test_institution_registry_is_owned_by_bank_plugin() -> None:
    assert detect_registered_institution("中国建设银行 账户交易明细 序号 交易日期") == "中国建设银行"
