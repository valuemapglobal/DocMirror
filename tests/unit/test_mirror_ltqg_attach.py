# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""attach_mirror_ltqg syncs domain_specific mirror fields."""

from __future__ import annotations

from docmirror.core.analyze.mirror_ltqg import attach_mirror_ltqg
from docmirror.models.entities.parse_result import CellValue, LogicalTable, ParserInfo, ParseResult, RowType, TableRow


def test_attach_mirror_ltqg_writes_domain_specific():
    lt = LogicalTable(
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
    pr = ParseResult(
        logical_tables=[lt],
        parser_info=ParserInfo(
            structure={
                "ltqg_enabled": True,
                "ltqg_expected_data_rows": 1,
                "ltqg_passed_tables": 1,
                "ltqg_skipped_tables": 0,
            }
        ),
    )
    attach_mirror_ltqg(pr, {"ltqg": {"enabled": True, "expected_data_rows": 1, "passed_tables": 1, "skipped_tables": 0}})
    ds = pr.entities.domain_specific
    assert ds.get("mirror_ltqg_enabled") is True
    assert ds.get("mirror_expected_data_rows") == 1


def test_exported_data_row_estimate_zero_when_failed():
    from docmirror.core.table.compose.ledger_quality import exported_data_row_estimate

    lt = LogicalTable(row_count=127, quality_passed=False, data_row_estimate=0)
    assert exported_data_row_estimate(lt) == 0
