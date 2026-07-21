# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lossless native-PDF table candidates for the canonical extraction path.

The detector deliberately produces an engine-neutral dictionary contract.  It
belongs to the physical evidence layer: no document-domain labels or business
field names are inferred here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

BBox = list[float]


def extract_pymupdf_table_candidates(
    page: Any,
    *,
    page_number: int,
    page_id: str,
    normalize_bbox: Callable[[list[float]], list[float]],
    text_atoms: Sequence[Any],
    vector_atoms: Sequence[Any],
) -> list[dict[str, Any]]:
    """Return physical table candidates with exact native cell geometry.

    Candidate text ownership is resolved after all tables are known.  A token
    inside overlapping candidates is owned by the smallest enclosing table,
    which prevents a page-sized false positive from stealing nested tables.
    """
    try:
        finder = page.find_tables()
        native_tables = list(getattr(finder, "tables", None) or [])
    except Exception:
        return []

    candidates: list[dict[str, Any]] = []
    for table_index, native in enumerate(native_tables):
        try:
            extracted = native.extract() or []
        except Exception:
            continue
        raw_rows = [[str(value or "").strip() for value in row] for row in extracted if isinstance(row, list | tuple)]
        if not raw_rows or not any(any(cell for cell in row) for row in raw_rows):
            continue

        source_bbox = _bbox(getattr(native, "bbox", None))
        if source_bbox is None:
            continue
        bbox = normalize_bbox(source_bbox)
        source_cells = _native_cell_matrix(native, raw_rows)
        cell_bboxes = [[normalize_bbox(cell) if cell is not None else None for cell in row] for row in source_cells]
        row_bands, col_bands = _grid_bands(cell_bboxes, bbox)
        cell_spans = _cell_spans(cell_bboxes, row_bands, col_bands)
        statuses = [["exact" if cell is not None else "derived" for cell in row] for row in cell_bboxes]
        loss_reasons = [[None if cell is not None else "covered_by_merged_cell" for cell in row] for row in cell_bboxes]
        width = max((len(row) for row in raw_rows), default=0)
        preserve_headers = _looks_like_header(raw_rows, width)
        candidate_id = f"table-candidate:p{page_number}:t{table_index}"
        candidates.append(
            {
                "candidate_id": candidate_id,
                "page_id": page_id,
                "page_number": page_number,
                "table_index": table_index,
                "engine": "pymupdf_native",
                "confidence": 1.0,
                "bbox": bbox,
                "source_bbox": source_bbox,
                "rows": raw_rows,
                "preserve_headers": preserve_headers,
                "geometry": {
                    "coordinate_system": "pdf_points_top_left",
                    "geometry_source": "pymupdf_native_cells",
                    "geometry_confidence": 1.0,
                    "cell_bboxes": cell_bboxes,
                    "cell_geometry_status": statuses,
                    "cell_geometry_loss_reason": loss_reasons,
                    "cell_evidence_ids": [[[] for _ in row] for row in raw_rows],
                    "cell_token_ids": [[[] for _ in row] for row in raw_rows],
                    "cell_confidences": [[1.0 for _ in row] for row in raw_rows],
                    "cell_spans": cell_spans,
                    "row_bands": row_bands,
                    "col_bands": col_bands,
                },
                "evidence_ids": [],
                "vector_evidence_ids": [],
            }
        )

    if not candidates:
        return []

    _assign_text_ownership(candidates, text_atoms)
    _attach_vector_evidence(candidates, vector_atoms)
    return candidates


