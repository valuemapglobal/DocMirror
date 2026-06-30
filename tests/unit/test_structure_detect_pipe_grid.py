# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDU pipe grid detection unit tests (Phase 0 / ADR-M13-03)."""

from __future__ import annotations

from docmirror.tables.structure_detect import (
    detect_pipe_grid_in_text,
    extract_header_zone,
)
from tests.unit.test_pipe_text_table_builder import BOC_HEADER, BOC_ROW1, _synthetic_boc_text


def _synthetic_boc_with_rows(row_count: int = 20) -> str:
    rows = []
    for i in range(2, row_count + 2):
        rows.append(
            f"| {i:2d} |220401|220401|网上支付|    |ref{i}|        100.00|                  |"
            f"           {1000 + i}.00|ref |counterparty |"
        )
    return _synthetic_boc_text(rows)


def test_boc_pipe_grid_high_confidence():
    signal = detect_pipe_grid_in_text(_synthetic_boc_with_rows(20))
    assert signal.header_detected is True
    assert signal.split_debit_credit is True
    assert signal.confidence >= 0.85
    assert signal.expected_primary_rows >= 1


def test_boc_header_snippet_detected():
    snippet = "\n".join([BOC_HEADER, BOC_ROW1])
    signal = detect_pipe_grid_in_text(snippet)
    assert signal.header_detected is True
    assert signal.split_debit_credit is True


def test_markdown_pipe_negative_low_confidence():
    md = "\n".join([
        "| Name | Age | City |",
        "| --- | --- | --- |",
        "| Alice | 30 | NYC |",
        "| Bob | 25 | LA |",
    ])
    signal = detect_pipe_grid_in_text(md)
    assert signal.confidence < 0.85


def test_no_pipes_zero_signal():
    signal = detect_pipe_grid_in_text("plain prose without tables")
    assert signal.header_detected is False
    assert signal.confidence == 0.0


def test_header_zone_respects_table_block():
    from docmirror.models.entities.parse_result import PageContent, ParseResult, TableBlock, TableRow, CellValue

    full = "户名 张三\n|序号|记账日|\n| 1 |220401|"
    pr = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        table_id="t1",
                        headers=["序号", "记账日"],
                        rows=[TableRow(cells=[CellValue(text="1"), CellValue(text="220401")])],
                    )
                ],
            )
        ]
    )
    zone = extract_header_zone(full, parse_result=pr)
    assert "序号" not in zone
    assert "户名" in zone
