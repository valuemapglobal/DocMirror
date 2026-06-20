# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Header anchors — column boundaries from header cell positions.

Purpose: Uses vocabulary-matched header cells as anchor points for column
divider placement.

Main components: ``detect_columns_by_header_anchors``.

Upstream: Header row chars, ``utils.vocabulary``.

Downstream: ``extract.char_strategy``, ``table.column_anchor``.
"""

from __future__ import annotations

import logging

from docmirror.core.extract.utils import (
    _assign_chars_to_columns,
    _chars_to_text,
    _cluster_x_positions,
    _group_chars_into_rows,
)
from docmirror.core.utils.vocabulary import _is_header_cell, _score_header_by_vocabulary
from docmirror.core.utils.watermark import is_watermark_char

logger = logging.getLogger(__name__)


def detect_columns_by_header_anchors(page_plum) -> list[list[str]] | None:
    """Header-anchor column detection method."""
    chars = page_plum.chars
    if not chars or len(chars) < 10:
        return None

    chars = [c for c in chars if not is_watermark_char(c)]
    if not chars:
        return None

    rows_by_y = _group_chars_into_rows(chars)
    if len(rows_by_y) < 2:
        return None

    header_row_idx = -1
    best_vocab_score = 0
    # Scan the first 15 rows: prefer vocab matches, handle KV metadata rows before the header
    for i, (y_mid, row_chars) in enumerate(rows_by_y[:15]):
        row_text = _chars_to_text(row_chars)
        cells = [t.strip() for t in row_text.split("  ") if t.strip()]
        if len(cells) < 2:
            continue
        vs = _score_header_by_vocabulary(cells)
        if vs > best_vocab_score:
            best_vocab_score = vs
            header_row_idx = i
        elif vs == 0 and header_row_idx == -1:
            # Fallback: structural heuristic (when no vocab matches)
            if all(_is_header_cell(c) for c in cells[:4]):
                header_row_idx = i

    if header_row_idx == -1:
        return None

    header_chars = rows_by_y[header_row_idx][1]
    col_bounds = _cluster_x_positions([c["x0"] for c in header_chars])

    if len(col_bounds) < 2:
        return None

    result: list[list[str]] = []
    for y_mid, row_chars in rows_by_y[header_row_idx:]:
        row = _assign_chars_to_columns(row_chars, col_bounds)
        result.append(row)

    return result if len(result) >= 2 else None