def _looks_like_header(rows: list[list[str]], width: int) -> bool:
    """Conservative physical-header heuristic.

    Two-column PDF tables are commonly label/value forms.  Treating their
    first row as a header loses a business row during logical composition, so
    they remain headerless unless the native grid has at least three columns.
    """
    if width < 3 or len(rows) < 2:
        return False
    first = rows[0]
    return sum(bool(str(value).strip()) for value in first) >= max(2, width // 2)


def _native_cell_matrix(native: Any, raw_rows: list[list[str]]) -> list[list[BBox | None]]:
    native_rows = list(getattr(native, "rows", None) or [])
    matrix: list[list[BBox | None]] = []
    for row_index, raw_row in enumerate(raw_rows):
        cells = []
        if row_index < len(native_rows):
            cells = list(getattr(native_rows[row_index], "cells", None) or [])
        matrix.append([_bbox(cells[col]) if col < len(cells) else None for col in range(len(raw_row))])
    return matrix


def _grid_bands(cell_bboxes: list[list[BBox | None]], table_bbox: BBox) -> tuple[list[BBox], list[BBox]]:
    cells = [cell for row in cell_bboxes for cell in row if cell is not None]
    ys = _clustered_coordinates([table_bbox[1], table_bbox[3], *(v for cell in cells for v in (cell[1], cell[3]))])
    xs = _clustered_coordinates([table_bbox[0], table_bbox[2], *(v for cell in cells for v in (cell[0], cell[2]))])
    row_bands = [[table_bbox[0], ys[i], table_bbox[2], ys[i + 1]] for i in range(max(0, len(ys) - 1))]
    col_bands = [[xs[i], table_bbox[1], xs[i + 1], table_bbox[3]] for i in range(max(0, len(xs) - 1))]
    return row_bands, col_bands


def _clustered_coordinates(values: Sequence[float], tolerance: float = 0.75) -> list[float]:
    ordered = sorted(float(value) for value in values)
    groups: list[list[float]] = []
    for value in ordered:
        if not groups or abs(value - groups[-1][-1]) > tolerance:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [round(sum(group) / len(group), 4) for group in groups]


def _cell_spans(
    matrix: list[list[BBox | None]],
    row_bands: list[BBox],
    col_bands: list[BBox],
) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for row_index, row in enumerate(matrix):
        for col_index, cell in enumerate(row):
            if cell is None:
                continue
            covered_rows = [band for band in row_bands if _overlap_1d(cell[1], cell[3], band[1], band[3])]
            covered_cols = [band for band in col_bands if _overlap_1d(cell[0], cell[2], band[0], band[2])]
            row_span = max(1, len(covered_rows))
            col_span = max(1, len(covered_cols))
            if row_span > 1 or col_span > 1:
                spans.append(
                    {
                        "row": row_index,
                        "col": col_index,
                        "row_span": row_span,
                        "col_span": col_span,
                        "bbox": cell,
                    }
                )
    return spans


def _assign_text_ownership(candidates: list[dict[str, Any]], text_atoms: Sequence[Any]) -> None:
    for atom in text_atoms:
        atom_bbox = _bbox(getattr(atom, "bbox", None))
        if atom_bbox is None:
            continue
        center = ((atom_bbox[0] + atom_bbox[2]) / 2.0, (atom_bbox[1] + atom_bbox[3]) / 2.0)
        owners = [candidate for candidate in candidates if _contains(candidate["bbox"], center)]
        if not owners:
            continue
        owner = min(owners, key=lambda candidate: _area(candidate["bbox"]))
        token_id = str(getattr(atom, "id", "") or "")
        if not token_id:
            continue
        owner["evidence_ids"].append(token_id)
        metadata = dict(getattr(atom, "metadata", None) or {})
        metadata.update(
            {
                "block_type": "table",
                "table_candidate_id": owner["candidate_id"],
                "table_engine": owner["engine"],
            }
        )
        atom.metadata = metadata
        cell = _owning_cell(owner["geometry"]["cell_bboxes"], center)
        if cell is not None:
            row_index, col_index = cell
            owner["geometry"]["cell_token_ids"][row_index][col_index].append(token_id)
            owner["geometry"]["cell_evidence_ids"][row_index][col_index].append(token_id)


def _attach_vector_evidence(candidates: list[dict[str, Any]], vector_atoms: Sequence[Any]) -> None:
    for candidate in candidates:
        table_bbox = candidate["bbox"]
        vector_ids = []
        for atom in vector_atoms:
            atom_bbox = _bbox(getattr(atom, "bbox", None))
            atom_id = str(getattr(atom, "id", "") or "")
            if atom_bbox is not None and atom_id and _intersects(table_bbox, atom_bbox):
                vector_ids.append(atom_id)
        candidate["vector_evidence_ids"] = vector_ids
        candidate["evidence_ids"] = list(dict.fromkeys([*candidate["evidence_ids"], *vector_ids]))


def _owning_cell(matrix: list[list[BBox | None]], center: tuple[float, float]) -> tuple[int, int] | None:
    matches: list[tuple[float, int, int]] = []
    for row_index, row in enumerate(matrix):
        for col_index, cell in enumerate(row):
            if cell is not None and _contains(cell, center):
                matches.append((_area(cell), row_index, col_index))
    if not matches:
        return None
    _, row_index, col_index = min(matches)
    return row_index, col_index


def _bbox(value: Any) -> BBox | None:
    if value is None:
        return None
    try:
        values = [float(v) for v in value]
    except (TypeError, ValueError):
        return None
    if len(values) < 4:
        return None
    x0, y0, x1, y1 = values[:4]
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def _contains(bbox: BBox, point: tuple[float, float], tolerance: float = 0.5) -> bool:
    return (
        bbox[0] - tolerance <= point[0] <= bbox[2] + tolerance
        and bbox[1] - tolerance <= point[1] <= bbox[3] + tolerance
    )


def _intersects(left: BBox, right: BBox) -> bool:
    return min(left[2], right[2]) >= max(left[0], right[0]) and min(left[3], right[3]) >= max(left[1], right[1])


def _area(bbox: BBox) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _overlap_1d(start: float, end: float, band_start: float, band_end: float) -> bool:
    overlap = min(end, band_end) - max(start, band_start)
    band_size = max(0.001, band_end - band_start)
    return overlap / band_size >= 0.8


__all__ = ["extract_pymupdf_table_candidates"]
