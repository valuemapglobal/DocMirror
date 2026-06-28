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

    @property
    def confidence_tier(self) -> Literal["high", "medium", "low"]:
        """Classify token confidence into three tiers."""
        if self.confidence >= 0.7:
            return "high"
        elif self.confidence >= 0.3:
            return "medium"
        return "low"

    def is_reliable(self, threshold: float = 0.3) -> bool:
        """Check if token meets a consumer-specific confidence threshold."""
        return self.confidence >= threshold

    @staticmethod
    def from_rapidocr_word(
        word: tuple,
        page: int = 1,
        source: str = "rapidocr",
        idx: int = 0,
    ) -> "OCRToken":
        """Convert a RapidOCR word tuple to an OCRToken.

        Expected word tuple format: (x0, y0, x1, y1, text, confidence)
        Compatible with output from runner_legacy._run_ocr() and
        rapidocr_engine.RapidOCREngine.detect_image_words().
        """
        if len(word) < 5:
            raise ValueError(f"RapidOCR word tuple too short: {len(word)} elements")

        text = str(word[4] or "").strip()
        if not text:
            raise ValueError("Empty text in RapidOCR word tuple")

        try:
            x0 = float(word[0])
            y0 = float(word[1])
            x1 = float(word[2])
            y1 = float(word[3])
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid bbox in RapidOCR word tuple: {e}") from e

        # Extract confidence — try different positions for compatibility
        confidence = 1.0
        for idx_val in (-1, 5):
            try:
                value = float(word[idx_val])
            except (IndexError, TypeError, ValueError):
                continue
            if 0.0 <= value <= 1.0:
                confidence = value
                break

        bbox: BBox = (x0, y0, x1, y1)
        return OCRToken(
            token_id=f"ocr_p{page}_t{idx}",
            text=text,
            bbox=bbox,
            confidence=confidence,
            page=page,
            source=source,
            coordinate_system="image_pixels",
            raw_bbox=bbox,
            raw_coordinate_system="image_pixels",
        )

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
class TieredTokenCollection:
    """All OCR tokens preserved in three confidence tiers — none discarded.

    Each tier is independently accessible. Consumers call ``filter_by_threshold()``
    with their own tolerance rather than relying on a single binary gate.
    """
    high: list[OCRToken] = field(default_factory=list)      # confidence >= 0.7
    medium: list[OCRToken] = field(default_factory=list)    # 0.3 <= confidence < 0.7
    low: list[OCRToken] = field(default_factory=list)       # confidence < 0.3

    @property
    def all(self) -> list[OCRToken]:
        return self.high + self.medium + self.low

    def filter_by_threshold(self, threshold: float) -> list[OCRToken]:
        """Return all tokens with confidence >= threshold."""
        return [t for t in self.all if t.confidence >= threshold]

    @classmethod
    def from_tokens(cls, tokens: list[OCRToken]) -> "TieredTokenCollection":
        """Partition a flat token list into three confidence tiers."""
        high: list[OCRToken] = []
        medium: list[OCRToken] = []
        low: list[OCRToken] = []
        for t in tokens:
            tier = t.confidence_tier
            if tier == "high":
                high.append(t)
            elif tier == "medium":
                medium.append(t)
            else:
                low.append(t)
        return cls(high=high, medium=medium, low=low)


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
