# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Borderless ledger table post-processing — precision-first, no row loss."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from docmirror.core.utils.vocabulary import (
    _is_header_row,
    _is_junk_row,
    _score_header_by_vocabulary,
)

if TYPE_CHECKING:
    from docmirror.models.entities.extraction_profile import ExtractionProfile

logger = logging.getLogger(__name__)


def _headers_match_expected(row: list[str], expected: list[str]) -> bool:
    if not expected or not row:
        return False
    hits = 0
    cells = [str(c or "").strip() for c in row]
    for exp in expected:
        if any(exp in c or c in exp for c in cells if c):
            hits += 1
    return hits >= max(3, len(expected) // 2)


def _find_header_row_index(table: list[list[str]], expected_headers: list[str]) -> int:
    """Locate the real header row; return -1 for continuation pages (no header)."""
    scan = min(8, len(table))
    for i in range(scan):
        row = table[i]
        if expected_headers and _headers_match_expected(row, expected_headers):
            return i
        if _is_header_row(row) and _score_header_by_vocabulary(row) >= 3:
            return i
    return -1


def _min_data_columns(profile: ExtractionProfile | None) -> int:
    expected = len(profile.expected_header_columns) if profile else 8
    return max(6, expected - 1)


def _is_valid_ledger_data_row(row: list[str], min_cols: int) -> bool:
    cells = [str(c or "").strip() for c in row]
    if len(cells) < 2:
        return False
    return sum(1 for c in cells if c) >= min_cols


def post_process_ledger_table(
    table_data: list[list[str]],
    profile: ExtractionProfile | None = None,
) -> tuple[list[list[str]] | None, dict[str, str]]:
    """Post-process borderless ledger tables without misclassifying data rows as headers.

    Rules:
      - Page with header: strip preamble rows before header; keep header + all data rows.
      - Continuation page (no header in first rows): keep **all** data rows — zero drops.
      - Junk filter: only remove rows that are clearly non-transaction noise.
    """
    if not table_data:
        return table_data, {}

    table_data = [list(row) for row in table_data]
    expected = list(profile.expected_header_columns) if profile else []
    min_cols = _min_data_columns(profile)

    header_idx = _find_header_row_index(table_data, expected)

    if header_idx >= 0:
        preamble_rows = table_data[:header_idx]
        header = table_data[header_idx]
        data_rows = table_data[header_idx + 1 :]
        preamble_kv: dict[str, str] = {}
        if preamble_rows:
            try:
                from docmirror.core.table.postprocess import _extract_preamble_kv

                preamble_kv = _extract_preamble_kv(preamble_rows)
            except Exception:
                preamble_kv = {}
        clean = [
            r
            for r in data_rows
            if _is_valid_ledger_data_row(r, min_cols) and not _is_junk_row(r)
        ]
        return [header] + clean, preamble_kv

    # Continuation page — every row is data; do NOT treat row 0 as pseudo-header
    clean = [
        r
        for r in table_data
        if _is_valid_ledger_data_row(r, min_cols) and not _is_junk_row(r)
    ]
    return clean if clean else table_data, {}
