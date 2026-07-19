# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Bank statement template registry and canonical style integration."""

from __future__ import annotations

import os

import pytest

from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
from docmirror.plugins.bank_statement.wide_table_recovery import _recover_cross_page_wide_tables


def test_builtin_templates_registered():
    pytest.importorskip("docmirror_enterprise", reason="enterprise package is not available in OSS CI")
    from docmirror_enterprise.plugins.bank_statement.configs.registry import ensure_builtin_templates, reset_registry

    reset_registry()
    reg = ensure_builtin_templates()
    ids = {t["template_id"] for t in reg.list_templates()}
    assert "generic" in ids
    assert "icbc_personal_v2022" in ids
    assert reg.template_count >= 3


def test_style_registry_extracts_three_transactions_from_clean_table():
    ctx = StyleContext(
        tables=[
            [
                ["交易日期", "摘要", "收入", "支出", "余额"],
                ["2024-01-01", "工资入账", "5000.00", "0.00", "8000.00"],
                ["2024-01-02", "转账支出", "0.00", "200.00", "7800.00"],
                ["2024-01-03", "消费", "0.00", "50.00", "7750.00"],
            ]
        ],
        full_text="中国工商银行\n个人客户交易明细\n户名：张三",
        institution=None,
        page_count=1,
    )
    detection = BankStyleDetector().detect(ctx)
    assert detection.primary_style == "split_debit_credit"
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) >= 3


def test_style_registry_extracts_wide_debit_credit_table_and_skips_footer():
    ctx = StyleContext(
        tables=[
            [
                [
                    "序号",
                    "会计日期",
                    "交易日期",
                    "交易名称",
                    "借方发生额",
                    "贷方发生额",
                    "余额",
                    "对方账号",
                    "对方户名",
                    "摘要",
                ],
                [
                    "1",
                    "20251114",
                    "20251114",
                    "来账",
                    "",
                    "120,000.00",
                    "139,038.63",
                    "011101421000 9630",
                    "重庆正大华日软 件有限公司",
                    "往来款",
                ],
                [
                    "2",
                    "20251114",
                    "20251114",
                    "代付",
                    "97,462.92",
                    "",
                    "41,575.71",
                    "641106012890 900100012499",
                    "应付代收业务款 项",
                    "代发工资",
                ],
                ["当前账单借方发生数： 1", "当前账单贷方发生数：1", "", "", "", "", "", "", "", ""],
            ]
        ],
        full_text="交通银行\n当前账单借方发生数：1 当前账单贷方发生数：1 本月累计借方发生额：97,462.92 本月累计贷方发生额：120,000.00",
        institution=None,
        page_count=1,
    )
    detection = BankStyleDetector().detect(ctx)
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)

    assert len(records) == 2
    assert [r["normalized"]["direction"] for r in records] == ["income", "expense"]
    assert records[0]["normalized"]["counter_account"] == "0111014210009630"
    assert records[0]["normalized"]["counter_party"] == "重庆正大华日软件有限公司"


def test_cross_page_native_income_expense_table_inherits_header():
    page_tables = [
        [
            ["序 号", "交易日期", "交易时 间", "支出金额", "收入金额", "余额", "对方账号", "对方户名"],
            [
                "1",
                "2023-12- 28",
                "15:28:5 3",
                "",
                "2,800.00",
                "2,932.04",
                "24020034091 00018033",
                "贵阳世钟 汽车配件 有限公司",
            ],
            ["2", "2023-12- 27", "14:06:0 2", "7.00", "", "132.04", "60220903", "网上银行 结算手续 费收入"],
        ],
        [
            [
                "3",
                "2023-12- 27",
                "14:06:0 2",
                "10,500.00",
                "",
                "139.04",
                "32050161716 000000050",
                "无锡市融 达汽车零 部件有限 公司",
            ],
            ["4", "2023-12- 27", "13:58:5 9", "", "10,500.00", "10,639.04", "62284810431 55907917", "张淑红"],
        ],
    ]
    tables = _recover_cross_page_wide_tables(page_tables)

    assert len(tables) == 1
    assert len(tables[0]) == 5
    assert tables[0][1][1] == "2023-12-28"
    assert tables[0][1][2] == "15:28:53"

    ctx = StyleContext(
        tables=tables,
        full_text="收入总金额：13300.00 收入总笔数：2 支出总金额：10507.00 支出总笔数：2",
        institution=None,
        page_count=2,
    )
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(BankStyleDetector().detect(ctx), ctx, plugin)
    norms = [record["normalized"] for record in records]

    assert len(records) == 4
    assert sum(1 for norm in norms if norm["direction"] == "income") == 2
    assert sum(1 for norm in norms if norm["direction"] == "expense") == 2
    assert norms[0]["counter_party"] == "贵阳世钟汽车配件有限公司"


def test_removed_detector_is_not_registered():
    pytest.importorskip("docmirror_enterprise", reason="enterprise package is not available in OSS CI")

    with pytest.raises(ImportError):
        from docmirror_enterprise.plugins.bank_statement.detectors.template_detector import (  # noqa: F401
            BankStatementDetector,
        )


@pytest.mark.skipif(
    not os.environ.get("DOCMIRROR_RUN_SYNTHETIC_TESTS"),
    reason="Synthetic PDF OCR test requires DOCMIRROR_RUN_SYNTHETIC_TESTS=1",
)
@pytest.mark.asyncio
async def test_bank_synthetic_extracts_transactions():
    from docmirror.plugins.bank_statement.context import collect_tables_from_parse_result
    from scripts.generate_synthetic_golden_pdfs import ensure_bank_synthetic
    from tests.golden.test_golden_matrix_benchmark import _parse_case

    pdf = ensure_bank_synthetic()
    pr = await _parse_case(pdf)
    assert pr.entities.document_type == "bank_statement"
    assert len(pr.extractor_full_text or pr.full_text) > 50

    ctx = StyleContext(
        tables=collect_tables_from_parse_result(pr),
        full_text=pr.full_text or "",
        institution=None,
        page_count=len(pr.pages or []),
        parse_result=pr,
    )
    detection = BankStyleDetector().detect(ctx)
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) >= 3

    api = pr.to_mirror_json_vnext()
    doc = api
    assert len(doc.get("pages") or []) >= 1
