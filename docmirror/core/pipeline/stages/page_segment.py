# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""CPS page stage: spatial segmentation into zones."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from docmirror.core.extract.segmentation import segment_page_for_extraction
from docmirror.core.pipeline.context import PageExtractionContext
from docmirror.core.segment.zones import apply_zone_template, build_zone_template

if TYPE_CHECKING:
    from docmirror.core.pipeline.page_extractor import PageExtractor

logger = logging.getLogger(__name__)
_clock = time.perf_counter


def run_segment(
    extractor: PageExtractor,
    ctx: PageExtractionContext,
    page_plum: Any,
) -> tuple[list | None, bool, float]:
    """Segment page into zones; may build zone template on host."""
    page_idx = ctx.page_idx
    fitz_page = ctx.fitz_page
    zone_template = ctx.zone_template
    extraction_profile = ctx.extraction_profile
    width, height = ctx.layout_al.width if hasattr(ctx.layout_al, "width") else fitz_page.rect.width, (
        ctx.layout_al.height if hasattr(ctx.layout_al, "height") else fitz_page.rect.height
    )

    _seg_t = _clock()
    used_template = False
    zones = None

    skip_zone_template = extraction_profile and extraction_profile.is_full_page_table()
    if zone_template is not None and not skip_zone_template:
        zones = apply_zone_template(zone_template, page_plum, page_idx)
        if zones is not None:
            used_template = True

    if zones is None:
        if extractor._host._layout_detector and not skip_zone_template:
            zones = extractor._model_segmentation(fitz_page, page_plum, page_idx)
        else:
            zones = segment_page_for_extraction(page_plum, page_idx, extraction_profile)

    seg_ms = (_clock() - _seg_t) * 1000
    if used_template:
        logger.debug(f"[DocMirror] Perf #9: page {page_idx} segmentation via template ({seg_ms:.0f}ms)")

    should_build_template = (
        not used_template
        and zones
        and len(zones) >= 2
    )
    if should_build_template:
        try:
            width_plum = page_plum.width if hasattr(page_plum, "width") else width
            height_plum = page_plum.height if hasattr(page_plum, "height") else height
            new_template = build_zone_template(zones, width_plum, height_plum, page_idx)
            if new_template.zone_count > 0:
                extractor._host._zone_template = new_template
                logger.debug(
                    f"[DocMirror] Perf #9: zone template {'rebuilt' if page_idx > 0 else 'built'} "
                    f"({new_template.zone_count} zones) from page {page_idx}"
                )
        except Exception as exc:
            logger.debug(f"[DocMirror] Perf #9: template build failed: {exc}")

    return zones, used_template, seg_ms
