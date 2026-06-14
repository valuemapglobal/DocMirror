# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.core.segment.zones import (
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
from docmirror.core.segment.graph_router import GraphRouter  # noqa: F401
from docmirror.core.segment.layout_model import LayoutDetector  # noqa: F401
