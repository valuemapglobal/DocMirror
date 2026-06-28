# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""XY-Cut recursive projection column detector.

Phase 1 of the DFG engine: detects column layouts on document pages using
horizontal projection histograms. The algorithm is document-agnostic — it works
on any page with rectangular blocks.

Algorithm (XY-Cut):
    1. Build horizontal projection profile (sum of block overlap at each x)
    2. Find zero-runs (gaps) wider than min_gap_width
    3. Split blocks into columns at gaps
    4. Recursively check sub-columns within each column

Design: ADR-M13 — geometry is a universal language. One algorithm for all document types.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MIN_GAP_WIDTH = 15  # points — minimum gap width to consider a column break
DEFAULT_MIN_COLUMN_WIDTH = 60  # points — minimum column width to check for sub-columns
DEFAULT_MIN_BLOCK_COUNT_FOR_COLUMNS = 4  # minimum blocks on a page to attempt column detection


@dataclass
class ColumnAssignment:
    """Result of column detection for a page."""
    page_number: int = 0
    columns: list[list[int]] = field(default_factory=list)  # list of block index groups per column
    gap_positions: list[float] = field(default_factory=list)  # x positions of detected gaps
    confidence: float = 1.0
    degraded: bool = False


@dataclass
class ColumnLayout:
    """Full column detection result for a document."""
    pages: dict[int, ColumnAssignment] = field(default_factory=dict)  # page_number → assignment


def detect_columns(
    blocks: list[dict[str, Any]],
    page_width: float,
    page_height: float,
    *,
    min_gap_width: float = DEFAULT_MIN_GAP_WIDTH,
    min_column_width: float = DEFAULT_MIN_COLUMN_WIDTH,
    min_block_count: int = DEFAULT_MIN_BLOCK_COUNT_FOR_COLUMNS,
) -> ColumnAssignment:
    """Detect columns on a single page using XY-Cut recursive projection.

    Args:
        blocks: List of block dicts, each with at least ``bbox`` key [x0, y0, x1, y1].
        page_width: Page width in points.
        page_height: Page height in points.
        min_gap_width: Minimum gap width in points to consider a column break.
        min_column_width: Minimum column width to recursively check for sub-columns.
        min_block_count: Minimum number of blocks to attempt column detection.

    Returns:
        ColumnAssignment with columns (groups of block indices) and gap positions.
    """
    if len(blocks) < min_block_count:
        return ColumnAssignment(columns=[list(range(len(blocks)))], confidence=1.0)

    # ── Step 1: Build horizontal projection profile ──
    # Resolution: 1 unit per point, clipped to page width
    width_int = max(1, int(page_width))
    x_profile = [0] * width_int

    for blk_idx, block in enumerate(blocks):
        bbox = block.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        x0 = max(0, int(bbox[0]))
        x1 = min(width_int - 1, int(bbox[2]))
        for x in range(x0, x1 + 1):
            if 0 <= x < len(x_profile):
                x_profile[x] = 1

    # ── Step 2: Find zero-runs (empty vertical stripes) ──
    gaps: list[tuple[int, int]] = []
    in_gap = False
    gap_start = 0

    for x in range(width_int):
        if x_profile[x] == 0:
            if not in_gap:
                gap_start = x
                in_gap = True
        else:
            if in_gap:
                gap_width = x - gap_start
                if gap_width >= min_gap_width:
                    gaps.append((gap_start, x))
                in_gap = False

    # Handle trailing gap
    if in_gap:
        gap_width = width_int - gap_start
        if gap_width >= min_gap_width:
            gaps.append((gap_start, width_int))

    # ── Step 3: Split blocks into columns at gap midpoints ──
    if not gaps:
        return ColumnAssignment(columns=[list(range(len(blocks)))], confidence=1.0)

    # Compute gap midpoints as column dividers
    gap_midpoints = [(g[0] + g[1]) / 2.0 for g in gaps]

    # Build column boundaries
    boundaries = [0.0] + gap_midpoints + [page_width]
    num_columns = len(gaps) + 1

    columns: list[list[int]] = [[] for _ in range(num_columns)]
    for blk_idx, block in enumerate(blocks):
        bbox = block.get("bbox")
        if not bbox or len(bbox) < 4:
            columns[0].append(blk_idx)
            continue

        # Assign block to column based on its horizontal center
        center_x = (bbox[0] + bbox[2]) / 2.0

        col_idx = 0
        for i in range(num_columns):
            if center_x >= boundaries[i] and center_x < boundaries[i + 1]:
                col_idx = i
                break
        else:
            # If center_x at far right edge
            col_idx = num_columns - 1

        columns[col_idx].append(blk_idx)

    # ── Step 4: Recursively check for sub-columns ──
    final_columns: list[list[int]] = []
    for col_blk_indices in columns:
        if len(col_blk_indices) < min_block_count:
            final_columns.append(col_blk_indices)
            continue

        # Compute column width
        col_blocks = [blocks[i] for i in col_blk_indices]
        col_x0 = min((blocks[i].get("bbox") or [0])[0] for i in col_blk_indices)
        col_x1 = max((blocks[i].get("bbox") or [page_width])[2] for i in col_blk_indices)
        col_width = col_x1 - col_x0

        # Recursion guard: don't recurse if column width is nearly the same as page width
        if col_width > min_column_width and col_width < page_width * 0.95:
            # Use a higher min_gap_width for sub-column detection to prevent infinite recursion
            sub_min_gap = max(min_gap_width * 2, col_width * 0.15)
            if sub_min_gap < col_width * 0.8:
                sub_assignment = detect_columns(
                    col_blocks, col_width, page_height,
                    min_gap_width=sub_min_gap,
                    min_column_width=min_column_width,
                    min_block_count=min_block_count,
                )
                # Map sub-column indices back to original block indices
            for sub_col in sub_assignment.columns:
                final_columns.append([col_blk_indices[s] for s in sub_col])
        else:
            final_columns.append(col_blk_indices)

    # ── Compute confidence ──
    # Higher confidence when blocks are well-distributed across columns
    if len(final_columns) <= 1:
        confidence = 0.5
        degraded = True
    else:
        col_sizes = [len(c) for c in final_columns]
        if max(col_sizes) > 0 and min(col_sizes) / max(col_sizes) > 0.1:
            confidence = 0.95
            degraded = False
        else:
            confidence = 0.7
            degraded = max(col_sizes) > 3 * (min(col_sizes) or 1)

    return ColumnAssignment(
        columns=final_columns,
        gap_positions=gap_midpoints,
        confidence=confidence,
        degraded=degraded,
    )


