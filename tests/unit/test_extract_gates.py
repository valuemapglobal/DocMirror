# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for EXTRACT_GATE oracle mode and dual-view consistency."""

from docmirror.eval.gates import (
    GATE_PROFILES,
    OracleMode,
    dual_view_consistency_check,
    extract_row_preservation_check,
)
from docmirror.models.entities.parse_result import (
    CellValue,
    LogicalTable,
    PageContent,
    ParseResult,
    TableBlock,
    TableRow,
)


def _make_row(cells: list[str], page: int = 1) -> TableRow:
    return TableRow(
        cells=[CellValue(text=c) for c in cells],
        source_page=page,
    )


def test_extract_row_preservation_oracle_mode():
    profile = GATE_PROFILES["wechat_payment"]
    assert profile.oracle_mode == OracleMode.PDFPLUMBER_FULL_PAGE_SAMPLE

    result = ParseResult(
        logical_tables=[
            LogicalTable(
                logical_id="lt_primary",
                table_id="lt_primary",
                row_count=5111,
                source_pages=list(range(1, 220)),
            ),
            LogicalTable(
                logical_id="lt_q",
                table_id="lt_q",
                row_count=6,
                source_pages=[219],
            ),
        ]
    )
    gate = extract_row_preservation_check(
        result,
        profile=profile,
        oracle_row_count=5100,
    )
    assert gate.checks["min_logical_rows"]
    assert gate.checks["max_logical_rows"]
    assert gate.checks["row_preservation"]
    assert gate.metrics["row_preservation_ratio"] >= 0.995


def test_extract_row_preservation_oracle_mode_fails_low_ratio():
    profile = GATE_PROFILES["wechat_payment"]
    result = ParseResult(
        logical_tables=[
            LogicalTable(logical_id="lt", table_id="lt", row_count=4000, source_pages=[1, 2]),
        ]
    )
    gate = extract_row_preservation_check(
        result,
        profile=profile,
        oracle_row_count=5000,
    )
    assert not gate.checks["row_preservation"]
    assert not gate.passed


def test_dual_view_consistency_with_quarantine():
    rows = [[f"c{i}", "x"] for i in range(10)]
    page = PageContent(
        page_number=1,
        tables=[TableBlock(table_id="t1", rows=[_make_row(r, 1) for r in rows])],
    )
    result = ParseResult(
        pages=[page],
        logical_tables=[
            LogicalTable(logical_id="lt_primary", table_id="lt_primary", row_count=10, source_pages=[1]),
            LogicalTable(logical_id="lt_q", table_id="lt_q", row_count=3, source_pages=[2]),
        ],
    )
    quarantined = [{"page": 2, "row_count": 3, "reason": "col_count_mismatch"}]
    gate = dual_view_consistency_check(result, quarantined_tables=quarantined)
    assert gate.checks["primary_le_total_logical"]
    assert gate.checks["secondary_logical_bounded"]
    assert gate.passed


def test_dual_view_consistency_fails_unexplained_gap():
    result = ParseResult(
        logical_tables=[
            LogicalTable(logical_id="lt_primary", table_id="lt_primary", row_count=100, source_pages=[1]),
            LogicalTable(logical_id="lt_extra", table_id="lt_extra", row_count=50, source_pages=[2]),
        ],
    )
    gate = dual_view_consistency_check(result, quarantined_tables=[])
    assert not gate.checks["secondary_logical_bounded"]
    assert not gate.passed
