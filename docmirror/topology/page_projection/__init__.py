# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""vNext page projection topology helpers."""

from docmirror.topology.page_projection.block_index import build_page_blocks, page_projection_blocks_enabled
from docmirror.topology.page_projection.build import (
    build_page_regions_for_page,
    build_regions_from_domain_specific,
)
from docmirror.topology.page_projection.detect import RegionCandidate, detect_page_region_candidates
from docmirror.topology.page_projection.models import PageBlock, PageFlow, PageProjection, PageRegion

__all__ = [
    "PageBlock",
    "PageFlow",
    "PageProjection",
    "PageRegion",
    "RegionCandidate",
    "build_page_blocks",
    "build_page_regions_for_page",
    "build_regions_from_domain_specific",
    "detect_page_region_candidates",
    "page_projection_blocks_enabled",
]
