# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Pipe-delimited bank ledger table builder from Mirror full text.

Thin wrapper over Core SDU ``build_pipe_table_from_text`` for Plugin LTRO.
"""

from __future__ import annotations

from docmirror.core.table.structure_detect.pipe_grid import detect_pipe_header_in_text, split_pipe_row
from docmirror.core.table.structure_detect.pipe_table_builder import (
    build_pipe_table_from_text,
    count_expected_primary_rows,
)

build_tables_from_pipe_text = build_pipe_table_from_text

__all__ = [
    "build_tables_from_pipe_text",
    "count_expected_primary_rows",
    "detect_pipe_header_in_text",
    "split_pipe_row",
]
