# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Zone models — dataclasses for layout regions and zone templates.

Purpose: Defines ``Zone``, ``ContentRegion``, ``ALPageLayout``, and
``ZoneTemplate`` used throughout segmentation and template replay.

Main components: ``Zone``, ``ContentRegion``, ``ALPageLayout``, ``ZoneTemplate``.

Upstream: Segmentation algorithms (internal).

Downstream: ``segment.zone_segment``, ``extract.template_injector``,
``pipeline.context``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

@dataclass
class ContentRegion:
    """A content region on the page."""

    type: str  # "text" | "table" | "image"
    bbox: tuple[float, float, float, float]
    page: int
    text_preview: str = ""
    area: float = 0.0

    def __post_init__(self):
        x0, y0, x1, y1 = self.bbox
        self.area = max(0, (x1 - x0) * (y1 - y0))


@dataclass
class ALPageLayout:
    """Single page layout analysis result."""

    page_index: int
    width: float
    height: float
    regions: list[ContentRegion] = field(default_factory=list)
    has_table: bool = False
    table_count: int = 0
    image_count: int = 0
    text_region_count: int = 0
    is_continuation: bool = False
    is_scanned: bool = False
    header_text: str = ""
    footer_text: str = ""



@dataclass(slots=True)
class Zone:
    """A large zone on the page (3~5 zones/page)."""

    type: str  # "title" | "summary" | "data_table" | "footer" | "formula" | "unknown"
    bbox: tuple[float, float, float, float]
    page: int = 0
    chars: list = field(default_factory=list)
    rects: list = field(default_factory=list)
    text: str = ""
    confidence: float = 1.0  # Model Detection Confidence, rule method default 1.0



@dataclass
class ZoneTemplate:
    """Cached zone layout template from a reference page.

    Stores normalized (0-1) bbox ratios so the template can be applied
    to pages of any DPI/dimension.
    """

    zones: list  # List of (zone_type, bbox_ratio, confidence)
    # bbox_ratio = (x0/page_w, y0/page_h, x1/page_w, y1/page_h)
    source_page: int = 0
    zone_count: int = 0


