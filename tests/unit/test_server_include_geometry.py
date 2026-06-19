# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from docmirror.models.entities.parse_result import CellValue, PageContent, ParseResult, TableBlock, TableRow
from docmirror.server.output_builder import build_api_response


def test_build_api_response_mirror_level_forensic_includes_geometry():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        rows=[
                            TableRow(
                                cells=[
                                    CellValue(
                                        text="A1",
                                        bbox=[1, 2, 3, 4],
                                        row_index=0,
                                        col_index=0,
                                        geometry_status="exact",
                                        geometry_source="unit",
                                        token_ids=["tok1"],
                                    )
                                ]
                            )
                        ]
                    )
                ],
            )
        ]
    )

    standard = build_api_response(result, mirror_level="standard")
    forensic = build_api_response(result, mirror_level="forensic")

    standard_cell = standard["data"]["document"]["pages"][0]["tables"][0]["rows"][0]["cells"][0]
    forensic_cell = forensic["data"]["document"]["pages"][0]["tables"][0]["rows"][0]["cells"][0]

    assert "bbox" not in standard_cell
    assert forensic_cell["bbox"] == [1, 2, 3, 4]
    assert forensic_cell["token_ids"] == ["tok1"]
