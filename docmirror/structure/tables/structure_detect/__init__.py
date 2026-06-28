# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Structure Detect Utilities (SDU) — document-agnostic grid/pipe detection SSOT."""

from docmirror.structure.tables.structure_detect.header_zone import extract_header_zone
from docmirror.structure.tables.structure_detect.pipe_grid import (
    PipeGridSignal,
    count_primary_pipe_rows,
    detect_pipe_grid_in_text,
    detect_pipe_grid_page,
    detect_pipe_header_in_text,
    page_has_no_drawing_primitives,
    split_pipe_row,
)
from docmirror.structure.tables.structure_detect.pipe_page_extract import extract_pipe_delimited_table
from docmirror.structure.tables.structure_detect.pipe_table_builder import (
    build_pipe_table_from_text,
    count_expected_primary_rows,
)

__all__ = [
    "PipeGridSignal",
    "build_pipe_table_from_text",
    "count_expected_primary_rows",
    "count_primary_pipe_rows",
    "detect_pipe_grid_in_text",
    "detect_pipe_grid_page",
    "detect_pipe_header_in_text",
    "extract_pipe_delimited_table",
    "extract_header_zone",
    "page_has_no_drawing_primitives",
    "split_pipe_row",
]
