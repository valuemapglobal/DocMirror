# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Tests for CSV/Parquet tabular exporters."""

from __future__ import annotations

import pytest

from docmirror.output.exporters.tabular import export_parse_result, export_tables_to_csv
from docmirror.models.entities.parse_result import CellValue, PageContent, ParseResult, TableBlock, TableRow


def _result_with_table() -> ParseResult:
    table = TableBlock(
        table_id="t1",
        headers=["日期", "金额"],
        rows=[TableRow(cells=[CellValue(text="2024-01-01"), CellValue(text="100")])],
    )
    page = PageContent(page_number=1, tables=[table])
    return ParseResult(pages=[page])


def test_export_tables_to_csv():
    csv_text = export_tables_to_csv(_result_with_table())
    assert "日期" in csv_text
    assert "2024-01-01" in csv_text
    assert "# table_1" in csv_text


def test_export_parse_result_csv():
    payload, media_type, suffix = export_parse_result(_result_with_table(), "csv")
    assert media_type == "text/csv"
    assert suffix == ".csv"
    assert "金额" in payload


def test_export_parse_result_parquet_optional():
    pytest.importorskip("pyarrow")
    payload, media_type, suffix = export_parse_result(_result_with_table(), "parquet")
    assert media_type == "application/octet-stream"
    assert suffix == ".parquet"
    assert len(payload) > 0
