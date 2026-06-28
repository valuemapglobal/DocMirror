# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Table projection — x-projection column boundary detection.

Purpose: Fallback column detection via char x-projection when line-based and
char-strategy paths fail.

Main components: ``detect_column_boundaries``, ``detect_table_by_projection``,
``projection_fallback``.

Upstream: Char streams in table zones.

Downstream: ``pipeline.handlers.fallback_table``, ``extract.signal_processor``.
"""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. X-axis projection histogram calculation
# ═══════════════════════════════════════════════════════════════════════════════


def compute_x_projection(chars: list[dict], page_w: float, bin_size: float = 2.0) -> list[int]:
    """T-11: Compute X-axis projection histogram.

    Args:
        chars: list of characters
        page_w: page width
        bin_size: histogram bin size (px), default 2px

    Returns:
        Projection histogram array, each element represents the character count at that x position
    """
    if not chars or page_w <= 0:
        logger.debug("[projection] compute_x_projection: empty input or invalid page_w")
        return []

    # Initialize histogram
    num_bins = int(page_w / bin_size) + 1
    histogram = [0] * num_bins

    # Populate histogram
    for c in chars:
        x0 = c.get("x0", 0)
        x1 = c.get("x1", x0)

        # Bin range covered by the character
        bin_start = int(x0 / bin_size)
        bin_end = int(x1 / bin_size)

        # Increment within range
        for bin_idx in range(bin_start, min(bin_end + 1, num_bins)):
            histogram[bin_idx] += 1

    return histogram


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Column boundary detection
# ═══════════════════════════════════════════════════════════════════════════════


def detect_column_boundaries(
    projection: list[int], min_valley_depth: float = 0.3, min_column_width: float = 20.0, bin_size: float = 2.0
) -> list[int]:
    """T-11: Detect column boundaries from projection histogram.

    Args:
        projection: X-axis projection histogram
        min_valley_depth: Minimum valley depth (relative to peak ratio)
        min_column_width: Minimum column width (px)
        bin_size: Histogram bin size (px)

    Returns:
        Column boundary position list (px coordinates)
    """
    if not projection or len(projection) < 10:
        logger.debug(
            f"[projection] detect_column_boundaries: projection too short ({len(projection) if projection else 0} bins)"
        )
        return []

    # Step 1: Smooth histogram (moving average, window=5)
    smoothed = _smooth_projection(projection, window_size=5)

    # Step 2: Find global maximum
    max_val = max(smoothed)
    if max_val == 0:
        logger.debug("[projection] detect_column_boundaries: max value is 0 (empty projection)")
        return []

    # Step 3: Detect local minima (valleys)
    valleys = []
    for i in range(1, len(smoothed) - 1):
        if smoothed[i] < smoothed[i - 1] and smoothed[i] < smoothed[i + 1]:
            # Check valley depth
            depth = 1.0 - (smoothed[i] / max_val)
            if depth >= min_valley_depth:
                valleys.append(i)

    # Step 4: Filter: column width < min_column_width
    min_bin_width = int(min_column_width / bin_size)
    filtered_valleys = [valleys[0]] if valleys else []

    for i in range(1, len(valleys)):
        if valleys[i] - filtered_valleys[-1] >= min_bin_width:
            filtered_valleys.append(valleys[i])

    # Step 5: Convert to px coordinates
    boundaries = [v * bin_size for v in filtered_valleys]

    logger.debug(
        f"[Projection] Detected {len(boundaries)} column boundaries (valley depth threshold={min_valley_depth})"
    )

    return boundaries


def _smooth_projection(projection: list[int], window_size: int = 5) -> list[float]:
    """Smooth projection histogram (moving average)."""
    if not projection:
        return []

    smoothed = []
    half_w = window_size // 2

    for i in range(len(projection)):
        # Window range
        start = max(0, i - half_w)
        end = min(len(projection), i + half_w + 1)

        # Compute mean
        window = projection[start:end]
        avg = sum(window) / len(window)
        smoothed.append(avg)

    return smoothed


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Assign characters to columns
# ═══════════════════════════════════════════════════════════════════════════════


def assign_chars_to_columns(chars: list[dict], column_boundaries: list[float], page_w: float) -> dict[int, list[dict]]:
    """T-11: Assign characters to corresponding columns.

    Args:
        chars: list of characters
        column_boundaries: Column boundary position list (px)
        page_w: page width

    Returns:
        {col_index: [chars]}
    """
    if not chars or not column_boundaries:
        return {}

    # Add start and end boundaries
    boundaries = [0.0] + sorted(column_boundaries) + [page_w]

    # Assign characters
    columns: dict[int, list[dict]] = defaultdict(list)

    for c in chars:
        x_mid = (c.get("x0", 0) + c.get("x1", 0)) / 2

        # Find the column interval containing x_mid
        for col_idx in range(len(boundaries) - 1):
            if boundaries[col_idx] <= x_mid < boundaries[col_idx + 1]:
                columns[col_idx].append(c)
                break

    logger.debug(f"[Projection] Assigned chars to {len(columns)} columns")
    return dict(columns)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Unified entry: table detection
# ═══════════════════════════════════════════════════════════════════════════════


def detect_table_by_projection(
    chars: list[dict], page_w: float, page_h: float, min_rows: int = 3, min_cols: int = 2
) -> tuple | None:
    """T-11: Detect table structure using projection histogram.

    Algorithm:
      1. Group characters by y (row detection)
      2. Compute X-projection for each group
      3. Detect column boundaries
      4. Validate: rows >= min_rows, cols >= min_cols
      5. Return table boundaries and column positions

    Args:
        chars: list of characters
        page_w: page width
        page_h: Page height
        min_rows: Minimum row count
        min_cols: Minimum column count

    Returns:
        (y_top, y_bottom, [col_x_positions]) or None
    """
    if not chars or page_w <= 0 or page_h <= 0:
        return None

    # Step 1: Group characters by y
    y_bin = 3.0
    y_groups: dict[int, list] = defaultdict(list)

    for c in chars:
        y_mid = (c.get("top", 0) + c.get("bottom", 0)) / 2
        y_key = round(y_mid / y_bin) * y_bin
        y_groups[y_key].append(c)

    if len(y_groups) < min_rows:
        return None

    # Step 2: Compute X projection for all characters
    all_x_projection = compute_x_projection(chars, page_w, bin_size=2.0)

    if not all_x_projection:
        return None

    # Step 3: Detect column boundaries
    column_boundaries = detect_column_boundaries(
        all_x_projection, min_valley_depth=0.3, min_column_width=20.0, bin_size=2.0
    )

    if len(column_boundaries) < min_cols - 1:  # n columns need n-1 boundaries
        return None

    # Step 4: Compute column center positions
    boundaries = [0.0] + sorted(column_boundaries) + [page_w]
    col_positions = []

    for i in range(len(boundaries) - 1):
        col_center = (boundaries[i] + boundaries[i + 1]) / 2
        col_positions.append(col_center)

    if len(col_positions) < min_cols:
        return None

    # Step 5: Verify row consistency (check if multiple rows have same column count)
    row_cell_counts = []

    for y_key in sorted(y_groups.keys()):
        row_chars = y_groups[y_key]
        if len(row_chars) < 2:
            continue

        # Assign characters to columns
        row_columns = assign_chars_to_columns(row_chars, column_boundaries, page_w)

        # Count columns with characters
        non_empty_cols = sum(1 for cols in row_columns.values() if cols)
        if non_empty_cols >= min_cols:
            row_cell_counts.append(non_empty_cols)

    # Check if enough rows have consistent column counts
    if len(row_cell_counts) < min_rows:
        return None

    # Verify column count consistency (allow +/-1 error)
    if max(row_cell_counts) - min(row_cell_counts) > 1:
        logger.debug(f"[Projection] Column count inconsistent: {row_cell_counts}")
        return None

    # Step 6: Compute table boundaries
    y_top = min(y_groups.keys())
    y_bottom = max(y_groups.keys())

    logger.info(
        f"[Projection] Table detected: {len(row_cell_counts)} rows × "
        f"{len(col_positions)} cols (y={y_top:.0f}-{y_bottom:.0f})"
    )

    return (y_top, y_bottom, col_positions)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: integration with Column Consensus
# ═══════════════════════════════════════════════════════════════════════════════


def projection_fallback(
    chars: list[dict], page_w: float, page_h: float, min_rows: int = 3, min_cols: int = 2
) -> tuple | None:
    """T-11: Projection histogram fallback entry point.

    Called when gap-based clustering fails.

    Returns:
        (y_top, y_bottom, [col_x_positions]) or None
    """
    try:
        return detect_table_by_projection(chars, page_w, page_h, min_rows, min_cols)
    except Exception as e:
        logger.warning(f"[Projection] Fallback failed: {e}")
        return None