def detect_columns_from_pages(
    pages: list[dict[str, Any]],
    *,
    min_gap_width: float = DEFAULT_MIN_GAP_WIDTH,
    min_column_width: float = DEFAULT_MIN_COLUMN_WIDTH,
    min_block_count: int = DEFAULT_MIN_BLOCK_COUNT_FOR_COLUMNS,
) -> ColumnLayout:
    """Detect columns across all pages of a document.

    Args:
        pages: List of page dicts with ``page_number``, ``blocks`` (or ``texts``),
               ``width``, ``height`` keys.
        min_gap_width: Minimum gap width in points.
        min_column_width: Minimum column width.
        min_block_count: Minimum blocks to attempt detection.

    Returns:
        ColumnLayout mapping page_number → ColumnAssignment.
    """
    layout = ColumnLayout()

    for page in pages:
        page_num = int(page.get("page_number") or 0)
        page_width = float(page.get("width") or page.get("page_width") or 0)
        page_height = float(page.get("height") or page.get("page_height") or 0)

        if page_width <= 0 or page_height <= 0:
            logger.debug("Column detection: skipping page %d (no dimensions)", page_num)
            continue

        # Collect blocks from this page — prefer blocks, fall back to texts
        blocks = page.get("blocks") or page.get("texts") or []
        if not blocks:
            # Try to build block list from individual text items
            texts = page.get("texts") or []
            if texts:
                blocks = texts

        if not blocks:
            layout.pages[page_num] = ColumnAssignment(columns=[], confidence=1.0)
            continue

        assignment = detect_columns(
            blocks,
            page_width,
            page_height,
            min_gap_width=min_gap_width,
            min_column_width=min_column_width,
            min_block_count=min_block_count,
        )
        assignment.page_number = page_num
        layout.pages[page_num] = assignment

    return layout


__all__ = [
    "ColumnAssignment",
    "ColumnLayout",
    "DEFAULT_MIN_BLOCK_COUNT_FOR_COLUMNS",
    "DEFAULT_MIN_COLUMN_WIDTH",
    "DEFAULT_MIN_GAP_WIDTH",
    "detect_columns",
    "detect_columns_from_pages",
]
