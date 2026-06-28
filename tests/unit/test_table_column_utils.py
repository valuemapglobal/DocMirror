# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Tests for effective table column counting."""

from __future__ import annotations

from docmirror.structure.tables.table_column_utils import effective_table_column_count
from docmirror.models.entities.parse_result import CellValue, TableBlock, TableRow


def test_pipe_delimited_header_counts_as_multi_column():
    table = TableBlock(
        headers=["| 交易日期 | 摘要 | 收入 | 支出 | 余额 |"],
        rows=[TableRow(cells=[CellValue(text="2024-01-01")])],
    )
    assert effective_table_column_count(table) == 5


def test_normal_headers():
    table = TableBlock(
        headers=["A", "B", "C"],
        rows=[TableRow(cells=[CellValue(text="1"), CellValue(text="2"), CellValue(text="3")])],
    )
    assert effective_table_column_count(table) == 3
