# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Profile-driven page segmentation for Core Extract (EPO)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from docmirror.core.layout.layout_analysis import Zone, segment_page_into_zones

if TYPE_CHECKING:
    from docmirror.models.entities.extraction_profile import ExtractionProfile

logger = logging.getLogger(__name__)


def _chars_in_bbox(chars: list, bbox: tuple[float, float, float, float]) -> list:
    x0, y0, x1, y1 = bbox
    return [c for c in chars if c.get("x0", 0) >= x0 - 1 and c.get("x1", 0) <= x1 + 1 and c.get("top", 0) >= y0 - 1 and c.get("bottom", 0) <= y1 + 1]


def _find_header_anchor_y(chars: list, expected_headers: list[str]) -> float | None:
    """Locate y of the column-header row; None if continuation page (no header band)."""
    if not chars or not expected_headers:
        return None
    from collections import defaultdict

    lines: dict[float, list] = defaultdict(list)
    for c in chars:
        y = round(float(c.get("top", 0)), 0)
        lines[y].append(c)

    best_y: float | None = None
    best_hits = 0
    for y in sorted(lines.keys()):
        row_chars = sorted(lines[y], key=lambda c: c.get("x0", 0))
        line_text = "".join(c.get("text", "") for c in row_chars)
        hits = sum(1 for h in expected_headers if h in line_text)
        if hits > best_hits:
            best_hits = hits
            best_y = y
    if best_hits >= max(3, len(expected_headers) // 2):
        return best_y
    return None


def _segment_full_page_table(page_plum, page_idx: int, profile: ExtractionProfile) -> list[Zone]:
    """Use full page (or sidebar-trimmed width) as data_table — avoids y-crop row loss."""
    page_w = page_plum.width
    page_h = page_plum.height
    chars = page_plum.chars or []
    x_right = profile.table_x_right(page_w)

    expected = list(profile.expected_header_columns or [])
    header_y = 0.0
    anchor_y = _find_header_anchor_y(chars, expected)
    if anchor_y is not None:
        header_y = max(0.0, anchor_y - 2.0)
    elif chars:
        top_band = [c for c in chars if c.get("top", 0) < min(180, page_h * 0.15)]
        if top_band:
            row_ys = sorted(set(round(c["top"] / 5) * 5 for c in top_band))
            if len(row_ys) >= 2:
                gap = row_ys[-1] - row_ys[-2]
                if gap > 25:
                    header_y = row_ys[-1] - 5

    table_bbox = (0.0, header_y, x_right, page_h)
    table_chars = _chars_in_bbox(chars, table_bbox)
    zones: list[Zone] = []

    if header_y > 40:
        title_chars = [c for c in chars if c.get("top", 0) < header_y]
        title_text = " ".join(c.get("text", "") for c in sorted(title_chars, key=lambda c: (c.get("top", 0), c.get("x0", 0))))
        zones.append(
            Zone(
                type="title",
                bbox=(0.0, 0.0, page_w, header_y),
                page=page_idx,
                chars=title_chars,
                text=title_text.strip(),
            )
        )

    zones.append(
        Zone(
            type="data_table",
            bbox=table_bbox,
            page=page_idx,
            chars=table_chars,
            rects=page_plum.rects or [],
            text="",
        )
    )
    logger.debug(
        "[Segmentation] full_page_table page=%d bbox=%s chars=%d",
        page_idx,
        tuple(round(v, 1) for v in table_bbox),
        len(table_chars),
    )
    return zones


def _expand_zone_y_margin(zones: list[Zone], margin_pt: float, page_h: float) -> list[Zone]:
    if margin_pt <= 0:
        return zones
    out: list[Zone] = []
    for z in zones:
        if z.type != "data_table":
            out.append(z)
            continue
        x0, y0, x1, y1 = z.bbox
        new_bbox = (x0, max(0, y0 - margin_pt), x1, min(page_h, y1 + margin_pt))
        out.append(
            Zone(
                type=z.type,
                bbox=new_bbox,
                page=z.page,
                chars=z.chars,
                rects=z.rects,
                text=z.text,
                confidence=z.confidence,
            )
        )
    return out


def segment_page_for_extraction(
    page_plum,
    page_idx: int,
    profile: ExtractionProfile | None = None,
) -> list[Zone]:
    """Segment page using profile-driven strategy."""
    if profile and profile.is_full_page_table():
        return _segment_full_page_table(page_plum, page_idx, profile)

    zones = segment_page_into_zones(page_plum, page_idx)
    if profile and profile.zone_y_margin_pt > 0:
        zones = _expand_zone_y_margin(zones, profile.zone_y_margin_pt, page_plum.height)
    return zones
