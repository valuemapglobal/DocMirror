# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ADR-BS-07 export partition — passed vs quarantined logical tables."""

from __future__ import annotations

from docmirror.models.entities.parse_result import CellValue, LogicalTable, RowType, TableRow
from docmirror.tables.compose.ledger_quality import partition_export_logical_tables


def _lt(*, passed: bool, logical_id: str) -> LogicalTable:
    return LogicalTable(
        headers=["交易日期", "摘要", "余额"],
        rows=[TableRow(cells=[CellValue(text="2024-01-01")], row_type=RowType.DATA)],
        row_count=1,
        logical_id=logical_id,
        quality_passed=passed,
        data_row_estimate=1 if passed else 0,
        quality_skip_reason=None if passed else "fragment_table",
    )


def test_partition_export_splits_passed_and_skipped():
    good = _lt(passed=True, logical_id="lt_0")
    bad = _lt(passed=False, logical_id="lt_1")
    export, skipped = partition_export_logical_tables([good, bad])
    assert [lt.logical_id for lt in export] == ["lt_0"]
    assert [lt.logical_id for lt in skipped] == ["lt_1"]


def test_partition_export_all_passed():
    tables = [_lt(passed=True, logical_id="lt_0"), _lt(passed=True, logical_id="lt_1")]
    export, skipped = partition_export_logical_tables(tables)
    assert len(export) == 2
    assert skipped == []
