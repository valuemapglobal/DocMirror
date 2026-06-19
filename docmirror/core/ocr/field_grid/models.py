# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Field grid data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from docmirror.core.ocr.micro_grid.models import BBox

GeometryStatus = Literal["exact", "estimated", "empty", "quarantined"]


@dataclass(frozen=True)
class LabelToken:
    text: str
    bbox: BBox
    line_id: str
    token_ids: tuple[str, ...] = ()
    confidence: float = 1.0

    @property
    def x_center(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "bbox": list(self.bbox),
            "line_id": self.line_id,
            "token_ids": list(self.token_ids),
            "confidence": self.confidence,
            "x_center": self.x_center,
        }


@dataclass(frozen=True)
class FieldCell:
    cell_id: str
    row_index: int
    col_index: int
    label_text: str | None
    text: str
    raw_text: str
    bbox: BBox
    token_ids: tuple[str, ...] = ()
    line_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    assignment_confidence: float = 0.0
    assignment_method: str = "empty"
    geometry_status: GeometryStatus = "empty"
    inferred_types: tuple[str, ...] = ()
    quarantine_reason: str | None = None
    continuation_cell_ids: tuple[str, ...] = ()
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "cell_id": self.cell_id,
            "row_index": self.row_index,
            "col_index": self.col_index,
            "label_text": self.label_text,
            "text": self.text,
            "raw_text": self.raw_text,
            "bbox": list(self.bbox),
            "token_ids": list(self.token_ids),
            "line_ids": list(self.line_ids),
            "confidence": self.confidence,
            "assignment_confidence": self.assignment_confidence,
            "assignment_method": self.assignment_method,
            "geometry_status": self.geometry_status,
            "inferred_types": list(self.inferred_types),
        }
        if self.quarantine_reason:
            out["quarantine_reason"] = self.quarantine_reason
        if self.continuation_cell_ids:
            out["continuation_cell_ids"] = list(self.continuation_cell_ids)
        if self.audit:
            out["audit"] = self.audit
        return out
