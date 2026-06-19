# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic contracts for scanned local structure restoration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

BBox = tuple[float, float, float, float]
NodeRole = Literal["anchor", "label", "value", "caption", "separator", "unknown"]
EdgeRelation = Literal["label_of", "same_field", "next_block", "belongs_to", "continuation"]


@dataclass(frozen=True)
class StructureNode:
    node_id: str
    role: NodeRole
    text: str
    bbox: BBox
    page: int
    token_ids: tuple[str, ...] = ()
    line_ids: tuple[str, ...] = ()
    confidence: float = 1.0
    normalized_text: str | None = None
    recognition_source: str = "ocr"
    audit: dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.bbox
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "text": self.text,
            "bbox": list(self.bbox),
            "page": self.page,
            "token_ids": list(self.token_ids),
            "line_ids": list(self.line_ids),
            "confidence": self.confidence,
            **({"normalized_text": self.normalized_text} if self.normalized_text is not None else {}),
            "recognition_source": self.recognition_source,
            **({"audit": self.audit} if self.audit else {}),
        }


@dataclass(frozen=True)
class StructureEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation: EdgeRelation
    confidence: float = 1.0
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "relation": self.relation,
            "confidence": self.confidence,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class LocalStructureCandidate:
    candidate_id: str
    page: int
    bbox: BBox
    anchors: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    score: float = 0.0
    coordinate_system: str = "pdf_points_top_left"
    source_line_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "page": self.page,
            "bbox": list(self.bbox),
            "anchors": list(self.anchors),
            "reason_codes": list(self.reason_codes),
            "score": self.score,
            "coordinate_system": self.coordinate_system,
            "source_line_ids": list(self.source_line_ids),
        }


@dataclass(frozen=True)
class LocalStructure:
    structure_id: str
    page: int
    bbox: BBox
    structure_kind: str
    anchors: tuple[str, ...] = ()
    row_bands: tuple[dict[str, Any], ...] = ()
    col_bands: tuple[dict[str, Any], ...] = ()
    nodes: tuple[StructureNode, ...] = ()
    edges: tuple[StructureEdge, ...] = ()
    cells: tuple[Any, ...] = ()
    confidence: float = 0.0
    coordinate_system: str = "pdf_points_top_left"
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "structure_id": self.structure_id,
            "page": self.page,
            "bbox": list(self.bbox),
            "structure_kind": self.structure_kind,
            "anchors": list(self.anchors),
            "row_bands": [dict(row) for row in self.row_bands],
            "col_bands": [dict(col) for col in self.col_bands],
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "confidence": self.confidence,
            "coordinate_system": self.coordinate_system,
            "audit": self.audit,
        }
        if self.cells:
            out["cells"] = [
                cell.to_dict() if hasattr(cell, "to_dict") else dict(cell)
                for cell in self.cells
            ]
        return out
