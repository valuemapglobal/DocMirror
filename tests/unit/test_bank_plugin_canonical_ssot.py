# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin coverage denominator uses Mirror LTQG SSOT."""

from __future__ import annotations

from docmirror.models.entities.parse_result import CellValue, LogicalTable, ParseResult, ParserInfo, RowType, TableRow
from docmirror.plugins.bank_statement.canonical import build_style_meta
from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.ltro import ReconstructionMeta
from docmirror.plugins.bank_statement.style_detector import StyleDetectionResult
from docmirror.plugins.bank_statement.style_registry import _expected_rows


def _detection() -> StyleDetectionResult:
    return StyleDetectionResult(
        primary_style="grid_standard",
        confidence=0.9,
        parser_chain=["grid_standard"],
        institution_hint="ccb",
    )


def _parse_result_with_ltqg(expected: int = 47) -> ParseResult:
    headers = ["交易日期", "摘要", "借方发生额", "贷方发生额", "余额"]
    rows = [
        TableRow(
            cells=[CellValue(text="2024-01-01"), CellValue(text="x"), CellValue(text="1.00")],
            row_type=RowType.DATA,
        )
        for _ in range(expected)
    ]
    return ParseResult(
        logical_tables=[
            LogicalTable(
                headers=headers,
                rows=rows,
                row_count=expected,
                quality_passed=True,
                data_row_estimate=expected,
            )
        ],
        parser_info=ParserInfo(
            structure={
                "ltqg_enabled": True,
                "ltqg_expected_data_rows": expected,
            }
        ),
    )


def test_build_style_meta_uses_mirror_expected_rows():
    pr = _parse_result_with_ltqg(47)
    meta = build_style_meta(
        _detection(),
        reconstruction=ReconstructionMeta(source="canonical_table", expected_primary_rows=127),
        record_count=40,
        parse_result=pr,
    )
    assert meta.expected_primary_rows == 47
    assert abs(meta.coverage_ratio - (40 / 47)) < 0.001


def test_style_registry_expected_rows_from_parse_result():
    pr = _parse_result_with_ltqg(47)
    ctx = StyleContext(
        tables=[[["交易日期", "摘要"], ["2024-01-01", "x"]]],
        full_text="",
        institution="ccb",
        page_count=1,
        parse_result=pr,
        reconstruction=ReconstructionMeta(source="canonical_table", expected_primary_rows=127),
    )
    expected = _expected_rows(ctx)
    assert expected == 47


def test_style_registry_expected_rows_prefers_cached_ocr_recovery_over_weak_mirror_count():
    pr = _parse_result_with_ltqg(2)
    pr.entities.domain_specific["_bank_ocr_implicit_recovery"] = {
        "status": "ready",
        "row_count": 128,
        "tables": [[["交易日期", "收/支"], *[["2024-01-01", "收入"] for _ in range(128)]]],
    }
    ctx = StyleContext(
        tables=[[["交易日期", "摘要"], ["2024-01-01", "x"]]],
        full_text="",
        institution="ccb",
        page_count=1,
        parse_result=pr,
        reconstruction=ReconstructionMeta(source="canonical_table", expected_primary_rows=2),
    )

    assert _expected_rows(ctx) == 128
