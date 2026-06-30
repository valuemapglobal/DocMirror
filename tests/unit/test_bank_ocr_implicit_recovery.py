# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OCR implicit table recovery tests for scanned bank ledgers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.ocr_implicit_table_recovery import (
    recover_ocr_implicit_ledger_tables,
    recovered_ocr_implicit_row_count,
)
from docmirror.plugins.bank_statement.styles import grid_standard


def _mirror_table(rows: list[list[str]]) -> dict:
    cells = []
    for row_idx, row in enumerate(rows):
        for col_idx, text in enumerate(row):
            cells.append({"row": row_idx, "col": col_idx, "text": text})
    return {
        "blocks": [
            {
                "type": "table",
                "content": {"grid": {"cells": cells}},
            }
        ]
    }


def test_recover_ocr_implicit_table_keeps_valid_rows_with_page_noise() -> None:
    mirror = _mirror_table(
        [
            ["交易日期", "月收/支", "交易金额", "账户余额", "摘要", "对方账号", "对方户名凭证序号", "机构", "柜员", "备注信息"],
            ["20221008", "支出", "4.00", "1256.57", "POS消费", "第3页", "Q", "OB8B9E", "ORD95E", "D02"],
            ["20221009", "支山", "4.00", "1252.57", "POS消费", "", "", "", "", ""],
        ]
    )
    parse_result = SimpleNamespace(mirror=mirror)

    tables = recover_ocr_implicit_ledger_tables(parse_result, "")
    assert len(tables) == 1
    assert len(tables[0]) == 3

    ctx = StyleContext(tables=tables, full_text="", institution=None, page_count=1, parse_result=parse_result)
    plugin = BankStatementCommunityPlugin()
    raw = grid_standard.extract_transactions(ctx, plugin)
    records = [grid_standard.normalize_record(row, plugin) for row in raw]

    assert len(records) == 2
    assert records[0]["date"] == "2022-10-08"
    assert records[0]["direction"] == "expense"
    assert records[0]["amount"] == pytest.approx(4.0)
    assert records[1]["direction"] == "expense"


def test_recover_paragraph_ledger_rows_and_repairs_amount_balance_orientation() -> None:
    mirror = {
        "blocks": [
            {
                "type": "paragraph",
                "page_ids": ["page:0001"],
                "bbox": [30, 100, 560, 120],
                "text": "交易日期 收/支 交易金额 摘要 账户余额 对方账号 柜员 备注信息 对方户名凭证序号 机构",
            },
            {
                "type": "paragraph",
                "page_ids": ["page:0001"],
                "bbox": [30, 130, 520, 145],
                "text": "20220419 支出 2.00 944.75 网络付款 1500947831 0098 NY0035 2号生活馆",
            },
            {
                "type": "paragraph",
                "page_ids": ["page:0001"],
                "bbox": [30, 146, 520, 160],
                "text": "20220419 支出 800.00 144.75 网络付款 1000050001 0098 NY0024 微信转账",
            },
            {
                "type": "paragraph",
                "page_ids": ["page:0001"],
                "bbox": [30, 161, 520, 176],
                "text": "扫二维码 支出 20220420 网络付款 125.75 19. 00 1000107101 0098 NY0016 付款",
            },
            {
                "type": "paragraph",
                "page_ids": ["page:0001"],
                "bbox": [30, 177, 520, 192],
                "text": "收入 20220425 800.00 925.75 网络收款 243300133 0098 NY0062",
            },
        ]
    }
    parse_result = SimpleNamespace(mirror=mirror)

    tables = recover_ocr_implicit_ledger_tables(parse_result, "")
    assert len(tables) == 1
    assert len(tables[0]) == 5

    ctx = StyleContext(tables=tables, full_text="", institution=None, page_count=1, parse_result=parse_result)
    plugin = BankStatementCommunityPlugin()
    raw = grid_standard.extract_transactions(ctx, plugin)
    records = [grid_standard.normalize_record(row, plugin) for row in raw]

    assert [(r["amount"], r["balance"]) for r in records] == [
        (2.0, 944.75),
        (800.0, 144.75),
        (19.0, 125.75),
        (800.0, 925.75),
    ]


def test_recover_ocr_implicit_table_caches_tables_on_parse_result() -> None:
    mirror = _mirror_table(
        [
            ["交易日期", "收/支", "交易金额", "账户余额"],
            ["20240101", "收入", "10.00", "10.00"],
            ["20240102", "支出", "3.00", "7.00"],
        ]
    )
    parse_result = SimpleNamespace(
        mirror=mirror,
        entities=SimpleNamespace(domain_specific={}),
    )

    first = recover_ocr_implicit_ledger_tables(parse_result, "")
    assert recovered_ocr_implicit_row_count(parse_result) == 2

    first[0].append(["mutated"])
    parse_result.mirror = {"blocks": []}
    second = recover_ocr_implicit_ledger_tables(parse_result, "")

    assert len(second) == 1
    assert len(second[0]) == 3
    assert recovered_ocr_implicit_row_count(parse_result) == 2
