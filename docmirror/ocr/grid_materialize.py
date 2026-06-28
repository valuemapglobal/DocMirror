# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unified grid cell materialization with exclusive token assignment (Design 19 P2).

Both field_grid and micro_grid share one assign pass: each OCR token maps to at
most one (row_index, col_index) cell. Native tokens win over char/line splits.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from docmirror.ocr.field_grid.assign import (
    assignment_confidence,
    assignment_method,
    cell_bbox,
)
from docmirror.ocr.field_grid.geometry import bbox_overlap_ratio
from docmirror.ocr.field_grid.tokens import _source_priority, dedupe_visual_tokens
from docmirror.ocr.micro_grid.models import BBox, OCRToken

GridKey = tuple[int, int]


@dataclass(frozen=True)
class GridCell:
    row_index: int
    col_index: int
    bbox: BBox
    text: str
    token_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    assignment_confidence: float = 0.0
    assignment_method: str = "empty"
    geometry_status: str = "empty"
    role: str = ""
    label_text: str | None = None
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "row_index": self.row_index,
            "col_index": self.col_index,
            "bbox": list(self.bbox),
            "text": self.text,
            "token_ids": list(self.token_ids),
            "confidence": self.confidence,
            "assignment_confidence": self.assignment_confidence,
            "assignment_method": self.assignment_method,
            "geometry_status": self.geometry_status,
        }
        if self.role:
            out["role"] = self.role
        if self.label_text:
            out["label_text"] = self.label_text
        if self.audit:
            out["audit"] = self.audit
        return out


def _cell_match_score(
    token: OCRToken,
    row_band: dict[str, Any],
    col_band: dict[str, Any],
    *,
    min_token_overlap: float,
) -> tuple[float, float] | None:
    cell = cell_bbox(row_band, col_band)
    overlap = bbox_overlap_ratio(token.bbox, cell)
    cx, cy = token.center
    center_inside = cell[0] <= cx <= cell[2] and cell[1] <= cy <= cell[3]
    if overlap < min_token_overlap and not (center_inside and overlap > 0.0):
        return None
    cell_center_x = (cell[0] + cell[2]) / 2.0
    cell_center_y = (cell[1] + cell[3]) / 2.0
    center_distance = abs(cx - cell_center_x) + abs(cy - cell_center_y)
    score = overlap + (0.05 if center_inside else 0.0)
    return score, center_distance


def exclusive_assign_tokens_to_grid(
    tokens: Iterable[OCRToken],
    row_bands: list[dict[str, Any]],
    col_bands: list[dict[str, Any]],
    *,
    min_token_overlap: float = 0.20,
) -> dict[GridKey, list[OCRToken]]:
    """Assign each token to at most one grid cell across all row/col bands."""
    token_list = dedupe_visual_tokens(tokens)
    assignments: dict[GridKey, list[OCRToken]] = {
        (int(row["index"]), int(col["index"])): [] for row in row_bands for col in col_bands
    }
    for token in token_list:
        best_key: GridKey | None = None
        best_score = -1.0
        best_distance = float("inf")
        for row_band in row_bands:
            row_index = int(row_band["index"])
            for col_band in col_bands:
                col_index = int(col_band["index"])
                matched = _cell_match_score(
                    token,
                    row_band,
                    col_band,
                    min_token_overlap=min_token_overlap,
                )
                if matched is None:
                    continue
                score, center_distance = matched
                key = (row_index, col_index)
                if score > best_score + 1e-9 or (abs(score - best_score) <= 1e-9 and center_distance < best_distance):
                    best_key = key
                    best_score = score
                    best_distance = center_distance
        if best_key is not None and best_score > 0.0:
            assignments[best_key].append(token)
    return {key: coalesce_tokens_prefer_native(bucket) for key, bucket in assignments.items() if bucket}


