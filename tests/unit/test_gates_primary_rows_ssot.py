# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""EXTRACT_GATE primary row count uses Mirror LTQG SSOT."""

from __future__ import annotations

from docmirror.eval.gates import _primary_logical_row_count
from docmirror.models.entities.parse_result import CellValue, LogicalTable, ParseResult, ParserInfo, RowType, TableRow


def test_primary_logical_row_count_uses_ltqg_not_raw_max():
    good = LogicalTable(
        headers=["交易日期", "摘要", "余额"],
        rows=[TableRow(cells=[CellValue(text="2024-01-01")], row_type=RowType.DATA)],
        row_count=47,
        logical_id="lt_0",
        quality_passed=True,
        data_row_estimate=47,
    )
    bad = LogicalTable(
        headers=["", "", ""],
        rows=[TableRow(cells=[CellValue(text="?")], row_type=RowType.DATA) for _ in range(127)],
        row_count=127,
        logical_id="lt_1",
        quality_passed=False,
        data_row_estimate=0,
    )
    pr = ParseResult(
        logical_tables=[good, bad],
        parser_info=ParserInfo(
            structure={
                "ltqg_enabled": True,
                "ltqg_expected_data_rows": 47,
            }
        ),
    )
    assert _primary_logical_row_count(pr) == 47
