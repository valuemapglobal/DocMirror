# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Page-Centric Mirror (PCM) — page canvas and region models."""

from docmirror.ocr.page_canvas.block_index import build_page_blocks, pcm_blocks_enabled
from docmirror.ocr.page_canvas.build import (
    build_page_regions_for_page,
    build_regions_from_domain_specific,
)
from docmirror.ocr.page_canvas.detect import RegionCandidate, detect_page_region_candidates
from docmirror.ocr.page_canvas.models import PageBlock, PageCanvas, PageFlow, PageRegion

__all__ = [
    "PageBlock",
    "PageCanvas",
    "PageFlow",
    "PageRegion",
    "RegionCandidate",
    "build_page_blocks",
    "build_page_regions_for_page",
    "build_regions_from_domain_specific",
    "detect_page_region_candidates",
    "pcm_blocks_enabled",
]
