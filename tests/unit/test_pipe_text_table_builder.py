# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for pipe-delimited text table builder (BOC / mainframe ASCII ledgers)."""

from __future__ import annotations

from docmirror.structure.tables.pipe_row_merge import merge_pipe_continuation_rows
from docmirror.plugins.bank_statement.pipe_text_table_builder import (
    build_tables_from_pipe_text,
    count_expected_primary_rows,
    detect_pipe_header_in_text,
    split_pipe_row,
)

BOC_HEADER = (
    "|序号|记账日|起息日|交易类型|凭证|         凭证号码/业务编号/用途/摘要         |"
    "    借方发生额    |    贷方发生额    |        余额        |    机构/柜员/流水     |           备注           |"
)
BOC_ROW1 = (
    "| 1  |220401|220401|网上支付|    |3235840008882022040194831167/票号130230103293|"
    "                  |         49,234.67|           56,020.44|06257/9880809/43627150 |深圳前海微众银行股份有限公|"
)
BOC_CONT = (
    "|    |      |      |        |    |820220316190626506票据金额50,000元贴现款     |"
    "                  |                  |                    |                       |司/深圳前海微众银行股份有 |"
)


def _synthetic_boc_text(extra_rows: list[str] | None = None) -> str:
    rows = extra_rows or []
    return "\n".join([
        "账号     544362180589         账户名称  南京创沃电气设备有限公司",
        "开户行     中国银行南京浦东路支行",
        "───────────────────────────────────────────────",
        BOC_HEADER,
        "───────────────────────────────────────────────",
        BOC_ROW1,
        BOC_CONT,
        *rows,
    ])


def test_detect_boc_header():
    text = _synthetic_boc_text()
    assert detect_pipe_header_in_text(text) is True
    assert detect_pipe_header_in_text("random text without pipes") is False


def test_split_pipe_row():
    cells = split_pipe_row(BOC_ROW1)
    assert cells[0] == "1"
    assert cells[1] == "220401"
    assert "49,234.67" in cells[7]


def test_merge_continuation_rows():
    header = split_pipe_row(BOC_HEADER)
    row1 = split_pipe_row(BOC_ROW1)
    cont = split_pipe_row(BOC_CONT)
    table = merge_pipe_continuation_rows([header, row1, cont])
    assert len(table) == 2
    assert "深圳前海微众银行" in table[1][-1]


def test_build_tables_from_pipe_text():
    rows = []
    for i in range(2, 76):
        rows.append(
            f"| {i:2d} |220401|220401|网上支付|    |ref{i}|        100.00|                  |"
            f"           {1000 + i}.00|ref |counterparty |"
        )
    text = _synthetic_boc_text(rows)
    tables = build_tables_from_pipe_text(text)
    assert len(tables) == 1
    assert len(tables[0]) - 1 == 75
    assert count_expected_primary_rows(text) == 75


def test_multi_page_dedupe_headers():
    page2_header = BOC_HEADER
    page2_row = (
        "| 76 |220428|220428|网上支付|    |last-txn|          10.00|                  |"
        "           100.00|ref |note |"
    )
    text = _synthetic_boc_text() + "\n" + page2_header + "\n" + page2_row
    tables = build_tables_from_pipe_text(text)
    assert len(tables[0]) - 1 == 2
