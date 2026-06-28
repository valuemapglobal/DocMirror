"""Header-band reconstruction for financial statement grids."""

from __future__ import annotations

from typing import Any


def build_header_bands(
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    cells: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    header_rows = [row for row in rows if row.get("role") == "header"]
    if not header_rows and columns:
        return [_band_from_columns(columns)]

    bands: list[dict[str, Any]] = []
    for level, row in enumerate(header_rows):
        row_index = int(row.get("index", 0) or 0)
        row_cells = [
            cell
            for cell in cells
            if _cell_row(cell) == row_index and str(cell.get("text") or "").strip()
        ]
        if not row_cells:
            continue
        bands.append(
            {
                "level": level,
                "row_range": [row_index, row_index],
                "cells": [_header_cell(cell) for cell in row_cells],
            }
        )
    if not bands and columns:
        return [_band_from_columns(columns)]
    return bands


def _band_from_columns(columns: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "level": 0,
        "row_range": [0, 0],
        "cells": [
            {
                "text": str(col.get("header") or ""),
                "col_range": [int(col.get("index", index) or index), int(col.get("index", index) or index)],
                "row_span": 1,
                "col_span": 1,
                "bbox": col.get("bbox"),
                "evidence_ids": [],
                "is_merged": False,
            }
            for index, col in enumerate(columns)
            if str(col.get("header") or "").strip()
        ],
    }


def _header_cell(cell: dict[str, Any]) -> dict[str, Any]:
    col = _cell_col(cell)
    row_span = int(cell.get("row_span", 1) or 1)
    col_span = int(cell.get("col_span", 1) or 1)
    return {
        "text": str(cell.get("text") or ""),
        "col_range": [col, col + max(col_span - 1, 0)],
        "row_span": row_span,
        "col_span": col_span,
        "bbox": cell.get("bbox"),
        "evidence_ids": list(cell.get("evidence_ids") or []),
        "is_merged": row_span > 1 or col_span > 1,
    }


def _cell_row(cell: dict[str, Any]) -> int:
    return int(cell.get("row_index", cell.get("row", 0)) or 0)


def _cell_col(cell: dict[str, Any]) -> int:
    return int(cell.get("col_index", cell.get("column_index", cell.get("col", 0))) or 0)
