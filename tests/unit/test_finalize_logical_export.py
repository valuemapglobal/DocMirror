# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LTQG finalize export path and raw_max with physical quarantine."""

from __future__ import annotations

from docmirror.models.entities.parse_result import CellValue, LogicalTable, ParseResult, RowType, TableRow
from docmirror.quality.mirror_ltqg import attach_mirror_ltqg
from docmirror.evidence.spe_consumer import mirror_api_meta_fields
from docmirror.tables.compose.ledger_quality import (
    apply_ltqg,
    finalize_logical_tables_for_export,
)


def _bank_profile():
    class _Profile:
        profile_id = "borderless_ledger_bank"
        document_type_hint = "bank_statement"

        def is_borderless_ledger(self):
            return True

    return _Profile()


def test_raw_max_includes_quarantined_physical_rows():
    good = LogicalTable(
        headers=["交易日期", "摘要", "余额"],
        rows=[TableRow(cells=[CellValue(text="2024-01-01")], row_type=RowType.DATA)],
        row_count=47,
        source_pages=[1, 2, 3],
    )
    _, summary = apply_ltqg(
        [good],
        profile=_bank_profile(),
        quarantined_tables=[{"page": 4, "row_count": 120, "reason": "col_count_mismatch"}],
    )
    assert summary.raw_max_rows == 120


def test_finalize_export_partitions_failed_tables():
    good = LogicalTable(
        headers=["交易日期", "摘要", "借方发生额", "贷方发生额", "余额"],
        rows=[TableRow(cells=[CellValue(text="2024-01-01")], row_type=RowType.DATA)],
        row_count=1,
        logical_id="lt_0",
    )
    bad = LogicalTable(
        headers=["", "", ""],
        rows=[TableRow(cells=[CellValue(text="?")], row_type=RowType.DATA) for _ in range(20)],
        row_count=20,
        logical_id="lt_1",
        source_pages=[4],
    )
    export, skipped, summary = finalize_logical_tables_for_export(
        [good, bad],
        profile=_bank_profile(),
    )
    assert len(export) == 1
    assert len(skipped) == 1
    assert summary.export_logical_tables == 1
    assert summary.expected_data_rows == 1


def test_attach_mirror_ltqg_quarantine_counts():
    pr = ParseResult(
        logical_tables=[
            LogicalTable(
                headers=["交易日期", "摘要", "余额"],
                rows=[TableRow(cells=[CellValue(text="2024-01-01")], row_type=RowType.DATA)],
                row_count=47,
                quality_passed=True,
                data_row_estimate=47,
            )
        ],
    )
    meta = {
        "ltqg": {
            "enabled": True,
            "expected_data_rows": 47,
            "passed_tables": 1,
            "skipped_tables": 0,
            "export_logical_tables": 1,
        },
        "quarantined_tables": [{"page": 4, "row_count": 30}, {"page": 5, "row_count": 25}],
    }
    attach_mirror_ltqg(pr, meta)
    spe = pr.parser_info.structure or {}
    assert spe.get("quarantined_physical_count") == 2
    assert pr.entities.domain_specific.get("mirror_quarantined_physical_count") == 2

    api = pr.to_mirror_json_vnext()
    assert "meta" not in api
    assert api["source"]["provenance"]["parser_info"]["structure"]["quarantined_physical_count"] == 2
    assert mirror_api_meta_fields(pr).get("quarantined_physical_count") == 2
