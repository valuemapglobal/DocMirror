# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Zone segment — top-level page → zones entry point.

Purpose: Primary API called by ``page_segment`` to partition a page into
semantic zones, optionally applying cross-page templates.

Main components: ``segment_page_into_zones``.

Upstream: ``pipeline.stages.page_segment``, ``FitzEngine`` page.

Downstream: ``pipeline.handlers``, ``segment.zone_template``.
"""

from __future__ import annotations

import logging

from docmirror.layout.segment.zone_builder import (
    _build_zones_from_extent,
    _column_consensus,
    _isolate_formula_components,
    _legacy_y_band_zones,
    _refine_by_lines,
)
from docmirror.layout.segment.zone_models import Zone

logger = logging.getLogger(__name__)


def segment_page_into_zones(
    page_plum,
    page_idx: int,
    gap_threshold: float = 15.0,
) -> list[Zone]:
    """Spatial partitioning: Column Consensus architecture.

    Primary path: detect table extent by structural column alignment
    (Column Consensus), then derive all zones from the table extent.

    Fallback: legacy Y-band splitting when no table pattern is found.
    """
    chars = page_plum.chars
    rects = page_plum.rects or []
    page_h = page_plum.height
    page_w = page_plum.width

    if not chars:
        return []

    # ── Step 1: Column Consensus on ALL chars (before formula isolation) ──
    # Formula isolation can eat table data characters, breaking column
    # alignment detection.  Run Column Consensus first on the full char set.
    # Competitive strategy: try proven 3pt binning first; if it fails,
    # retry with adaptive binning based on median character height.
    table_extent = _column_consensus(chars, page_w, page_h)
    if table_extent is None:
        char_heights = [
            c.get("bottom", 0) - c.get("top", 0) for c in chars if (c.get("bottom", 0) - c.get("top", 0)) > 0
        ]
        if char_heights:
            sorted_h = sorted(char_heights)
            median_h = sorted_h[len(sorted_h) // 2]
            adaptive_bin = max(2.0, median_h * 0.4)
            # Only retry if adaptive bin differs meaningfully from default 3pt
            if abs(adaptive_bin - 3.0) > 0.5:
                table_extent = _column_consensus(chars, page_w, page_h, y_bin=adaptive_bin)
                if table_extent is not None:
                    logger.debug(
                        f"column_consensus: adaptive y_bin={adaptive_bin:.1f}pt succeeded (median_h={median_h:.1f}pt)"
                    )

    # ── Step 2: Line enhancement (Tier 2) ──
    if table_extent:
        lines = page_plum.lines or []
        table_extent = _refine_by_lines(table_extent, lines, rects)

    # ── Step 2.5: Rect-grid table extent (Tier 1.5 fallback) ──
    # When column consensus fails but the page has dense rect grids (e.g.
    # 东莞银行: 165 rects forming 15 rows × 11 cols), derive table extent
    # from the rect bounding box.
    if not table_extent and len(rects) >= 20:
        x_lefts = sorted(set(round(r["x0"]) for r in rects))
        if len(x_lefts) >= 4:
            # Rects share ≥ 4 distinct left-edge x positions → grid structure
            y_min = min(r["top"] for r in rects)
            y_max = max(r["bottom"] for r in rects)
            if y_max - y_min > 50:  # At least 50pt tall
                table_extent = (y_min, y_max, x_lefts)
                logger.debug(
                    f"segment_page_into_zones: Rect-grid fallback → "
                    f"table extent y={y_min:.0f}-{y_max:.0f} "
                    f"({len(rects)} rects, {len(x_lefts)} x-cols)"
                )

    # ── Step 2.6: Line-grid table extent (Tier 1.5b fallback) ──
    # When rect-grid also fails but the page has a clear line grid (e.g.
    # 交通银行: 644 lines forming 13 rows × 18 cols), derive table extent
    # from the h-line/v-line bounding box.
    if not table_extent:
        lines = page_plum.lines or []
        if len(lines) >= 10:
            h_lines = [l for l in lines if abs(l["top"] - l["bottom"]) < 2]
            v_lines = [l for l in lines if abs(l["x0"] - l["x1"]) < 2]
            h_ys = sorted(set(round(l["top"]) for l in h_lines))
            v_xs = sorted(set(round(l["x0"]) for l in v_lines))
            if len(h_ys) >= 5 and len(v_xs) >= 4:
                y_min = min(h_ys)
                y_max = max(h_ys)
                if y_max - y_min > 50:
                    table_extent = (y_min, y_max, v_xs)
                    logger.debug(
                        f"segment_page_into_zones: Line-grid fallback → "
                        f"table extent y={y_min}-{y_max} "
                        f"({len(h_lines)} h-lines, {len(v_lines)} v-lines, "
                        f"{len(h_ys)} rows × {len(v_xs)} cols)"
                    )

    # ── Step 3: Build zones ──
    if table_extent:
        zones = _build_zones_from_extent(chars, rects, table_extent, page_w, page_h, page_idx)
        logger.debug(
            f"segment_page_into_zones: Column Consensus path → "
            f"{len(zones)} zones (table y={table_extent[0]:.0f}-{table_extent[1]:.0f})"
        )
    else:
        # Fallback: formula isolation + legacy Y-band splitting
        remaining_chars, formula_zones = _isolate_formula_components(chars, page_w, page_h)
        if remaining_chars:
            zones = _legacy_y_band_zones(remaining_chars, rects, page_w, page_h, page_idx, gap_threshold)
        else:
            zones = []
        zones.extend(formula_zones)
        logger.debug(f"segment_page_into_zones: Legacy fallback → {len(zones)} zones")

    # ── Step 4: GraphRouter reading order (preserved) ──
    from .graph_router import GraphRouter

    router = GraphRouter(page_width=page_w, page_height=page_h)
    causal_zones = router.build_flow(zones)

    return causal_zones
