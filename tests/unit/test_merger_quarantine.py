# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for merger quarantine collection."""

from docmirror.models.entities.domain import Block, PageLayout
from docmirror.tables.cross_page_fusion import collect_quarantined_tables


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


def test_collect_quarantined_tables_header_mismatch_with_profile():
    """Borderless ledger: pseudo-header tail page quarantined (wechat page 219 pattern)."""

    class _Profile:
        merge_quarantine_on_col_mismatch = True

        def is_borderless_ledger(self):
            return True

    pages = [
        _page(1, [["交易单号", "交易时间", "交易类型", "收/支/其他", "交易方式", "金额(元)", "交易对方", "商户单号"]]
        + [["d"] * 8] * 2),
        _page(2, [["1.免责声明", "col2", "col3", "col4", "col5", "col6", "col7", "col8"]]),
    ]
    quarantined = collect_quarantined_tables(pages, profile=_Profile())
    assert len(quarantined) == 1
    assert quarantined[0]["page"] == 2
    assert quarantined[0]["reason"] == "col_count_mismatch"


def test_collect_quarantined_tables_keeps_97_stable_jsb_like_rows():
    rows = [["交易日期", "摘要", "借方发生额", "贷方发生额", "余额", "对方户名", "渠道", "流水号"]]
    rows.extend([["2026-01-01", "转账", "100.00", "", "900.00", "张三", "柜面", str(i)] for i in range(97)])
    pages = [_page(1, rows)]

    assert collect_quarantined_tables(pages) == []
