# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for merger quarantine collection."""

from docmirror.core.table.merger import collect_quarantined_tables
from docmirror.models.entities.domain import Block, PageLayout


def _page(num: int, rows: list[list[str]]) -> PageLayout:
    return PageLayout(
        page_number=num,
        width=600,
        height=800,
        blocks=(
            Block(
                block_id=f"t{num}",
                block_type="table",
                bbox=(0, 0, 600, 800),
                reading_order=0,
                page=num,
                raw_content=rows,
            ),
        ),
    )


def test_collect_quarantined_tables_empty():
    assert collect_quarantined_tables([]) == []


def test_collect_quarantined_tables_detects_col_mismatch():
    # Page 1: 8-col ledger; page 2: 1-col footnote → quarantine
    pages = [
        _page(1, [["h"] * 8] + [["d"] * 8] * 3),
        _page(2, [["footnote only"]]),
    ]
    quarantined = collect_quarantined_tables(pages)
    assert len(quarantined) == 1
    assert quarantined[0]["page"] == 2
    assert quarantined[0]["reason"] == "col_count_mismatch"
    assert quarantined[0]["action"] == "standalone_physical_table"
