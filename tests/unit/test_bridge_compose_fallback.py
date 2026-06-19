# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bridge fallback uses merger quarantine + LTQG export pipeline (extractor parity)."""

from __future__ import annotations

from docmirror.core.bridge.parse_result_bridge import ParseResultBridge
from docmirror.core.table.compose.composer import TableComposer
from docmirror.core.table.compose.export_pipeline import page_content_to_layouts
from docmirror.models.entities.domain import BaseResult, Block, PageLayout


def _table_page(num: int, rows: list[list[str]]) -> PageLayout:
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


def test_bridge_fallback_preserves_quarantined_merge_groups_in_mirror():
    headers = [
        "交易日期",
        "摘要",
        "借方发生额",
        "贷方发生额",
        "余额",
        "备注",
        "渠道",
        "流水",
    ]
    data = ["2024-01-01", "test", "100.00", "", "1000.00", "", "", "1"]
    pages = (
        _table_page(1, [headers, data, data]),
        _table_page(2, [headers, data, data]),
        _table_page(3, [["footnote only"]]),
    )
    base = BaseResult(
        pages=pages,
        full_text="银行流水 交易明细",
        metadata={
            "layout_profile_id": "borderless_ledger_bank",
            "pre_analysis": {
                "scene_hint": "bank_statement",
                "content_type": "table_dominant",
            },
        },
    )
    pr = ParseResultBridge.from_base_result(base)
    assert len(pr.logical_tables) == 2
    assert pr.logical_tables[0].source_pages == [1, 2]
    assert pr.logical_tables[1].merge_method == "quarantine_standalone"
    assert pr.logical_tables[1].source_pages == [3]

    spe = pr.parser_info.structure or {}
    assert spe.get("quarantined_physical_count") == 1
    assert spe.get("ltqg_enabled") is True


def test_bridge_fallback_differs_from_legacy_compose_heuristic():
    """Mirror keeps quarantined pages as standalone logical tables; legacy compose used header heuristics."""
    headers = ["c"] * 8
    pages = (
        _table_page(1, [headers] + [headers] * 2),
        _table_page(2, [headers] + [headers] * 2),
        _table_page(3, [["footnote only"]]),
    )
    base = BaseResult(pages=pages, full_text="", metadata={})
    pr = ParseResultBridge.from_base_result(base)
    assert len(pr.logical_tables) == 2
    assert pr.logical_tables[1].merge_method == "quarantine_standalone"

    parse_pages = ParseResultBridge.from_base_result(base).pages
    legacy = TableComposer().compose(parse_pages)
    assert len(legacy) >= 2


def test_page_content_to_layouts_enables_fallback_without_base_pages():
    headers = ["H1", "H2"]
    pages = (
        _table_page(1, [headers, ["a", "b"]]),
        _table_page(2, [headers, ["c", "d"]]),
    )
    base = BaseResult(pages=pages, full_text="", metadata={})
    pr = ParseResultBridge.from_base_result(base)
    layouts = page_content_to_layouts(pr.pages)
    assert len(layouts) == 2
    assert layouts[0].blocks[0].raw_content[0] == headers
