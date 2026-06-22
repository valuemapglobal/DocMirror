# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.models.entities.parse_result import DocumentSection, LogicalTable, ParseResult
from docmirror.models.mirror.document_structure import build_document_structure


def test_document_structure_uses_sections_and_cross_page_tables():
    result = ParseResult(
        sections=[DocumentSection(id="s1", title="交易明细", page_start=1, page_end=2)],
        logical_tables=[
            LogicalTable(
                table_id="lt1",
                source_pages=[1, 2],
                source_physical_ids=["p1_t1", "p2_t1"],
                merge_confidence=0.9,
            )
        ],
    )

    structure = build_document_structure(result)

    assert structure["outline"][0]["title"] == "交易明细"
    assert structure["flows"][0]["type"] == "cross_page_table"
    assert structure["flows"][0]["source_pages"] == [1, 2]
