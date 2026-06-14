# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Zone image crop and formula recognition utilities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docmirror.core.pipeline.page_extractor import PageExtractor

logger = logging.getLogger(__name__)

def group_words_into_lines(words: list[dict], tolerance_ratio: float = 0.5) -> list[list[dict]]:
    """Group OCR words into lines by Y coordinate.

    Args:
        words: List of OCR word dicts, each with bbox and text fields.
        tolerance_ratio: Line spacing tolerance (relative to average character height).

    Returns:
        Word lists grouped by line.
    """
    if not words:
        return []

    # Calculate centre y of each word
    items = []
    for w in words:
        bbox = w.get("bbox", (0, 0, 0, 0))
        if len(bbox) >= 4:
            cy = (bbox[1] + bbox[3]) / 2
            h = bbox[3] - bbox[1]
            items.append((cy, h, w))

    if not items:
        return []

    # Sort by y
    items.sort(key=lambda x: x[0])

    # Estimate average character height
    avg_h = sum(h for _, h, _ in items) / len(items) if items else 10
    tolerance = avg_h * tolerance_ratio

    # Group into lines
    lines: list[list[dict]] = []
    current_line: list[dict] = [items[0][2]]
    current_y = items[0][0]

    for cy, h, w in items[1:]:
        if abs(cy - current_y) <= tolerance:
            current_line.append(w)
        else:
            # Sort line internally by x
            current_line.sort(key=lambda word: word.get("bbox", (0,))[0])
            lines.append(current_line)
            current_line = [w]
            current_y = cy

    if current_line:
        current_line.sort(key=lambda word: word.get("bbox", (0,))[0])
        lines.append(current_line)

    return lines



def crop_zone_image(fitz_page, bbox) -> bytes:
    """Crop an image region from a page at the given bbox."""
    try:
        import fitz as pymupdf

        rect = pymupdf.Rect(*bbox)
        clip = fitz_page.get_pixmap(clip=rect, dpi=300)
        return clip.tobytes("png")
    except Exception as exc:
        logger.debug(f"crop_image: suppressed {exc}")
        return b""



def recognize_formula(extractor: "PageExtractor", image_bytes: bytes) -> str:
    """Formula image -> LaTeX (delegated to FormulaEngine).

    FormulaEngine internally selects backend by strategy:
        UniMERNet ONNX > rapid_latex_ocr > empty string
    """
    return extractor._host._formula_engine.recognize(image_bytes)

