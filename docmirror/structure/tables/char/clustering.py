# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Char clustering — x-position clustering for column boundaries.

Purpose: Detects column boundaries by clustering char x-centroids when
headers are ambiguous.

Main components: ``detect_columns_by_clustering``.

Upstream: Zone char dicts from ``extract.utils`` grouping.

Downstream: ``extract.char_strategy``, ``extract.engine``.
"""

from __future__ import annotations

import logging

from docmirror.structure.tables.utils import (
    _assign_chars_to_columns,
    _cluster_x_positions,
    _group_chars_into_rows,
)
from docmirror.structure.utils.watermark import is_watermark_char

logger = logging.getLogger(__name__)


def detect_columns_by_clustering(page_plum) -> list[list[str]] | None:
    """x-coordinate clustering method."""
    chars = page_plum.chars
    if not chars or len(chars) < 10:
        return None

    chars = [c for c in chars if not is_watermark_char(c)]
    if not chars:
        return None

    all_x0 = [c["x0"] for c in chars]
    col_bounds = _cluster_x_positions(all_x0, gap_multiplier=2.5)

    if len(col_bounds) < 2:
        return None

    rows_by_y = _group_chars_into_rows(chars)
    result: list[list[str]] = []
    for y_mid, row_chars in rows_by_y:
        row = _assign_chars_to_columns(row_chars, col_bounds)
        result.append(row)

    return result if len(result) >= 2 else None
