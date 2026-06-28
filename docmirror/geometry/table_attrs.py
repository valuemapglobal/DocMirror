# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Helpers for attaching table geometry to physical table blocks."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.geometry.table_geometry import build_table_geometry


def table_geometry_coverage(table: list[list[Any]], cell_bboxes: list[list[Any]] | None) -> float | None:
    """Return covered/non-empty cell ratio for a raw table matrix."""
    nonempty = 0
    covered = 0
    cell_bboxes = cell_bboxes or []
    for ri, row in enumerate(table):
        if not isinstance(row, list):
            continue
        for ci, text in enumerate(row):
            if not str(text).strip():
                continue
            nonempty += 1
            if (
                ri < len(cell_bboxes)
                and isinstance(cell_bboxes[ri], list)
                and ci < len(cell_bboxes[ri])
                and cell_bboxes[ri][ci]
            ):
                covered += 1
    if nonempty == 0:
        return None
    return covered / nonempty


def build_table_geometry_attrs(
    table: list[list[Any]],
    *,
    chars: list[dict[str, Any]] | None = None,
    table_bbox: Sequence[float] | None = None,
    native_cell_bboxes: list[list[Sequence[float] | None]] | None = None,
    page_number: int = 0,
    table_index: int = 0,
    geometry_source: str = "estimated_from_chars",
    geometry_confidence: float | None = None,
    base_attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build block attrs carrying canonical and compatibility geometry keys."""
    attrs = dict(base_attrs or {})
    geometry = build_table_geometry(
        table,
        chars=chars,
        table_bbox=table_bbox,
        native_cell_bboxes=native_cell_bboxes,
        page_number=page_number,
        table_index=table_index,
        geometry_source=geometry_source,
        geometry_confidence=geometry_confidence,
    ).to_attrs()
    if attrs.get("merged_cells"):
        geometry["merged_cells"] = attrs["merged_cells"]

    attrs["geometry"] = geometry
    attrs["cell_bboxes"] = geometry.get("cell_bboxes")
    attrs["cell_geometry_status"] = geometry.get("cell_geometry_status")
    attrs["cell_geometry_loss_reason"] = geometry.get("cell_geometry_loss_reason")
    attrs["cell_evidence_ids"] = geometry.get("cell_evidence_ids")
    attrs["cell_token_ids"] = geometry.get("cell_token_ids")
    attrs["cell_confidences"] = geometry.get("cell_confidences")
    attrs["row_bands"] = geometry.get("row_bands")
    attrs["col_bands"] = geometry.get("col_bands")

    coverage = table_geometry_coverage(table, geometry.get("cell_bboxes"))
    if coverage is not None:
        attrs["geometry_coverage_ratio"] = coverage
    return attrs
