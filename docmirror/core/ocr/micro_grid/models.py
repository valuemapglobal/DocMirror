# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contracts for OCR-token based scanned micro-grids."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

BBox = tuple[float, float, float, float]
CellStatus = Literal["exact", "estimated", "empty", "missing"]


@dataclass(frozen=True)
class OCRToken:
    token_id: str
    text: str
    bbox: BBox
    confidence: float = 1.0
    page: int = 0
    source: str = "rapidocr"
    coordinate_system: str = "pdf_points_top_left"
    raw_bbox: BBox | None = None
    raw_coordinate_system: str = "image_pixels"
    source_token_id: str | None = None

    @property
    def center(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.bbox
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "text": self.text,
            "bbox": list(self.bbox),
            "confidence": self.confidence,
            "page": self.page,
            "source": self.source,
            "coordinate_system": self.coordinate_system,
            **({"raw_bbox": list(self.raw_bbox)} if self.raw_bbox else {}),
            "raw_coordinate_system": self.raw_coordinate_system,
            **({"source_token_id": self.source_token_id} if self.source_token_id else {}),
        }


@dataclass(frozen=True)
class MicroGridCandidate:
    candidate_id: str
    page: int
    bbox: BBox
    anchors: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    score: float = 0.0
    coordinate_system: str = "pdf_points_top_left"

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "page": self.page,
            "bbox": list(self.bbox),
            "anchors": list(self.anchors),
            "reason_codes": list(self.reason_codes),
            "score": self.score,
            "coordinate_system": self.coordinate_system,
        }


@dataclass(frozen=True)
class MicroGridCell:
    row_index: int
    col_index: int
    bbox: BBox
    text: str = ""
    confidence: float = 0.0
    geometry_status: CellStatus = "empty"
    token_ids: tuple[str, ...] = ()
    assignment_confidence: float = 0.0
    assignment_method: str = ""
    crop_ocr_text: str | None = None
    recognition_source: str = "tokens"
    recognition_audit: dict[str, Any] = field(default_factory=dict)
    role: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "col_index": self.col_index,
            "bbox": list(self.bbox),
            "text": self.text,
            "confidence": self.confidence,
            "geometry_status": self.geometry_status,
            "token_ids": list(self.token_ids),
            **({"assignment_confidence": self.assignment_confidence} if self.assignment_confidence else {}),
            **({"assignment_method": self.assignment_method} if self.assignment_method else {}),
            **({"crop_ocr_text": self.crop_ocr_text} if self.crop_ocr_text is not None else {}),
            "recognition_source": self.recognition_source,
            **({"recognition_audit": self.recognition_audit} if self.recognition_audit else {}),
            "role": self.role,
        }


@dataclass(frozen=True)
class MicroGrid:
    grid_id: str
    page: int
    bbox: BBox
    anchor_text: str = ""
    row_bands: list[dict[str, Any]] = field(default_factory=list)
    col_bands: list[dict[str, Any]] = field(default_factory=list)
    cells: list[list[MicroGridCell]] = field(default_factory=list)
    grid_type_hint: str = ""
    coordinate_system: str = "pdf_points_top_left"
    geometry_source: str = "ocr_lines+estimated_bands"
    confidence: float = 0.0
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "grid_id": self.grid_id,
            "page": self.page,
            "bbox": list(self.bbox),
            "anchor_text": self.anchor_text,
            "row_bands": self.row_bands,
            "col_bands": self.col_bands,
            "cells": [[cell.to_dict() for cell in row] for row in self.cells],
            "grid_type_hint": self.grid_type_hint,
            "coordinate_system": self.coordinate_system,
            "geometry_source": self.geometry_source,
            "confidence": self.confidence,
            "audit": self.audit,
        }
