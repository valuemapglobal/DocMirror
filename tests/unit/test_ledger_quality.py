# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Mirror LTQG (ledger table quality gate)."""

from __future__ import annotations

from docmirror.tables.compose.ledger_quality import (
    apply_ltqg,
    assess_logical_table,
    should_enable_ltqg,
    sum_passed_data_row_estimates,
)
from docmirror.models.entities.parse_result import CellValue, LogicalTable, RowType, TableRow


def _bank_profile():
    class _Profile:
        profile_id = "borderless_ledger_bank"
        document_type_hint = "bank_statement"

        def is_borderless_ledger(self):
            return True

    return _Profile()


def _wechat_profile():
    class _Profile:
        profile_id = "borderless_ledger_wechat"
        document_type_hint = "wechat_payment"

        def is_borderless_ledger(self):
            return True

    return _Profile()


def _data_row(date: str, amount: str) -> TableRow:
    return TableRow(
        cells=[CellValue(text=date), CellValue(text=amount), CellValue(text="100.00")],
        row_type=RowType.DATA,
        source_page=1,
    )


def test_should_enable_ltqg_bank_only():
    assert should_enable_ltqg(_bank_profile()) is True
    assert should_enable_ltqg(_wechat_profile()) is False
    assert should_enable_ltqg(None) is False


def test_good_ledger_table_passes_ltqg():
    lt = LogicalTable(
        headers=["交易日期", "摘要", "借方发生额", "贷方发生额", "余额"],
        rows=[_data_row("2024-01-01", "100.00") for _ in range(5)],
        row_count=5,
        source_pages=[1],
    )
    quality = assess_logical_table(lt)
    assert quality.passed is True
    assert quality.data_row_estimate == 5
    assert quality.skip_reason is None


def test_fragment_table_fails_ltqg():
    lt = LogicalTable(
        headers=["", "", "", ""],
        rows=[
            TableRow(
                cells=[CellValue(text="x"), CellValue(text=""), CellValue(text=""), CellValue(text="")],
                row_type=RowType.DATA,
            )
            for _ in range(40)
        ],
        row_count=40,
        source_pages=[4],
    )
    quality = assess_logical_table(lt)
    assert quality.passed is False
    assert quality.skip_reason in ("fragment_table", "header_missing", "low_quality_score")
    assert quality.data_row_estimate == 0


def test_apply_ltqg_skips_wechat_profile():
    lt = LogicalTable(
        headers=["", "", "", ""],
        rows=[TableRow(cells=[CellValue(text="x")], row_type=RowType.DATA) for _ in range(10)],
        row_count=10,
        source_pages=[1],
    )
    out, summary = apply_ltqg([lt], profile=_wechat_profile())
    assert summary.enabled is False
    assert out[0].quality_passed is True


def test_apply_ltqg_marks_bad_table_and_expected_sum():
    good = LogicalTable(
        headers=["交易日期", "摘要", "借方发生额", "贷方发生额", "余额"],
        rows=[_data_row("2024-01-02", "50.00") for _ in range(3)],
        row_count=3,
        source_pages=[1],
    )
    bad = LogicalTable(
        headers=["", "", "", ""],
        rows=[
            TableRow(cells=[CellValue(text="?"), CellValue(text="")], row_type=RowType.DATA)
            for _ in range(127)
        ],
        row_count=127,
        source_pages=[4],
    )
    out, summary = apply_ltqg([good, bad], profile=_bank_profile())
    assert summary.enabled is True
    assert summary.passed_tables == 1
    assert summary.skipped_tables == 1
    assert summary.expected_data_rows == 3
    assert out[0].quality_passed is True
    assert out[1].quality_passed is False
    assert sum_passed_data_row_estimates(out) == 3


def test_quarantined_page_table_vetoed():
    lt = LogicalTable(
        headers=["交易日期", "摘要", "借方发生额", "贷方发生额", "余额"],
        rows=[_data_row("2024-01-01", "1.00")],
        row_count=1,
        source_pages=[2],
    )
    quality = assess_logical_table(lt, quarantined_pages={2})
    assert quality.passed is False
    assert quality.skip_reason == "merge_quarantine"
