# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic region-level OCR repair helpers for local structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from docmirror.ocr.local_structure.models import BBox
from docmirror.ocr.micro_grid.cell_recognition import pdf_bbox_to_image_region


@dataclass(frozen=True)
class RegionRecognition:
    text: str
    confidence: float = 0.0
    source: str = "none"
    raw_text: str = ""
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "source": self.source,
            "raw_text": self.raw_text,
            "audit": self.audit,
        }


def recognize_structure_region_from_image(
    page_image: Any,
    bbox: BBox,
    *,
    page_width: float,
    page_height: float,
    min_confidence: float = 0.35,
    pad_px: int = 4,
) -> RegionRecognition:
    """Run forced OCR on a local-structure region without applying domain semantics."""
    shape = getattr(page_image, "shape", None)
    if not shape or len(shape) < 2:
        return RegionRecognition("", 0.0, "unavailable", audit={"reason": "missing_page_image"})

    image_height, image_width = int(shape[0]), int(shape[1])
    region = pdf_bbox_to_image_region(
        bbox,
        page_width=page_width,
        page_height=page_height,
        image_width=image_width,
        image_height=image_height,
        pad_px=pad_px,
    )
    if region[2] - region[0] < 3 or region[3] - region[1] < 3:
        return RegionRecognition("", 0.0, "unavailable", audit={"reason": "empty_region", "region": region})

    try:
        from docmirror.ocr.vision.rapidocr_engine import get_ocr_engine

        raw = get_ocr_engine().force_recognize_regions(page_image, [region])
    except Exception as exc:
        return RegionRecognition("", 0.0, "region_crop_ocr_error", audit={"reason": str(exc), "region": region})

    if not raw:
        return RegionRecognition("", 0.0, "region_crop_ocr", audit={"reason": "no_text", "region": region})

    best = max(raw, key=lambda item: float(item[5]) if len(item) > 5 else 0.0)
    raw_text = str(best[4] if len(best) > 4 else "").strip()
    confidence = float(best[5] if len(best) > 5 else 0.0)
    if confidence < min_confidence or not raw_text:
        return RegionRecognition(
            "",
            confidence,
            "region_crop_ocr",
            raw_text=raw_text,
            audit={"reason": "filtered", "region": region},
        )
    return RegionRecognition(
        raw_text,
        confidence,
        "region_crop_ocr",
        raw_text=raw_text,
        audit={"region": region},
    )
