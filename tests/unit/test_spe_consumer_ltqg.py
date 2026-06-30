# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SPE consumer LTQG helpers."""

from __future__ import annotations

from docmirror.evidence.spe_consumer import (
    mirror_expected_primary_rows,
    read_ltqg_summary,
    spe_ltqg_warnings,
)
from docmirror.models.entities.parse_result import CellValue, LogicalTable, ParseResult, ParserInfo, RowType, TableRow
from docmirror.tables.compose.ledger_quality import apply_ltqg


def _bank_profile():
    class _Profile:
        profile_id = "borderless_ledger_bank"
        document_type_hint = "bank_statement"

        def is_borderless_ledger(self):
            return True

    return _Profile()


def test_read_ltqg_summary_from_spe():
    spe = {
        "ltqg_enabled": True,
        "ltqg_expected_data_rows": 47,
        "ltqg_passed_tables": 2,
        "ltqg_skipped_tables": 1,
    }
    summary = read_ltqg_summary(spe, None)
    assert summary["enabled"] is True
    assert summary["expected_data_rows"] == 47


def test_mirror_expected_primary_rows_from_logical_tables():
    good = LogicalTable(
        headers=["交易日期", "摘要", "借方发生额", "贷方发生额", "余额"],
        rows=[
            TableRow(
                cells=[CellValue(text="2024-01-01"), CellValue(text="x"), CellValue(text="1.00")],
                row_type=RowType.DATA,
            )
        ],
        row_count=1,
        logical_id="lt_0",
        quality_passed=True,
        data_row_estimate=1,
    )
    bad = LogicalTable(
        headers=["", "", ""],
        rows=[TableRow(cells=[CellValue(text="?")], row_type=RowType.DATA) for _ in range(20)],
        row_count=20,
        logical_id="lt_1",
        quality_passed=False,
        quality_skip_reason="fragment_table",
        data_row_estimate=0,
    )
    pr = ParseResult(logical_tables=[good, bad])
    assert mirror_expected_primary_rows(pr) == 1


def test_apply_ltqg_raw_max_in_spe_warnings():
    good = LogicalTable(
        headers=["交易日期", "摘要", "借方发生额", "贷方发生额", "余额"],
        rows=[
            TableRow(
                cells=[CellValue(text="2024-01-01"), CellValue(text="x"), CellValue(text="1.00")],
                row_type=RowType.DATA,
            )
        ],
        row_count=3,
        source_pages=[1],
    )
    bad = LogicalTable(
        headers=["", "", ""],
        rows=[TableRow(cells=[CellValue(text="?"), CellValue(text="")], row_type=RowType.DATA) for _ in range(127)],
        row_count=127,
        source_pages=[4],
    )
    _, summary = apply_ltqg([good, bad], profile=_bank_profile())
    spe = {
        "ltqg_enabled": True,
        "ltqg_expected_data_rows": summary.expected_data_rows,
        "ltqg_skipped_tables": summary.skipped_tables,
        "ltqg_raw_max_rows": summary.raw_max_rows,
    }
    warnings = spe_ltqg_warnings(spe)
    assert any(w.startswith("ltqg:skipped_tables:") for w in warnings)
    assert any("expected_below_raw_max" in w for w in warnings)


def test_parse_result_meta_ltqg_from_spe():
    from docmirror.evidence.spe_consumer import mirror_api_meta_fields

    pr = ParseResult()
    pr.parser_info = ParserInfo(
        structure={
            "ltqg_enabled": True,
            "ltqg_expected_data_rows": 10,
            "ltqg_passed_tables": 1,
            "ltqg_skipped_tables": 0,
            "physical_table_count": 5,
        }
    )
    mirror = pr.to_mirror_json_vnext()
    assert "meta" not in mirror
    meta = mirror_api_meta_fields(pr)
    assert meta["physical_table_count"] == 5
    assert meta["ltqg"]["expected_data_rows"] == 10
