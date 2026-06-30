# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Integration tests for table layer dual-view (design doc §10.2)."""

from __future__ import annotations

from docmirror.models.entities.domain import Block, PageLayout
from docmirror.tables.compose.composer import TableComposer


def _page(page_number: int, rows: list[list[str]]) -> PageLayout:
    return PageLayout(
        page_number=page_number,
        blocks=(
            Block(
                block_id=f"p{page_number}_t0",
                block_type="table",
                raw_content=rows,
                page=page_number,
                reading_order=1,
            ),
        ),
    )


class TestTableLayerSynthetic:
    """Fast synthetic fixtures — no OCR."""

    def test_three_page_bank_ledger_logical_merge(self):
        pages = [
            _page(1, [["日期", "金额"], ["2024-01-01", "100"]]),
            _page(2, [["日期", "金额"], ["2024-01-02", "200"]]),
            _page(3, [["日期", "金额"], ["2024-01-03", "300"]]),
        ]
        logical = TableComposer.from_page_layouts(pages)
        assert len(logical) == 1
        assert logical[0].row_count == 3
        assert logical[0].source_pages == [1, 2, 3]
        assert logical[0].merge_method == "cross_page_continuation"

    def test_single_page_no_cross_page_merge(self):
        pages = [_page(1, [["名称"], ["测试公司"]])]
        logical = TableComposer.from_page_layouts(pages)
        assert len(logical) == 1
        assert logical[0].merge_method == "none"
        assert logical[0].source_pages == [1]
