# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Structure geometry coverage for vNext page projection flow dedup.

Region ``structure`` is the SSOT for which OCR text belongs to S3/S4 content.
``flow.texts`` is the page-level complement: lines not mostly covered by any
declared structure element (cells, bands, nodes). When structure has no geometry,
callers fall back to the region envelope ``bbox``.
"""

from __future__ import annotations

from typing import Any


def iter_structure_bboxes(structure: dict[str, Any] | None) -> list[list[float]]:
    """Collect all axis-aligned bboxes declared in a region structure."""
    if not isinstance(structure, dict):
        return []
    out: list[list[float]] = []

    def add_bbox(raw: Any) -> None:
        if isinstance(raw, (list, tuple)) and len(raw) == 4:
            out.append([float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])])

    for band_key in ("row_bands", "col_bands"):
        for band in structure.get(band_key) or []:
            if isinstance(band, dict):
                add_bbox(band.get("bbox"))

    cells = structure.get("cells") or []
    if cells and isinstance(cells[0], list):
        for row in cells:
            if not isinstance(row, list):
                continue
            for cell in row:
                if isinstance(cell, dict):
                    add_bbox(cell.get("bbox"))
    else:
        for cell in cells:
            if isinstance(cell, dict):
                add_bbox(cell.get("bbox"))

    for node in structure.get("nodes") or []:
        if isinstance(node, dict):
            add_bbox(node.get("bbox"))

    return out


def text_mostly_inside_bbox(
    text_bbox: list[float],
    target_bbox: list[float],
    *,
    y_threshold: float = 0.7,
    x_threshold: float = 0.7,
) -> bool:
    """True when text overlaps target on both y and x axes above thresholds."""
    tx0, ty0, tx1, ty1 = (float(v) for v in text_bbox)
    rx0, ry0, rx1, ry1 = (float(v) for v in target_bbox)
    text_h = max(ty1 - ty0, 1e-6)
    text_w = max(tx1 - tx0, 1e-6)
    iy0, iy1 = max(ty0, ry0), min(ty1, ry1)
    if iy1 <= iy0:
        return False
    if (iy1 - iy0) / text_h < y_threshold:
        return False
    ix0, ix1 = max(tx0, rx0), min(tx1, rx1)
    if ix1 <= ix0:
        return False
    return (ix1 - ix0) / text_w >= x_threshold


def text_covered_by_structure(
    text_bbox: list[float],
    structure: dict[str, Any] | None,
    *,
    region_bbox: list[float] | None = None,
    y_threshold: float = 0.7,
    x_threshold: float = 0.7,
) -> bool:
    """True when text mostly overlaps structure geometry, else optional region envelope."""
    structure_bboxes = iter_structure_bboxes(structure)
    if structure_bboxes:
        return any(
            text_mostly_inside_bbox(
                text_bbox,
                bbox,
                y_threshold=y_threshold,
                x_threshold=x_threshold,
            )
            for bbox in structure_bboxes
        )
    if region_bbox is not None:
        return text_mostly_inside_bbox(
            text_bbox,
            region_bbox,
            y_threshold=y_threshold,
            x_threshold=x_threshold,
        )
    return False
