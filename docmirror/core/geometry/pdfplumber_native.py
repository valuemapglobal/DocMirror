# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Native pdfplumber table-cell geometry extraction."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.core.geometry.bbox import BBox, area, iou, normalize, union


def native_cell_bboxes_for_table(
    page: Any,
    raw_table: list[list[Any]],
    *,
    table_bbox: Sequence[float] | None = None,
    table_index: int = 0,
) -> list[list[BBox | None]] | None:
    """Return pdfplumber native cell bboxes when a table match is unambiguous."""
    if page is None or not raw_table:
        return None
    try:
        native_tables = list(page.find_tables() or [])
    except Exception:
        return None
    if not native_tables:
        return None

    expected_rows = len(raw_table)
    expected_cols = max((len(row) for row in raw_table if isinstance(row, list)), default=0)
    candidates: list[tuple[float, list[list[BBox | None]]]] = []
    for idx, native in enumerate(native_tables):
        matrix = _native_table_cell_matrix(native)
        if not matrix or len(matrix) != expected_rows:
            continue
        if max((len(row) for row in matrix), default=0) != expected_cols:
            continue
        score = _table_match_score(matrix, table_bbox, fallback_index_score=1.0 if idx == table_index else 0.0)
        candidates.append((score, matrix))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    if candidates[0][0] <= 0:
        return None
    return candidates[0][1]


def _native_table_cell_matrix(native: Any) -> list[list[BBox | None]] | None:
    rows = getattr(native, "rows", None)
    if rows:
        matrix: list[list[BBox | None]] = []
        for row in rows:
            cells = getattr(row, "cells", None)
            if cells is None and isinstance(row, dict):
                cells = row.get("cells")
            if cells is None:
                return None
            matrix.append([_cell_bbox(cell) for cell in cells])
        return matrix

    cells = getattr(native, "cells", None)
    if cells and all(isinstance(cell, (list, tuple)) and len(cell) >= 4 for cell in cells):
        return [[normalize(cell)] for cell in cells]
    return None


def _cell_bbox(cell: Any) -> BBox | None:
    if cell is None:
        return None
    if isinstance(cell, (list, tuple)) and len(cell) >= 4:
        return normalize(cell)
    bbox = getattr(cell, "bbox", None)
    if bbox is not None:
        return normalize(bbox)
    if isinstance(cell, dict):
        if cell.get("bbox") is not None:
            return normalize(cell.get("bbox"))
        keys = ("x0", "top", "x1", "bottom")
        if all(cell.get(key) is not None for key in keys):
            return normalize((cell["x0"], cell["top"], cell["x1"], cell["bottom"]))
    return None


def _table_match_score(
    matrix: list[list[BBox | None]],
    table_bbox: Sequence[float] | None,
    *,
    fallback_index_score: float,
) -> float:
    native_bbox = union(cell for row in matrix for cell in row if cell)
    if table_bbox is None:
        return fallback_index_score
    overlap = iou(native_bbox, table_bbox)
    if overlap > 0:
        return overlap
    if native_bbox and area(native_bbox) > 0:
        return fallback_index_score * 0.5
    return 0.0


__all__ = ["native_cell_bboxes_for_table"]
