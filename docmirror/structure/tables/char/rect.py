# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Rect columns — column extraction from vector rectangles.

Purpose: Uses PDF rectangle paths as cell boundaries when tables are drawn
with explicit rect annotations.

Main components: ``_extract_by_rect_columns``.

Upstream: Fitz vector rect list in zone.

Downstream: ``extract.engine`` vector-table path.
"""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def _extract_by_rect_columns(page_plum) -> list[list[str]] | None:
    """Rectangle column boundary method."""
    rects = page_plum.rects
    if not rects or len(rects) < 3:
        return None

    y_groups = defaultdict(list)
    for r in rects:
        y_key = round(r["top"] / 3) * 3
        y_groups[y_key].append(r)

    best_group = max(y_groups.values(), key=len)
    if len(best_group) < 3:
        return None

    raw_x = sorted(set(round(v, 1) for r in best_group for v in [r["x0"], r["x1"]]))
    x_positions = [0.0]
    for x in raw_x:
        if x - x_positions[-1] > 2:
            x_positions.append(x)
    x_positions.append(page_plum.width)

    if len(x_positions) < 4:
        return None

    header_top = min(r["top"] for r in best_group) - 2
    header_bottom = max(r["bottom"] for r in best_group) + 1

    try:
        cropped = page_plum.crop(
            (
                0,
                header_top,
                page_plum.width,
                page_plum.height,
            )
        )
        chars = cropped.chars
        if not chars:
            return None

        col_count = len(x_positions) - 1
        intervals = [(x_positions[i], x_positions[i + 1]) for i in range(col_count)]

        def _chars_to_row(row_chars):
            cells = [""] * col_count
            for c in sorted(row_chars, key=lambda c: c["x0"]):
                for ci, (x0, x1) in enumerate(intervals):
                    if x0 - 2 <= c["x0"] < x1 + 2:
                        cells[ci] += c["text"]
                        break
            return [cell.strip() for cell in cells]

        header_chars = [c for c in chars if c["top"] < header_bottom]
        data_chars = [c for c in chars if c["top"] >= header_bottom]

        table = []
        if header_chars:
            table.append(_chars_to_row(header_chars))

        row_groups = defaultdict(list)
        for c in data_chars:
            y_key = round(c["top"] / 3) * 3
            row_groups[y_key].append(c)

        for y_key in sorted(row_groups.keys()):
            row = _chars_to_row(row_groups[y_key])
            if any(cell for cell in row):
                table.append(row)

        while table and all(not row[0] for row in table):
            table = [row[1:] for row in table]
        while table and all(not row[-1] for row in table):
            table = [row[:-1] for row in table]

        if len(table) >= 3:
            return table

    except Exception as e:
        logger.debug(f"rect columns failed: {e}")

    return None
