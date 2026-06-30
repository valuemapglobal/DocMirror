# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local OCR repair engine.

The engine generates OCR candidates from local page-image crops.  It does not
decide whether a candidate is true; that remains a domain solver decision.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from docmirror.evidence.repair import RepairCandidate, RepairRequest
from docmirror.ocr.repair.crop_variants import crop_regions
from docmirror.ocr.repair.fusion import fuse_text_candidates
from docmirror.ocr.repair.preprocess_variants import build_preprocess_variants
from docmirror.ocr.repair.recognizers import rapidocr_recognize, tesseract_recognize

OCRRecognizer = Callable[[Any], list[dict[str, Any]]]


class LocalOCRRepairEngine:
    """Generate OCR repair candidates from a local page image."""

    def __init__(self, recognizers: list[OCRRecognizer] | None = None) -> None:
        self.recognizers = recognizers or [
            lambda image: rapidocr_recognize(image, source="rapidocr"),
            lambda image: tesseract_recognize(image, source="tesseract"),
        ]

    def repair_from_image(
        self,
        request: RepairRequest,
        page_image: Any,
        *,
        page_width: float,
        page_height: float,
        max_variants: int = 48,
        min_confidence: float = 0.35,
    ) -> list[RepairCandidate]:
        """Return fused candidates for one request and page image."""
        if not request.bbox:
            return []
        shape = getattr(page_image, "shape", None)
        if not shape or len(shape) < 2:
            return []
        image_height, image_width = int(shape[0]), int(shape[1])
        variants = crop_regions(
            request.bbox,
            page_width=page_width,
            page_height=page_height,
            image_width=image_width,
            image_height=image_height,
        )
        raw_candidates: list[dict[str, Any]] = []
        variant_count = 0
        for crop_meta in variants:
            if variant_count >= max_variants:
                break
            region = crop_meta["region"]
            x0, y0, x1, y1 = region
            crop = page_image[int(y0) : int(y1), int(x0) : int(x1)]
            for preprocess_name, image_variant in build_preprocess_variants(crop):
                if variant_count >= max_variants:
                    break
                variant_count += 1
                for recognizer in self.recognizers:
                    for item in recognizer(image_variant) or []:
                        candidate = dict(item)
                        candidate["crop"] = dict(crop_meta)
                        candidate["preprocess"] = preprocess_name
                        raw_candidates.append(candidate)
        return fuse_text_candidates(raw_candidates, request_id=request.request_id, min_confidence=min_confidence)


__all__ = ["LocalOCRRepairEngine", "OCRRecognizer"]
