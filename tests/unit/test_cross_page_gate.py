# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Tests for cross-page quality gate (CROSS_PAGE_CHECK)."""

from docmirror.eval.gates import cross_page_check
from docmirror.models.entities.parse_result import CellValue, LogicalTable, ParseResult, RowType, TableRow


def test_cross_page_check_passes_high_confidence():
    result = ParseResult(
        logical_tables=[
            LogicalTable(
                logical_id="lt_0",
                table_id="lt_0",
                merge_method="cross_page_continuation",
                merge_confidence=0.95,
                source_pages=[1, 2, 3],
                row_count=10,
            )
        ]
    )
    gate = cross_page_check(result, confidence_threshold=0.7)
    assert gate.passed
    assert gate.checks["has_logical_tables"]


def test_cross_page_check_fails_low_confidence():
    result = ParseResult(
        logical_tables=[
            LogicalTable(
                logical_id="lt_0",
                table_id="lt_0",
                merge_method="cross_page_continuation",
                merge_confidence=0.4,
                source_pages=[1, 2],
                row_count=5,
            )
        ]
    )
    gate = cross_page_check(result, confidence_threshold=0.7)
    assert not gate.passed
    assert any("merge_confidence" in f for f in gate.failures)
