# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bank Ledger Orchestrator (BLO) unit tests."""

from __future__ import annotations

from docmirror.models.entities.parse_result import CellValue, LogicalTable, ParseResult, TableRow
from docmirror.plugins.bank_statement.blo import BankLedgerOrchestrator, logical_table_to_matrices
from docmirror.plugins.bank_statement.canonical import dedupe_transaction_rows
from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry


def test_logical_table_to_matrices_includes_headers():
    lt = LogicalTable(
        headers=["交易日期", "摘要", "余额"],
        rows=[
            TableRow(cells=[CellValue(text="2024-01-01"), CellValue(text="x"), CellValue(text="1")]),
        ],
        row_count=1,
        logical_id="lt_0",
    )
    matrices = logical_table_to_matrices(lt)
    assert matrices[0][0] == ["交易日期", "摘要", "余额"]
    assert len(matrices[0]) == 2


def test_dedupe_transaction_rows():
    records = [
        {"row_index": 1, "normalized": {"date": "2024-01-01", "amount": 1.0, "balance": 2.0, "counter_party": "a"}},
        {"row_index": 2, "normalized": {"date": "2024-01-01", "amount": 1.0, "balance": 2.0, "counter_party": "a"}},
    ]
    out = dedupe_transaction_rows(records)
    assert len(out) == 1
    assert out[0]["row_index"] == 1


def test_blo_skips_failed_ltqg_table():
    good = LogicalTable(
        headers=["交易日期", "摘要", "收入", "支出", "余额"],
        rows=[
            TableRow(cells=[CellValue(text="2024-01-01"), CellValue(text="x"), CellValue(text="0"), CellValue(text="1"), CellValue(text="9")]),
        ],
        row_count=1,
        logical_id="lt_good",
        quality_passed=True,
    )
    bad = LogicalTable(
        headers=["", "", ""],
        rows=[TableRow(cells=[CellValue(text="?"), CellValue(text="?"), CellValue(text="?")])],
        row_count=20,
        logical_id="lt_bad",
        quality_passed=False,
        quality_skip_reason="fragment_table",
    )
    ctx = StyleContext(
        tables=[],
        full_text="中国工商银行",
        institution=None,
        page_count=2,
        parse_result=ParseResult(logical_tables=[good, bad]),
    )
    detection = BankStyleDetector().detect(ctx)
    plugin = BankStatementCommunityPlugin()
    records, _, meta = BankLedgerOrchestrator(BankStyleParserRegistry()).run(detection, ctx, plugin)
    assert meta.tables_skipped == 1
    assert meta.tables_parsed == 1
    assert len(records) >= 1
