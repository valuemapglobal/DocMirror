# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for TQG extract oracles."""

from __future__ import annotations

from docmirror.eval.tqg.extract_oracles import (
    run_column_fidelity_oracle,
    run_quarantine_metadata_oracle,
)
from docmirror.models.entities.parse_result import (
    CellValue,
    LogicalTable,
    PageContent,
    ParseResult,
    TableBlock,
    TableRow,
)


def _wechat_like_result() -> ParseResult:
    headers = ["交易单号", "交易时间", "交易类型", "收/支", "金额", "交易方式", "交易对方", "商户单号"]
    rows = [
        TableRow(
            cells=[
                CellValue(text="202601010001"),
                CellValue(text="2026-01-01 12:00:00"),
                *([CellValue(text="x")] * 6),
            ]
        )
        for _ in range(10)
    ]
    table = TableBlock(table_id="t1", headers=headers, rows=rows)
    lt = LogicalTable(
        logical_id="lt1",
        table_id="t1",
        headers=headers,
        rows=rows,
        row_count=len(rows),
        source_pages=[1],
    )
    return ParseResult(pages=[PageContent(page_number=1, tables=[table])], logical_tables=[lt])


def test_column_fidelity_oracle_passes():
    report = run_column_fidelity_oracle(
        _wechat_like_result(),
        {"min_columns": 8, "column_ratio_min": 0.99},
    )
    assert report.passed, report.failures


def test_quarantine_metadata_oracle_passes():
    class _Base:
        metadata = {
            "quarantined_tables": [
                {
                    "page": 219,
                    "reason": "col_count_mismatch",
                    "action": "standalone_physical_table",
                }
            ]
        }

    report = run_quarantine_metadata_oracle(
        {"base": _Base()},
        {
            "page": 219,
            "reason": "col_count_mismatch",
            "action": "standalone_physical_table",
            "require_nonempty": True,
        },
    )
    assert report.passed, report.failures


def test_text_snapshot_oracle_passes():
    from docmirror.eval.tqg.extract_oracles import run_text_snapshot_oracle

    class _Block:
        def __init__(self, content: str):
            self.block_type = "text"
            self.raw_content = content

    class _Page:
        def __init__(self):
            self.blocks = [_Block("ZhangSan"), _Block("110101199001011234")]

    class _Base:
        pages = [_Page()]

    report = run_text_snapshot_oracle(
        {"base": _Base()},
        {"min_text_lines": 2, "contains": ["ZhangSan"]},
    )
    assert report.passed, report.failures
