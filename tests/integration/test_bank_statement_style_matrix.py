# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parameterized bank statement style integration tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.plugins._runtime.runner import run_plugin_extract_sync

YINZUO = Path("tests/fixtures/bank_statement/重庆恒腾科技有限公司_银行流水_银座银行_20251229.pdf")
CCB = Path("tests/fixtures/bank_statement/银行流水_中国建设银行_20231226.pdf")


@pytest.mark.integration
@pytest.mark.parametrize(
    "fixture,expected_style,min_rows",
    [
        pytest.param(
            YINZUO,
            "compact_merged_ledger",
            6,
            marks=pytest.mark.skipif(not YINZUO.is_file(), reason="missing yinzuo fixture"),
        ),
        pytest.param(
            CCB,
            "grid_standard",
            1,
            marks=[
                pytest.mark.skipif(not CCB.is_file(), reason="missing ccb fixture"),
                pytest.mark.slow,
            ],
        ),
    ],
    ids=["yinzuo_compact", "ccb_grid"],
)
def test_bank_statement_style_matrix(fixture: Path, expected_style: str, min_rows: int):
    mirror = asyncio.run(
        perceive_document(fixture, PerceiveOptions(enhance_mode="standard"))
    ).mirror

    out = run_plugin_extract_sync(
        mirror,
        edition="community",
        full_text=mirror.full_text,
        file_path=str(fixture),
    )
    assert out is not None
    props = out.get("document", {}).get("properties", {})
    assert props.get("style_id") == expected_style
    assert out["metadata"].get("style_id") == expected_style

    records = out["data"]["records"]
    assert len(records) >= min_rows

    if expected_style == "compact_merged_ledger":
        norm = records[0]["normalized"]
        assert norm.get("date") == "2025-09-21"
        assert norm.get("amount") == pytest.approx(0.04)


@pytest.mark.integration
def test_style_matrix_synthetic_split_debit_credit():
    from docmirror.plugins.bank_statement.context import StyleContext
    from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
    from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
    from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin

    ctx = StyleContext(
        tables=[[
            ["交易日期", "摘要", "收入", "支出", "余额"],
            ["2024-01-01", "工资入账", "5000.00", "0.00", "8000.00"],
            ["2024-01-02", "转账支出", "0.00", "200.00", "7800.00"],
        ]],
        full_text="中国工商银行 个人客户交易明细",
        institution=None,
        page_count=1,
    )
    detection = BankStyleDetector().detect(ctx)
    assert detection.primary_style == "split_debit_credit"
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) >= 2
    assert records[0]["normalized"]["direction"] == "income"


@pytest.mark.integration
def test_style_matrix_synthetic_signed_amount():
    from docmirror.plugins.bank_statement.context import StyleContext
    from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
    from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
    from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
    from tests.unit.test_bank_styles_signed_amount import SIGNED_TABLE

    ctx = StyleContext(
        tables=SIGNED_TABLE,
        full_text="符号金额银行流水",
        institution=None,
        page_count=1,
    )
    detection = BankStyleDetector().detect(ctx)
    assert detection.primary_style == "signed_amount"
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) == 3
    assert records[0]["normalized"]["direction"] == "income"


@pytest.mark.integration
def test_style_matrix_synthetic_borderless_ocr():
    from docmirror.plugins.bank_statement.context import StyleContext
    from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
    from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
    from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
    from tests.unit.test_bank_styles_borderless_ocr import OCR_BORDERLESS_TABLE

    ctx = StyleContext(
        tables=OCR_BORDERLESS_TABLE,
        full_text="个人客户交易明细 中国工商银行",
        institution=None,
        page_count=1,
    )
    detection = BankStyleDetector().detect(ctx)
    assert detection.primary_style == "borderless_ocr"
    plugin = BankStatementCommunityPlugin()
    records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)
    assert len(records) >= 3


BOC = Path("tests/fixtures/bank_statement/中国银行-南京创沃电气设备有限公司_1.pdf")


@pytest.mark.integration
@pytest.mark.parametrize(
    "min_rows,min_coverage",
    [(71, 0.95)],
)
def test_style_matrix_boc_pipe_text(min_rows: int, min_coverage: float):
    if not BOC.is_file():
        pytest.skip("missing BOC fixture")

    mirror = asyncio.run(
        perceive_document(BOC, PerceiveOptions(enhance_mode="standard"))
    ).mirror

    out = run_plugin_extract_sync(
        mirror,
        edition="community",
        full_text=mirror.full_text,
        file_path=str(BOC),
    )
    assert out is not None
    props = out["document"]["properties"]
    assert props.get("style_id") == "split_debit_credit"
    assert props.get("reconstruction_source") in ("pipe_text", "mirror_table")
    assert props.get("coverage_ratio", 0) >= min_coverage

    records = out["data"]["records"]
    assert len(records) >= min_rows
    dated = [r.get("normalized", {}).get("date") for r in records if r.get("normalized", {}).get("date")]
    assert any(d == "2022-04-01" for d in dated)
    sample = next(r["normalized"] for r in records if r.get("normalized", {}).get("date") == "2022-04-01")
    assert sample.get("direction") in ("income", "expense")
    assert sample.get("counter_party")

    fields = out["data"].get("fields", {})
    holder = fields.get("account_holder", {}).get("normalized_value")
    if holder:
        assert holder == "南京创沃电气设备有限公司"
