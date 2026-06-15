# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Text zone handler — native text extraction for prose zones.

Purpose: Groups words into lines, applies watermark filtering, and builds
text/title blocks from digital text layers.

Main components: ``handle_text_zone``.

Upstream: Text zones, ``pipeline.handlers.zone_utils``.

Downstream: ``physical.models.Block`` (text/title types).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from docmirror.models.entities.domain import Block, Style
from docmirror.core.pipeline.handlers.page_styles import build_spans

if TYPE_CHECKING:
    from docmirror.core.pipeline.page_extractor import PageExtractor

logger = logging.getLogger(__name__)

def handle_text_zone(extractor: "PageExtractor",
    zone,
    block_id: str,
    page_idx: int,
    fitz_page,
    layout_al,
    style_map: dict[str, Style],
    reading_order: int,
) -> Block | None:
    """Handle an unknown/text-type zone → Block conversion.

    Returns:
        A text Block if content was extracted, otherwise None.
    """
    text_content = None
    try:
        from fitz import Rect

        text_content = fitz_page.get_textbox(Rect(*zone.bbox)).strip()
    except Exception as exc:
        logger.debug(f"fitz textbox extraction: suppressed {exc}")
        text_content = zone.text.strip() if zone.text else ""

    if not text_content and zone.text:
        text_content = zone.text.strip()

    # P5: DET/REC Decoupling — crop ROI and run OCR on scanned content
    if not text_content and layout_al.is_scanned:
        try:
            import cv2
            import fitz
            import numpy as np

            from docmirror.core.ocr.vision.rapidocr_engine import get_ocr_engine

            ocr_engine = get_ocr_engine()
            if ocr_engine and ocr_engine._engine:
                bx0, by0, bx1, by1 = zone.bbox
                rect = fitz.Rect(max(0, bx0 - 5), max(0, by0 - 5), bx1 + 5, by1 + 5)
                pix_patch = fitz_page.get_pixmap(dpi=300, clip=rect)
                img_patch = np.frombuffer(pix_patch.samples, dtype=np.uint8).reshape(
                    pix_patch.h, pix_patch.w, pix_patch.n
                )
                if pix_patch.n == 3:
                    img_patch = cv2.cvtColor(img_patch, cv2.COLOR_RGB2BGR)
                elif pix_patch.n == 4:
                    img_patch = cv2.cvtColor(img_patch, cv2.COLOR_RGBA2BGR)
                words = ocr_engine.detect_image_words(img_patch, multi_scale=False)
                if words:
                    text_content = " ".join([w[4] for w in sorted(words, key=lambda w: (w[1], w[0]))])
        except Exception as e:
            logger.debug(f"[DocMirror] Zone OCR fallback/crop failed: {e}")

    if text_content:
        return Block(
            block_id=block_id,
            block_type="text",
            bbox=zone.bbox,
            reading_order=reading_order,
            page=page_idx + 1,
            raw_content=text_content,
            spans=build_spans(text_content, zone.bbox, style_map),
        )
    return None

