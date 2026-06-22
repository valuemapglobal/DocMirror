# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.models.entities.parse_result import (
    CellValue,
    PageContent,
    ParseResult,
    TableBlock,
    TableRow,
    TextBlock,
)
from docmirror.models.mirror.completeness import build_mirror_completeness


def test_mirror_completeness_reports_geometry_and_refs():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=600,
                height=800,
                texts=[TextBlock(content="Title", bbox=[1, 2, 3, 4], evidence_ids=["e1"])],
                tables=[
                    TableBlock(
                        table_id="t1",
                        headers=["A"],
                        rows=[
                            TableRow(
                                cells=[
                                    CellValue(
                                        text="v",
                                        bbox=[1, 2, 3, 4],
                                        token_ids=["tok1"],
                                        source_cell_refs=[{"ref": "cell1"}],
                                    )
                                ]
                            )
                        ],
                    )
                ],
            )
        ]
    )

    profile = build_mirror_completeness(result)

    assert profile["text"] == "full"
    assert profile["bbox"] in {"block", "token"}
    assert profile["source_refs"] in {"partial", "full"}
    assert profile["counts"]["tables"] == 1
