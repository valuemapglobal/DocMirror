# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Unit tests for TableComposer and cross-page merge group planning."""

from docmirror.core.table.compose.composer import TableComposer
from docmirror.core.table.merge.merger import collect_cross_page_merge_groups
from docmirror.models.entities.domain import Block, PageLayout
from docmirror.models.entities.layout_profile import LayoutProfile


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


class TestCollectCrossPageMergeGroups:
    def test_merges_matching_continuation_pages(self):
        pages = [
            _page(1, [["A", "B"], ["1", "2"], ["3", "4"]]),
            _page(2, [["A", "B"], ["5", "6"]]),
        ]
        groups = collect_cross_page_merge_groups(pages)
        assert len(groups) == 1
        assert groups[0]["pages"] == [1, 2]
        assert len(groups[0]["rows"]) == 4  # header + 3 data rows

    def test_splits_independent_tables(self):
        pages = [
            _page(1, [["A", "B"], ["1", "2"]]),
            _page(2, [["W1", "W2", "W3", "W4"], ["a", "b", "c", "d"]]),
        ]
        groups = collect_cross_page_merge_groups(pages)
        assert len(groups) == 2


class TestTableComposer:
    def test_from_page_layouts_produces_logical_table(self):
        pages = [
            _page(1, [["收/支", "金额"], ["支出", "10"]]),
            _page(2, [["收/支", "金额"], ["收入", "20"]]),
        ]
        logical = TableComposer.from_page_layouts(pages)
        assert len(logical) == 1
        assert logical[0].row_count == 2
        assert logical[0].source_pages == [1, 2]

    def test_skips_compose_when_profile_requests_skip(self):
        pages = [_page(1, [["A"], ["1"]])]
        profile = LayoutProfile(profile_id="credit", mirror_skip_cross_page_merge=True)
        logical = TableComposer.from_page_layouts(pages, profile=profile)
        assert len(logical) == 1
        assert logical[0].merge_method == "none"
        assert logical[0].source_physical_ids == ["pt_1_0"]

    def test_physical_ids_on_rows(self):
        pages = [
            _page(1, [["H1", "H2"], ["a", "b"]]),
            _page(2, [["H1", "H2"], ["c", "d"]]),
        ]
        logical = TableComposer.from_page_layouts(pages)
        assert logical[0].logical_id == "lt_0"
        assert logical[0].rows[0].source_physical_id == "pt_1_0"
        assert logical[0].rows[1].source_physical_id == "pt_2_0"
        assert logical[0].merge_method == "cross_page_continuation"
