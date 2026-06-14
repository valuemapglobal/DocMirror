# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Unit tests for table_access unified read layer."""

from docmirror.core.table.access import get_logical_tables, table_flatten
from docmirror.models.entities.parse_result import (
    CellValue,
    LogicalTable,
    PageContent,
    ParseResult,
    RowType,
    TableBlock,
    TableRow,
)


def _result_with_logical() -> ParseResult:
    return ParseResult(
        logical_tables=[
            LogicalTable(
                table_id="lt_0",
                headers=["收/支", "金额"],
                rows=[
                    TableRow(
                        cells=[CellValue(text="支出"), CellValue(text="10")],
                        row_type=RowType.DATA,
                        source_page=1,
                    )
                ],
                row_count=1,
                source_pages=[1],
                page_span=(1, 1),
            )
        ]
    )


def _legacy_merged_result() -> ParseResult:
    return ParseResult(
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        table_id="page1_table0",
                        headers=["收/支", "金额"],
                        rows=[
                            TableRow(
                                cells=[CellValue(text="支出"), CellValue(text="10")],
                                row_type=RowType.DATA,
                                source_page=1,
                            )
                        ],
                    )
                ],
            )
        ]
    )


class TestTableAccess:
    def test_prefers_logical_tables(self):
        result = _result_with_logical()
        tables = get_logical_tables(result)
        assert len(tables) == 1
        assert tables[0].table_id == "lt_0"

    def test_fallback_to_physical_page_one(self):
        result = _legacy_merged_result()
        tables = get_logical_tables(result)
        assert len(tables) == 1
        assert tables[0].headers == ["收/支", "金额"]

    def test_table_flatten(self):
        rows = table_flatten(_result_with_logical())
        assert rows == [{"收/支": "支出", "金额": "10"}]
