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

    assert "code" not in standard
    assert "message" not in standard
    assert "data" not in standard
    assert "meta" not in standard
    assert "metadata" not in standard
    assert "request_id" not in standard
    assert "timestamp" not in standard
    assert standard["mirror"]["schema"] == "docmirror.mirror_json"
    assert standard["source"]["provenance"]["output_ids"]["request_id"]
    assert forensic["mirror"]["profile"] == "forensic"

    standard_table = next(block for block in standard["blocks"] if block["type"] == "table")
    forensic_table = next(block for block in forensic["blocks"] if block["type"] == "table")
    standard_cell = standard_table["content"]["grid"]["cells"][-1]
    forensic_cell = forensic_table["content"]["grid"]["cells"][-1]

    assert standard_cell["text"] == "A1"
    assert forensic_cell["text"] == "A1"
    assert forensic_cell["bbox"] == [1, 2, 3, 4]
    assert forensic_cell["evidence_ids"]