def assign_tokens_to_col_bands_exclusive(
    tokens: Iterable[OCRToken],
    row_band: dict[str, Any],
    col_bands: Iterable[dict[str, Any]],
    *,
    min_token_overlap: float = 0.20,
) -> dict[int, list[OCRToken]]:
    """Row-scoped exclusive assign (backward-compatible bucket keyed by col index)."""
    bands = list(col_bands)
    grid = exclusive_assign_tokens_to_grid(
        tokens,
        [row_band],
        bands,
        min_token_overlap=min_token_overlap,
    )
    row_index = int(row_band["index"])
    out: dict[int, list[OCRToken]] = {int(band["index"]): [] for band in bands}
    for (_row, col_index), bucket in grid.items():
        if _row == row_index:
            out[col_index] = bucket
    return out


def coalesce_tokens_prefer_native(tokens: Iterable[OCRToken]) -> list[OCRToken]:
    """Drop char/line split fragments when a native parent token is present."""
    token_list = list(tokens)
    if not token_list:
        return []
    native_ids = {
        token.token_id for token in token_list if token.source_token_id is None and _source_priority(token) >= 60
    }
    filtered: list[OCRToken] = []
    for token in token_list:
        if token.source_token_id and token.source_token_id in native_ids:
            continue
        filtered.append(token)
    grouped: dict[str, OCRToken] = {}
    for token in filtered:
        group_key = token.source_token_id or token.token_id
        existing = grouped.get(group_key)
        if existing is None or _source_priority(token) > _source_priority(existing):
            grouped[group_key] = token
    return dedupe_visual_tokens(grouped.values())


def assemble_cell_text(tokens: Iterable[OCRToken]) -> str:
    return "".join(token.text for token in sorted(tokens, key=lambda t: (t.bbox[1], t.bbox[0]))).strip()


def materialize_grid_cell(
    *,
    row_band: dict[str, Any],
    col_band: dict[str, Any],
    tokens: Iterable[OCRToken],
    role: str = "",
    label_text: str | None = None,
    assignment_method_override: str | None = None,
) -> GridCell | None:
    token_list = coalesce_tokens_prefer_native(tokens)
    if not token_list:
        return None
    text = assemble_cell_text(token_list)
    if not text:
        return None
    method = assignment_method_override or assignment_method(token_list)
    assign_conf = assignment_confidence(token_list, row_band, col_band)
    geometry_status = "exact" if text and method == "overlap:native_token" else ("estimated" if text else "empty")
    return GridCell(
        row_index=int(row_band["index"]),
        col_index=int(col_band["index"]),
        bbox=cell_bbox(row_band, col_band),
        text=text,
        token_ids=tuple(token.token_id for token in token_list),
        confidence=max(token.confidence for token in token_list),
        assignment_confidence=assign_conf,
        assignment_method=method,
        geometry_status=geometry_status,
        role=role,
        label_text=label_text,
    )


def materialize_grid_cells(
    assignments: dict[GridKey, list[OCRToken]],
    row_bands: list[dict[str, Any]],
    col_bands: list[dict[str, Any]],
    *,
    col_label_by_index: dict[int, str] | None = None,
) -> list[GridCell]:
    """Build GridCell objects from an exclusive assignment map."""
    row_by_index = {int(row["index"]): row for row in row_bands}
    col_by_index = {int(col["index"]): col for col in col_bands}
    labels = col_label_by_index or {}
    cells: list[GridCell] = []
    for (row_index, col_index), bucket in sorted(assignments.items()):
        row_band = row_by_index.get(row_index)
        col_band = col_by_index.get(col_index)
        if row_band is None or col_band is None:
            continue
        cell = materialize_grid_cell(
            row_band=row_band,
            col_band=col_band,
            tokens=bucket,
            label_text=labels.get(col_index) or str(col_band.get("header") or "") or None,
            role=str(col_band.get("role") or ""),
        )
        if cell is not None:
            cells.append(cell)
    return cells
