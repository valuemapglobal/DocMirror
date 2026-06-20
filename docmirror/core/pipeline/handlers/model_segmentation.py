# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Model segmentation handler — ML-based layout fallback.

Purpose: Invokes layout detection models when rule-based segmentation is
insufficient, returning refined region bboxes.

Main components: ``model_segmentation``.

Upstream: ``page_segment`` when template/heuristic segmentation fails.

Downstream: ``segment.layout_model``, zone builder.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from docmirror.core.segment.zones import Zone, segment_page_into_zones

if TYPE_CHECKING:
    from docmirror.core.pipeline.page_extractor import PageExtractor

logger = logging.getLogger(__name__)


def model_segmentation(extractor: PageExtractor, fitz_page, page_plum, page_idx: int) -> list:
    """Model-based layout analysis: render page image -> DocLayout-YOLO inference -> Zone list.

    Falls back to rule-based method on failure.
    """
    try:
        import numpy as np

        # Render page as image (configurable DPI, default 200)
        render_dpi = extractor._host._model_render_dpi
        pixmap = fitz_page.get_pixmap(dpi=render_dpi)
        img_data = pixmap.samples
        img = np.frombuffer(img_data, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
        # RGBA → RGB
        if pixmap.n == 4:
            img = img[:, :, :3]

        # Model inference
        regions = extractor._host._layout_detector.detect(img, confidence_threshold=0.4)

        if not regions:
            logger.debug(f"[DocMirror] model detected 0 regions on page {page_idx}, falling back")
            return segment_page_into_zones(page_plum, page_idx)

        # Coordinate conversion: pixel space -> PDF point space (72 DPI)
        scale = 72.0 / render_dpi
        zones = []
        for region in regions:
            rx0, ry0, rx1, ry1 = region.bbox
            zone_bbox = (rx0 * scale, ry0 * scale, rx1 * scale, ry1 * scale)

            # Get text within region
            zone_text = ""
            zone_chars = []
            try:
                for char in page_plum.chars:
                    cx = float(char.get("x0", 0))
                    cy = float(char.get("top", 0))
                    if zone_bbox[0] <= cx <= zone_bbox[2] and zone_bbox[1] <= cy <= zone_bbox[3]:
                        zone_chars.append(char)
                        zone_text += char.get("text", "")
            except Exception as exc:
                logger.debug(f"operation: suppressed {exc}")

            zones.append(
                Zone(
                    type=region.category,
                    bbox=zone_bbox,
                    text=zone_text.strip(),
                    chars=zone_chars,
                    confidence=region.confidence,
                )
            )

        logger.info(f"[DocMirror] model segmentation: {len(zones)} zones on page {page_idx}")
        return zones

    except Exception as e:
        logger.warning(f"[DocMirror] model segmentation failed: {e}, falling back to rules")
        return segment_page_into_zones(page_plum, page_idx)
