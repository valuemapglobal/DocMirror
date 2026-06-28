# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Zone constants and helpers — shared zone type definitions.

Purpose: Centralizes zone type strings, defaults, and small helpers referenced
by segmentation and handlers.

Main components: Zone type constants and utility functions.

Upstream: Internal segment modules.

Downstream: ``pipeline.handlers``, ``extract.zone_crop``.
"""

from docmirror.layout.segment.layout_analysis import (
    _reconstruct_rows_from_chars,
    analyze_document_layout,
    analyze_document_layout_parallel,
    analyze_page_layout,
)
from docmirror.layout.segment.zone_models import ALPageLayout, ContentRegion, Zone, ZoneTemplate
from docmirror.layout.segment.zone_segment import segment_page_into_zones
from docmirror.layout.segment.zone_template import apply_zone_template, build_zone_template

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
