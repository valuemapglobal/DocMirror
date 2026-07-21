# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.models.entities.parse_result import (
    CellValue,
    PageContent,
    ParseResult,
    TableBlock,
    TableRow,
    TextBlock,
    TextLevel,
)
from docmirror.output.exporters.dispatch import export_parse_result
from docmirror.output.markdown_renderer import MARKDOWN_PROFILE_MARKER, validate_markdown


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
    assert payload.startswith(MARKDOWN_PROFILE_MARKER)
    assert '<!-- docmirror:page logical="1" source="1" -->' in payload
    assert "# Doc Title" in payload
    assert "| Col |" in payload
    assert "| Value |" in payload
    assert validate_markdown(payload) == []


def test_markdown_exporter_removes_unmaterialized_ocr_image_markup():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                texts=[
                    TextBlock(content="Before"),
                    TextBlock(
                        content=(
                            '<div style="text-align: center;">'
                            '<img src="imgs/missing.jpg" alt="Image" width="24%" />'
                            "</div>"
                        )
                    ),
                    TextBlock(content="After ![Image](https://example.invalid/missing.jpg)"),
                ],
            )
        ]
    )

    payload, _, _ = export_parse_result(result, "markdown")

    assert "Before" in payload
    assert "After" in payload
    assert "missing.jpg" not in payload
    assert "<div" not in payload
    assert "<img" not in payload
    assert "![" not in payload
    assert payload.count('<!-- docmirror:nontext type="image" disposition="omitted" -->') == 2
    assert validate_markdown(payload) == []


def test_markdown_exporter_neutralizes_provider_markdown_and_html():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                texts=[TextBlock(content="# forged heading\n\n- forged list\n\n<script>alert(1)</script>")],
            )
        ]
    )

    payload, _, _ = export_parse_result(result, "markdown")

    assert "\\# forged heading" in payload
    assert "\\- forged list" in payload
    assert "<script" not in payload
    assert validate_markdown(payload) == []


def test_markdown_exporter_flattens_headerless_spans_to_gfm():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        rows=[
                            TableRow(
                                cells=[CellValue(text="A", row_span=2), CellValue(text="B")],
                            ),
                            TableRow(cells=[CellValue(text="C", col_index=1)]),
                        ]
                    )
                ],
            )
        ]
    )

    payload, _, _ = export_parse_result(result, "markdown")

    assert "|  |  |" in payload
    assert "| A | B |" in payload
    assert "|  | C |" in payload
    assert "<table>" not in payload
    assert validate_markdown(payload) == []


def test_markdown_exporter_rejects_raw_html_tables():
    assert "forbidden_html_tag:table" in validate_markdown("<table><tr><td>A</td></tr></table>")


def test_markdown_exporter_preserves_cells_covered_by_invalid_span():
    header = ["收/支", "交易对方", "商品说明", "收/付款方式", "金额", "交易订单号", "商家订单号", "交易时间"]
    raw_rows = [
        ["交易时间段：2022-06-12 至 2023-06-11", "", "", "", "", "", "", ""],
        ["交易类型：全部", "", "", "", "", "", "", ""],
        header,
        ["支出", "示例商户", "商品", "花呗", "47.40", "2023061122001", "T200P1", "2023-06-11\n23:08:45"],
    ]
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        headers=raw_rows[0],
                        rows=[],
                        metadata={
                            "raw_rows": raw_rows,
                            "geometry": {
                                "cell_spans": [
                                    {"row": 0, "col": 0, "row_span": 1, "col_span": 8},
                                    {"row": 1, "col": 0, "row_span": 1, "col_span": 8},
                                    {"row": 2, "col": 0, "row_span": 1, "col_span": 8},
                                ]
                            },
                        },
                    )
                ],
            )
        ]
    )

    payload, _, _ = export_parse_result(result, "markdown")

    assert "交易时间段：2022-06-12 至 2023-06-11" in payload
    assert "| " + " | ".join(header) + " |" in payload
    assert "| 支出 | 示例商户 |" in payload
    assert "2023-06-11 23:08:45" in payload
    assert not any(tag in payload for tag in ("<table", "<tr", "<td", "<th", "<br>"))


def test_markdown_exporter_does_not_duplicate_unproven_geometric_table():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                texts=[TextBlock(content="姓名测试用户"), TextBlock(content="性别女 民族汉")],
                tables=[
                    TableBlock(
                        table_id="geo_table_0",
                        rows=[
                            TableRow(cells=[CellValue(text="姓名测试用户"), CellValue(text="")]),
                            TableRow(cells=[CellValue(text="性别女"), CellValue(text="民族汉")]),
                        ],
                        metadata={"source": "geometric_reconstructor"},
                    )
                ],
            )
        ]
    )

    payload, _, _ = export_parse_result(result, "markdown")

    assert payload.count("姓名测试用户") == 1
    assert payload.count("性别女 民族汉") == 1
    assert "<table>" not in payload
    assert validate_markdown(payload) == []
