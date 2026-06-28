# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Table postprocess — entry hook for full table normalization pipeline.

Purpose: Wraps ``table.pipeline.normalize_table`` as the single post-extraction
table cleanup entry used by handlers and postprocessor.

Main components: ``post_process_table``.

Upstream: Raw extracted table grids.

Downstream: ``table.pipeline`` stages, ``table.compose``.
"""

from __future__ import annotations

import logging

from docmirror.structure.tables.pipeline import kv_summary, stage_header, stage_preamble, stage_structure
from docmirror.structure.tables.pipeline.vocab_match import _find_vocab_words_in_string
from docmirror.structure.utils.text_utils import normalize_table

logger = logging.getLogger(__name__)

# Re-exports (backward compat)
_extract_preamble_kv = stage_preamble._extract_preamble_kv
_strip_preamble = stage_preamble._strip_preamble
_fix_header_by_vocabulary = stage_header._fix_header_by_vocabulary
_split_merged_columns = stage_structure._split_merged_columns
_clean_cell = stage_structure._clean_cell
_extract_summary_entities = kv_summary._extract_summary_entities


def post_process_table(
    table_data: list[list[str]],
    confirmed_header: list[str] | None = None,
) -> tuple[list[list[str]] | None, dict[str, str]]:
    """General-purpose table post-processing — orchestrates TNP stages."""
    if not table_data or len(table_data) < 2:
        return table_data, {}

    table_data = normalize_table([list(row) for row in table_data])

    rows, preamble_kv, resolved_header = stage_header.run_header_stage(
        table_data,
        confirmed_header=confirmed_header,
    )
    if not rows:
        return None, preamble_kv
    if resolved_header is None:
        return rows, preamble_kv
    header = rows[0]
    data_rows = list(rows[1:])
    data_rows = stage_structure.filter_junk_rows(header, data_rows, preamble_kv)
    header, data_rows = stage_structure.apply_structure_fixes(header, data_rows)
    result = stage_structure.clean_data_rows(header, data_rows)
    return result, preamble_kv


__all__ = [
    "_clean_cell",
    "_extract_preamble_kv",
    "_extract_summary_entities",
    "_find_vocab_words_in_string",
    "_fix_header_by_vocabulary",
    "_split_merged_columns",
    "_strip_preamble",
    "post_process_table",
]
