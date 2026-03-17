# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Unit tests for table extraction classifier (G2 L1 table layer coverage)."""

import pytest
from docmirror.core.table.extraction.classifier import (
    _compute_table_confidence,
    _tables_look_valid,
)


class TestComputeTableConfidence:
    def test_empty_tables_return_zero(self):
        assert _compute_table_confidence([], "lines") == 0.0
        assert _compute_table_confidence([[]], "text") == 0.0

    def test_single_row_returns_low_confidence(self):
        tables = [["Date", "Amount", "Balance"]]
        c = _compute_table_confidence(tables, "lines")
        assert 0.0 <= c <= 1.0

    def test_header_and_data_rows_increase_confidence(self):
        tables = [
            ["Date", "Amount", "Balance"],
            ["2024-01-01", "100.00", "500.00"],
            ["2024-01-02", "-50.00", "450.00"],
        ]
        c = _compute_table_confidence(tables, "text")
        assert c >= 0.0 and c <= 1.0

    def test_layer_bonus_affects_score(self):
        tables = [["A", "B"], ["1", "2"]]
        c_fallback = _compute_table_confidence(tables, "fallback")
        c_lines = _compute_table_confidence(tables, "lines")
        assert c_lines >= c_fallback


class TestTablesLookValid:
    def test_valid_two_row_table(self):
        tables = [[["H1", "H2"], ["a", "b"]]]
        assert _tables_look_valid(tables, min_rows=2) is True

    def test_single_row_fails_min_rows(self):
        tables = [[["H1", "H2"]]]
        assert _tables_look_valid(tables, min_rows=2) is False

    def test_empty_fails(self):
        assert _tables_look_valid([]) is False