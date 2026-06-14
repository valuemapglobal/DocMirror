# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Layout analysis and zone segmentation facade (CPA design 12)."""

from docmirror.core.segment.layout_analysis import (
    analyze_document_layout,
    analyze_document_layout_parallel,
    analyze_page_layout,
)
from docmirror.core.segment.zone_models import ALPageLayout, ContentRegion, Zone, ZoneTemplate
from docmirror.core.segment.zone_segment import segment_page_into_zones
from docmirror.core.segment.zone_template import apply_zone_template, build_zone_template
from docmirror.core.segment.layout_analysis import _reconstruct_rows_from_chars

__all__ = [
    "ALPageLayout",
    "ContentRegion",
    "Zone",
    "ZoneTemplate",
    "analyze_document_layout",
    "analyze_document_layout_parallel",
    "analyze_page_layout",
    "apply_zone_template",
    "build_zone_template",
    "segment_page_into_zones",
    "_reconstruct_rows_from_chars",
]
