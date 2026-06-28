# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Segment package — layout analysis and semantic zone partitioning.

Purpose: Transforms raw page geometry into typed zones (text, table, formula)
that the pipeline handlers consume.

Main components: ``segment_page_into_zones``, layout analyzers, zone models.

Upstream: ``FitzEngine`` page chars/lines, ``pipeline.stages.page_segment``.

Downstream: ``pipeline.handlers``, ``extract.zone_crop``.
"""

from docmirror.structure.segment.zones import (
    Zone,
    analyze_document_layout,
    analyze_document_layout_parallel,
    analyze_page_layout,
    segment_page_into_zones,
)

__all__ = [
    "Zone",
    "analyze_document_layout",
    "analyze_document_layout_parallel",
    "analyze_page_layout",
    "segment_page_into_zones",
]

# Optional layout helpers (CPA design 12 — formerly core/layout/)
from docmirror.structure.segment.graph_router import GraphRouter  # noqa: F401
from docmirror.structure.segment.layout_model import LayoutDetector  # noqa: F401
