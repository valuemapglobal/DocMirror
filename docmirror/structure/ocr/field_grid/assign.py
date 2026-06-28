# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exclusive token-to-column assignment for field grids."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from docmirror.structure.ocr.field_grid.geometry import bbox_overlap_ratio
from docmirror.structure.ocr.field_grid.tokens import _source_priority, dedupe_visual_tokens
from docmirror.structure.ocr.micro_grid.models import BBox, OCRToken


def equal_col_bands(
    header_bbox: BBox,
    *,
    count: int,
    start_index: int = 1,
    role: str = "month",
) -> list[dict[str, Any]]:
    x0, y0, x1, y1 = header_bbox
    step = max(x1 - x0, 1.0) / max(count, 1)
    return [
        {
            "index": start_index + idx,
            "header": str(start_index + idx),
            "bbox": [x0 + step * idx, y0, x0 + step * (idx + 1), y1],
            "role": role,
            "geometry_status": "estimated",
        }
        for idx in range(count)
    ]


def cell_bbox(row_band: dict[str, Any], col_band: dict[str, Any]) -> BBox:
    rb = row_band["bbox"]
    cb = col_band["bbox"]
    return (float(cb[0]), float(rb[1]), float(cb[2]), float(rb[3]))


def assign_tokens(
    tokens: Iterable[OCRToken],
    row_band: dict[str, Any],
    col_band: dict[str, Any],
    *,
    min_token_overlap: float = 0.45,
) -> list[OCRToken]:
    x0, y0, x1, y1 = cell_bbox(row_band, col_band)
    cell = (x0, y0, x1, y1)
    assigned = []
    for token in tokens:
        overlap = bbox_overlap_ratio(token.bbox, cell)
        cx, cy = token.center
        center_inside = x0 <= cx <= x1 and y0 <= cy <= y1
        if overlap >= min_token_overlap or (center_inside and overlap > 0.0):
            assigned.append(token)
    return dedupe_visual_tokens(assigned)


def assign_tokens_to_col_bands(
    tokens: Iterable[OCRToken],
    row_band: dict[str, Any],
    col_bands: Iterable[dict[str, Any]],
    *,
    min_token_overlap: float = 0.20,
) -> dict[int, list[OCRToken]]:
    from docmirror.structure.ocr.grid_materialize import assign_tokens_to_col_bands_exclusive

    return assign_tokens_to_col_bands_exclusive(
        tokens,
        row_band,
        col_bands,
        min_token_overlap=min_token_overlap,
    )


def assignment_confidence(tokens: Iterable[OCRToken], row_band: dict[str, Any], col_band: dict[str, Any]) -> float:
    token_list = list(tokens)
    if not token_list:
        return 0.0
    cell = cell_bbox(row_band, col_band)
    overlaps = [bbox_overlap_ratio(token.bbox, cell) for token in token_list]
    mean_overlap = sum(overlaps) / len(overlaps)
    mean_ocr_conf = sum(token.confidence for token in token_list) / len(token_list)
    return round(max(0.0, min(1.0, (mean_overlap * 0.7) + (mean_ocr_conf * 0.3))), 4)


def assignment_method(tokens: Iterable[OCRToken]) -> str:
    token_list = list(tokens)
    if not token_list:
        return "empty"
    priorities = {_source_priority(token) for token in token_list}
    if priorities and min(priorities) >= 100:
        return "overlap:native_token"
    if priorities and min(priorities) >= 80:
        return "overlap:ocr_char_split"
    if any("line_split" in token.source.lower() for token in token_list):
        return "overlap:line_fallback"
    return "overlap:mixed"
