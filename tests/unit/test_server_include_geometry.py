# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json

from docmirror.models.entities.parse_result import CellValue, PageContent, ParseResult, TableBlock, TableRow
from docmirror.models.sealed import seal_parse_result
from docmirror.output.mirror_projector import project_mirror


def test_mirror_projector_uses_fixed_canonical_contract():
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

    standard = project_mirror(seal_parse_result(result), mirror_level="standard")

    assert "code" not in standard
    assert "message" not in standard
    assert "data" not in standard
    assert "meta" not in standard
    assert "metadata" not in standard
    assert "request_id" not in standard
    assert "timestamp" not in standard
    assert standard["mirror"]["schema"] == "docmirror.mirror_json"
    assert standard["source"]["provenance"]["page_count"] == 1
    assert standard["mirror"]["profile"] == "canonical_full"
    serialized = json.dumps(standard)
    assert '"dmir"' not in serialized
    assert '"license_state"' not in serialized
    assert '"license_status"' not in serialized

    standard_table = next(block for block in standard["blocks"] if block["type"] == "table")
    standard_cell = standard_table["content"]["grid"]["cells"][-1]

    assert standard_cell["text"] == "A1"
