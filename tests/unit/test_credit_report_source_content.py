# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from docmirror.models.entities.parse_result import CellValue, PageContent, ParseResult, TableBlock, TableRow
from docmirror.plugins.credit_report.source_content import build_credit_source_content


def test_credit_source_content_preserves_every_table_cell() -> None:
    result = ParseResult(
        pages=[
            PageContent(
                page_number=3,
                source_page_number=2,
                width=596,
                height=419,
                tables=[
                    TableBlock(
                        table_id="pt_3_0",
                        headers=["管理机构", "账户标识"],
                        rows=[
                            TableRow(
                                cells=[
                                    CellValue(text="某银行", bbox=[10, 20, 100, 40], evidence_ids=["e1"]),
                                    CellValue(text="ABC123", bbox=[100, 20, 200, 40], evidence_ids=["e2"]),
                                ]
                            )
                        ],
                    )
                ],
            )
        ]
    )

    source = build_credit_source_content(result)

    assert source["logical_page_count"] == 1
    assert source["source_page_count"] == 1
    assert source["table_count"] == 1
    assert source["non_empty_table_cell_count"] == 4
    table = source["source_tables"][0]
    assert table["headers"] == ["管理机构", "账户标识"]
    assert table["rows"][0][1]["text"] == "ABC123"
    assert table["rows"][0][1]["evidence_ids"] == ["e2"]
