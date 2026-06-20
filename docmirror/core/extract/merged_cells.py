# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Merged cells detector — identifies colspan/rowspan from char geometry.

Purpose: Detects merged cell regions in extracted grids so structure fix
stages can expand or split cells correctly.

Main components: ``detect_merged_cells``.

Upstream: Char-assigned table grids.

Downstream: ``table.table_structure_fix``, ``table.pipeline.stage_structure``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def detect_merged_cells(
    page_plum,
    table_zone_bbox: tuple[float, float, float, float] | None = None,
) -> list[dict]:
    """P3-2: detect merged cells in a pdfplumber table.

    Uses pdfplumber's ``find_tables()`` API to get cell bounding boxes,
    then compares actual cell bboxes against an even grid to detect
    colspan / rowspan.

    Args:
        page_plum: pdfplumber page object.
        table_zone_bbox: Optional table-zone crop box.

    Returns:
        List of merged cells:
        ``[{"row": r, "col": c, "rowspan": rs, "colspan": cs}, ...]``
        Returns an empty list when none are detected.
    """
    try:
        work_page = page_plum
        if table_zone_bbox:
            try:
                x0, y0, x1, y1 = table_zone_bbox
                work_page = page_plum.crop((0, y0, page_plum.width, y1))
            except Exception as exc:
                logger.debug(f"operation: suppressed {exc}")

        tables = work_page.find_tables()
        if not tables or not tables[0].cells:
            return []

        cells = tables[0].cells  # List of (x0, y0, x1, y1)
        if len(cells) < 4:
            return []

        # Collect all unique x and y boundaries
        x_coords = sorted(set(round(c[0], 1) for c in cells) | set(round(c[2], 1) for c in cells))
        y_coords = sorted(set(round(c[1], 1) for c in cells) | set(round(c[3], 1) for c in cells))

        if len(x_coords) < 2 or len(y_coords) < 2:
            return []

        # Create grid row/column index mapping
        def _find_nearest_index(val, coords):
            best_idx = 0
            best_dist = abs(val - coords[0])
            for i, c in enumerate(coords[1:], 1):
                d = abs(val - c)
                if d < best_dist:
                    best_dist = d
                    best_idx = i
            return best_idx

        merged = []
        for cell_bbox in cells:
            cx0, cy0, cx1, cy1 = [round(v, 1) for v in cell_bbox]

            col_start = _find_nearest_index(cx0, x_coords)
            col_end = _find_nearest_index(cx1, x_coords)
            row_start = _find_nearest_index(cy0, y_coords)
            row_end = _find_nearest_index(cy1, y_coords)

            colspan = max(1, col_end - col_start)
            rowspan = max(1, row_end - row_start)

            if colspan > 1 or rowspan > 1:
                merged.append(
                    {
                        "row": row_start,
                        "col": col_start,
                        "rowspan": rowspan,
                        "colspan": colspan,
                    }
                )

        if merged:
            logger.debug(f"detected {len(merged)} merged cells")

        return merged

    except Exception as e:
        logger.debug(f"merged cell detection failed: {e}")
        return []
