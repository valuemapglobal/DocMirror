# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""CPS page stage: watermark filter + quality router."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from docmirror.core.pipeline.context import PageExtractionContext
from docmirror.core.utils.watermark import (
    _dedup_overlapping_chars,
    filter_watermark_page,
)

if TYPE_CHECKING:
    from docmirror.core.pipeline.page_extractor import PageExtractor

logger = logging.getLogger(__name__)


def run_prepare(
    extractor: PageExtractor,
    ctx: PageExtractionContext,
) -> tuple[Any, bool, Any]:
    """Prepare pdfplumber page: watermark filter and optional quality router."""
    page_plum = ctx.page_plum
    strategy_params = ctx.strategy_params or {}
    page_quality = ctx.page_quality
    content_type = ctx.content_type
    extraction_profile = ctx.extraction_profile

    _router = None
    if not (extraction_profile and extraction_profile.skip_pid_resample):
        try:
            from docmirror.core.analyze.quality_router import AdaptiveQualityRouter

            _router = AdaptiveQualityRouter(strategy_params)
        except Exception as exc:
            logger.debug(f"QualityRouter init: suppressed {exc}")

    _use_deep_watermark = False
    if content_type != "table_dominant":
        if _router and strategy_params:
            _use_deep_watermark = not strategy_params.get("skip_watermark_filter", False) and page_quality < 85

    _chars_before_wm = len(page_plum.chars)
    if _use_deep_watermark:
        try:
            from docmirror.core.utils.watermark import separate_watermark_layer

            page_plum = separate_watermark_layer(page_plum)
        except Exception as exc:
            logger.debug(f"deep watermark separation: suppressed {exc}")
            page_plum = filter_watermark_page(page_plum)
        watermark_filtered = len(page_plum.chars) < _chars_before_wm
        page_plum = _dedup_overlapping_chars(page_plum)
    else:
        from docmirror.core.utils.watermark import fused_filter_and_dedup

        page_plum, watermark_filtered = fused_filter_and_dedup(page_plum)

    return page_plum, watermark_filtered, _router
