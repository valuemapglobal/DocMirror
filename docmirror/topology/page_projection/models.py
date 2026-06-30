# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""vNext page projection dataclasses.

The model owns the wire-compatible page projection shape emitted by vNext.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PageFlow:
    texts: list[dict[str, Any]] = field(default_factory=list)
    key_values: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "texts": list(self.texts),
            "key_values": list(self.key_values),
        }


@dataclass
class PageRegion:
    region_id: str
    kind: str
    morphology: str
    bbox: list[float]
    structure: dict[str, Any]
    anchor_text: str = ""
    confidence: float = 0.0
    ocr_evidence_ref: str | None = None
    schema_hint: str = ""
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "region_id": self.region_id,
            "kind": self.kind,
            "morphology": self.morphology,
            "bbox": list(self.bbox),
            "anchor_text": self.anchor_text,
            "structure": self.structure,
            "confidence": self.confidence,
        }
        if self.ocr_evidence_ref:
            out["ocr_evidence_ref"] = self.ocr_evidence_ref
        if self.schema_hint:
            out["schema_hint"] = self.schema_hint
        if self.audit:
            out["audit"] = self.audit
        return out


@dataclass
class PageBlock:
    block_id: str
    morphology: str
    kind: str
    ref: str
    bbox: list[float] = field(default_factory=list)
    anchor_text: str = ""
    schema_hint: str = ""
    confidence: float = 0.0
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "block_id": self.block_id,
            "morphology": self.morphology,
            "kind": self.kind,
            "ref": self.ref,
            "bbox": list(self.bbox),
            "anchor_text": self.anchor_text,
            "confidence": self.confidence,
        }
        if self.schema_hint:
            out["schema_hint"] = self.schema_hint
        if self.audit:
            out["audit"] = self.audit
        return out


@dataclass
class PageProjection:
    page_number: int
    width: float | None = None
    height: float | None = None
    coordinate_system: str = "pdf_points_top_left"
    flow: PageFlow = field(default_factory=PageFlow)
    tables: list[dict[str, Any]] = field(default_factory=list)
    regions: list[PageRegion] = field(default_factory=list)
    blocks: list[PageBlock] = field(default_factory=list)
    morphology_summary: dict[str, int] = field(default_factory=dict)
    ocr_evidence_ref: str | None = None
    reading_order: list[str] = field(default_factory=list)
    reading_order_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "page_number": self.page_number,
            "coordinate_system": self.coordinate_system,
            "flow": self.flow.to_dict(),
            "tables": list(self.tables),
            "regions": [region.to_dict() for region in self.regions],
        }
        if self.blocks:
            out["blocks"] = [block.to_dict() for block in self.blocks]
        if self.morphology_summary:
            out["morphology_summary"] = dict(self.morphology_summary)
        if self.width is not None:
            out["width"] = self.width
        if self.height is not None:
            out["height"] = self.height
        if self.ocr_evidence_ref:
            out["ocr_evidence_ref"] = self.ocr_evidence_ref
        if self.reading_order:
            out["reading_order"] = list(self.reading_order)
        if self.reading_order_refs:
            out["reading_order_refs"] = list(self.reading_order_refs)
        return out
