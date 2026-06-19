# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Merger fragment quarantine for bank-statement profiles."""

from __future__ import annotations

from docmirror.core.table.merge.merger import collect_quarantined_tables
from docmirror.models.entities.domain import Block, PageLayout


def _bank_profile():
    class _Profile:
        profile_id = "borderless_ledger_bank"
        document_type_hint = "bank_statement"

        def is_borderless_ledger(self):
            return True

    return _Profile()


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


def test_fragment_table_quarantined_for_bank_profile():
    fragment_rows = [["?", "", "", ""] for _ in range(30)]
    pages = [_page(4, fragment_rows)]
    quarantined = collect_quarantined_tables(pages, profile=_bank_profile())
    reasons = {q["reason"] for q in quarantined}
    assert "fragment_table" in reasons
    frag = next(q for q in quarantined if q["reason"] == "fragment_table")
    assert frag["page"] == 4


def test_fragment_after_good_table_with_col_mismatch():
    good_rows = [
        ["交易日期", "摘要", "借方发生额", "贷方发生额", "余额", "备注", "渠道", "流水"],
        ["2024-01-01", "test", "100.00", "", "1000.00", "", "", "1"],
    ]
    fragment_rows = [["?", "", "", ""] for _ in range(30)]
    pages = [_page(1, good_rows), _page(4, fragment_rows)]
    quarantined = collect_quarantined_tables(pages, profile=_bank_profile())
    reasons = {q["reason"] for q in quarantined}
    assert "fragment_table" in reasons or "col_count_mismatch" in reasons


def test_fragment_quarantine_skipped_for_wechat_profile():
    class _Profile:
        profile_id = "borderless_ledger_wechat"
        document_type_hint = "wechat_payment"

        def is_borderless_ledger(self):
            return True

    fragment_rows = [[str(i), "?", "", ""] for i in range(30)]
    pages = [_page(1, fragment_rows)]
    quarantined = collect_quarantined_tables(pages, profile=_Profile())
    assert quarantined == []
