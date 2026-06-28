# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.output.exporters.dispatch import export_parse_result
from docmirror.models.entities.parse_result import (
    CellValue,
    PageContent,
    ParseResult,
    TableBlock,
    TableRow,
    TextBlock,
    TextLevel,
)


def test_markdown_exporter_renders_headings_and_tables():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                texts=[TextBlock(content="Doc Title", level=TextLevel.H1), TextBlock(content="Body")],
                tables=[
                    TableBlock(
                        headers=["Col"],
                        rows=[TableRow(cells=[CellValue(text="Value")])],
                    )
                ],
            )
        ]
    )

    payload, media_type, suffix = export_parse_result(result, "markdown")

    assert media_type == "text/markdown"
    assert suffix == ".md"
    assert "# Doc Title" in payload
    assert "| Col |" in payload
    assert "| Value |" in payload
