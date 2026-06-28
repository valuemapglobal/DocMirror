# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""RowKind taxonomy for pipe/grid ledger rows (BS-003)."""

from __future__ import annotations

from docmirror.structure.tables.row_kind import (
    RowKind,
    classify_pipe_cells,
    classify_pipe_line,
    filter_pipe_table_rows,
)
from tests.unit.test_pipe_text_table_builder import BOC_HEADER, BOC_ROW1


def test_classify_boc_header_line():
    assert classify_pipe_line(BOC_HEADER) == RowKind.HEADER


def test_classify_boc_data_line():
    assert classify_pipe_line(BOC_ROW1) == RowKind.DATA


def test_filter_repeated_pipe_headers():
    header_cells = ["序号", "记账日", "借方发生额", "贷方发生额", "余额"]
    table = [
        header_cells,
        ["1", "20240101", "100.00", "", "1000.00"],
        header_cells,
        ["2", "20240102", "50.00", "", "950.00"],
    ]
    filtered = filter_pipe_table_rows(table)
    assert len(filtered) == 3
    assert filtered[0] == header_cells
    assert classify_pipe_cells(filtered[1]) == RowKind.DATA


def test_preamble_cells_classified():
    assert classify_pipe_cells(["No.", "Bk.D.", "Amount"]) == RowKind.PREAMBLE
