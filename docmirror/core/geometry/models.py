# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lightweight geometry contracts for table layout conservation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

BBox = tuple[float, float, float, float]
GeometryStatus = Literal["exact", "estimated", "missing", "logical_only", "derived"]


@dataclass(frozen=True)
class CellGeometry:
    row_index: int
    col_index: int
    bbox: BBox | None = None
    status: GeometryStatus = "missing"
    confidence: float | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceToken:
    text: str
    bbox: BBox | None = None
    confidence: float = 1.0
    page: int = 0
    coordinate_system: str = "pdf_points_top_left"
    source: str = "unknown"


@dataclass(frozen=True)
class BandGeometry:
    index: int
    bbox: BBox
    role: str = ""


@dataclass(frozen=True)
class TableGeometry:
    table_bbox: BBox | None = None
    cell_bboxes: list[list[BBox | None]] = field(default_factory=list)
    cell_geometry_status: list[list[GeometryStatus]] = field(default_factory=list)
    cell_geometry_loss_reason: list[list[str | None]] = field(default_factory=list)
    cell_evidence_ids: list[list[list[str]]] = field(default_factory=list)
    cell_token_ids: list[list[list[str]]] = field(default_factory=list)
    cell_confidences: list[list[float | None]] = field(default_factory=list)
    row_bands: list[dict] = field(default_factory=list)
    col_bands: list[dict] = field(default_factory=list)
    coordinate_system: str = "pdf_points_top_left"
    geometry_source: str = ""
    geometry_confidence: float | None = None

    def to_attrs(self) -> dict:
        return {
            "table_bbox": list(self.table_bbox) if self.table_bbox else None,
            "cell_bboxes": [[list(cell) if cell else None for cell in row] for row in self.cell_bboxes],
            "cell_geometry_status": self.cell_geometry_status,
            "cell_geometry_loss_reason": self.cell_geometry_loss_reason,
            "cell_evidence_ids": self.cell_evidence_ids,
            "cell_token_ids": self.cell_token_ids,
            "cell_confidences": self.cell_confidences,
            "row_bands": self.row_bands,
            "col_bands": self.col_bands,
            "coordinate_system": self.coordinate_system,
            "geometry_source": self.geometry_source,
            "geometry_confidence": self.geometry_confidence,
        }
