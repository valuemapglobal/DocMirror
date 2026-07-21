# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared logical export pipeline for extraction and canonical assembly."""

from __future__ import annotations

from docmirror.models.entities.domain import Block, PageLayout
from docmirror.tables.compose.export_pipeline import compose_logical_export_from_layouts


def _page(num: int, rows: list[list[str]]) -> PageLayout:
    return PageLayout(
        page_number=num,
        blocks=(
            Block(
                block_id=f"p{num}",
                block_type="table",
                raw_content=rows,
                page=num,
                reading_order=0,
            ),
        ),
    )


def test_export_pipeline_merges_continuation_pages():
    pages = [
        _page(1, [["A", "B"], ["1", "2"]]),
        _page(2, [["A", "B"], ["3", "4"]]),
    ]
    result = compose_logical_export_from_layouts(pages)
    assert len(result.export_logical) == 1
    assert result.export_logical[0].row_count == 2


def test_export_pipeline_quarantines_col_mismatch_tail():
    headers = ["c"] * 8
    pages = [
        _page(1, [headers] + [headers] * 2),
        _page(2, [["tail"]]),
    ]
    result = compose_logical_export_from_layouts(pages)
    assert len(result.export_logical) == 1
    assert len(result.quarantined_physical) == 1
    assert len(result.skipped_logical) == 1
    assert result.skipped_logical[0].merge_method == "quarantine_standalone"
    assert result.skipped_logical[0].source_pages == [2]
