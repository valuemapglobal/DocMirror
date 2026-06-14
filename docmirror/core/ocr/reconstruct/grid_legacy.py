# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

def _group_chars_into_rows(chars: list[dict], y_tolerance: float = 8.0) -> list[tuple[float, list[dict]]]:
    """Group OCR character dicts into rows by y-coordinate proximity."""
    if not chars:
        return []

    sorted_chars = sorted(chars, key=lambda c: c.get("top", 0))

    rows: list[tuple[float, list[dict]]] = []
    current_y = sorted_chars[0].get("top", 0)
    current_row: list[dict] = [sorted_chars[0]]

    for ch in sorted_chars[1:]:
        ch_y = ch.get("top", 0)
        if abs(ch_y - current_y) <= y_tolerance:
            current_row.append(ch)
        else:
            # Sort within-row characters by x position
            current_row.sort(key=lambda c: c.get("x0", 0))
            rows.append((current_y, current_row))
            current_y = ch_y
            current_row = [ch]

    if current_row:
        current_row.sort(key=lambda c: c.get("x0", 0))
        rows.append((current_y, current_row))

    return rows


def _chars_to_text(chars: list[dict]) -> str:
    """Merge a list of character dicts into a single text string."""
    return " ".join(c.get("text", "") for c in chars).strip()


def _cluster_x_positions(x_positions: list[float], gap_multiplier: float = 2.0) -> list[tuple[float, float]]:
    """Detect column boundaries by clustering x-coordinates."""
    if not x_positions:
        return []

    sorted_x = sorted(set(x_positions))
    if len(sorted_x) < 2:
        return [(sorted_x[0], sorted_x[0] + 100)]

    # Compute inter-position gaps
    gaps = [sorted_x[i + 1] - sorted_x[i] for i in range(len(sorted_x) - 1)]
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 10

    # Split into columns at large gaps
    col_starts = [sorted_x[0]]
    for i, gap in enumerate(gaps):
        if gap > median_gap * gap_multiplier:
            col_starts.append(sorted_x[i + 1])

    # Build column boundary intervals (start, end)
    bounds = []
    for i, start in enumerate(col_starts):
        if i + 1 < len(col_starts):
            end = col_starts[i + 1]
        else:
            end = max(x_positions) + 10
        bounds.append((start, end))

    return bounds


def _assign_chars_to_columns(chars: list[dict], col_bounds: list[tuple[float, float]]) -> list[str]:
    """Assign a row's characters to column bins."""
    cols: list[list[dict]] = [[] for _ in col_bounds]

    for ch in chars:
        cx = (ch.get("x0", 0) + ch.get("x1", 0)) / 2
        assigned = False
        for i, (start, end) in enumerate(col_bounds):
            if start <= cx < end:
                cols[i].append(ch)
                assigned = True
                break
        if not assigned and cols:
            # Assign to the nearest column by midpoint distance
            min_dist = float("inf")
            min_idx = 0
            for i, (start, end) in enumerate(col_bounds):
                mid = (start + end) / 2
                dist = abs(cx - mid)
                if dist < min_dist:
                    min_dist = dist
                    min_idx = i
            cols[min_idx].append(ch)

    return [_chars_to_text(col) for col in cols]


def _split_tables_by_y_gap(
    rows_by_y: list[tuple[float, list[dict]]], page_h: float
) -> list[list[tuple[float, list[dict]]]]:
    """Split grouped rows into multiple tables based on vertical gaps."""
    if len(rows_by_y) < 4:
        return [rows_by_y]

    gap_threshold = page_h * 0.05
    tables: list[list[tuple[float, list[dict]]]] = []
    current: list[tuple[float, list[dict]]] = [rows_by_y[0]]

    for i in range(1, len(rows_by_y)):
        if rows_by_y[i][0] - rows_by_y[i - 1][0] > gap_threshold:
            tables.append(current)
            current = []
        current.append(rows_by_y[i])
    tables.append(current)

    return [t for t in tables if len(t) >= 2]


def _reconstruct_table_grid_2d(
    chars: list[dict], hough_lines: list[tuple[float, float]] | None = None
) -> list[list[str]]:
    """Robust 2D Table Grid Reconstruction (Virtual Grid Alignment).

    Replaces 1D x-coordinate clustering with a 2D spatial alignment algorithm.
    It builds a virtual grid by finding strong alignment edges and snapping characters
    to the optimal (row, col) coordinates, handling jagged cell contents and
    misaligned headers.

    Algorithm:
        1. Base Row Clustering: Group chars by y-overlap (IoU).
        2. Base Col Clustering: Group chars by x-overlap (IoU) or Hough lines.
        3. Grid Snapping: Assign each char to a (row_idx, col_idx) bucket.
        4. Output Generation: Build a dense 2D list of strings.
    """
    if not chars:
        return []

    # 1. Base Row Clustering (Robust y-projection)
    # Sort by top coordinate
    sorted_chars = sorted(chars, key=lambda c: c["top"])

    rows_y = []  # list of (min_y, max_y, chars)

    for c in sorted_chars:
        c_min_y, c_max_y = c["top"], c["bottom"]
        matched = False
        # Try to match with existing row (look at last few rows to handle slight overlaps)
        for i in range(len(rows_y) - 1, max(-1, len(rows_y) - 4), -1):
            r_min_y, r_max_y, r_chars = rows_y[i]

            # Calculate vertical IoU or significant overlap
            overlap = max(0, min(c_max_y, r_max_y) - max(c_min_y, r_min_y))
            c_height = c_max_y - c_min_y

            # If overlap is > 40% of character height, it belongs to this row
            if overlap > 0.4 * c_height or (c_min_y >= r_min_y and c_max_y <= r_max_y):
                # Update row boundaries
                rows_y[i] = (min(r_min_y, c_min_y), max(r_max_y, c_max_y), r_chars + [c])
                matched = True
                break

        if not matched:
            rows_y.append((c_min_y, c_max_y, [c]))

    # Sort rows by their physical y-position
    rows_y.sort(key=lambda x: x[0])
    row_chars_list = [r[2] for r in rows_y]

    # 2. Base Col Clustering
    col_bounds = []  # list of (min_x, max_x)

    if hough_lines and len(hough_lines) >= 2:
        col_bounds = hough_lines
    else:
        # Fallback to robust X-clustering using all characters
        x_spans = [(c["x0"], c["x1"]) for c in chars]
        x_spans.sort(key=lambda x: x[0])

        merged_cols = []
        for span in x_spans:
            if not merged_cols:
                merged_cols.append([span[0], span[1]])
                continue

            last_col = merged_cols[-1]
            # If x overlaps or gap is very small (< 10px), merge into same column
            if span[0] <= last_col[1] + 10:
                last_col[1] = max(last_col[1], span[1])
            else:
                merged_cols.append([span[0], span[1]])

        # If we merged everything into 1 column, fallback to K-Means/Gap logic
        if len(merged_cols) < 2:
            all_x0 = [c["x0"] for c in chars]
            # Reuse 1D clustering as a last resort
            col_bounds = _cluster_x_positions(all_x0, gap_multiplier=2.0)
        else:
            col_bounds = [(c[0], c[1]) for c in merged_cols]

    # Ensure at least 1 column
    if not col_bounds:
        col_bounds = [(0, 9999)]

    # 3. Grid Snapping
    num_rows = len(row_chars_list)
    num_cols = len(col_bounds)

    table_grid: list[list[list[dict]]] = [[[] for _ in range(num_cols)] for _ in range(num_rows)]

    for r_idx, r_chars in enumerate(row_chars_list):
        for c in r_chars:
            cx = (c["x0"] + c["x1"]) / 2

            # Find best column index
            best_c_idx = 0
            min_dist = float("inf")

            for c_idx, (start, end) in enumerate(col_bounds):
                if start <= cx <= end:
                    best_c_idx = c_idx
                    break

                # Calculate distance to mid-point if outside
                mid = (start + end) / 2
                dist = abs(cx - mid)
                if dist < min_dist:
                    min_dist = dist
                    best_c_idx = c_idx

            table_grid[r_idx][best_c_idx].append(c)

    # 4. Output Generation (Merge characters in each cell to string)
    final_table = []
    for r_idx in range(num_rows):
        row_str = []
        for c_idx in range(num_cols):
            cell_chars = table_grid[r_idx][c_idx]
            # Sort characters in cell left-to-right
            cell_chars.sort(key=lambda c: c["x0"])
            row_str.append(_chars_to_text(cell_chars))
        final_table.append(row_str)

    return final_table


def _detect_table_lines_hough(img_bgr, page_h: int, page_w: int) -> list[tuple[float, float]] | None:
    """Detect vertical table lines in a scanned image using Hough transform.

    Returns column boundary intervals derived from clustered vertical
    line x-coordinates, or ``None`` if too few lines are found.
    """
    import cv2

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    min_line_len = int(page_h * 0.15)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=3.14159 / 180,
        threshold=80,
        minLineLength=min_line_len,
        maxLineGap=10,
    )
    if lines is None:
        return None

    vertical_x = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if abs(x1 - x2) < 5:
            vertical_x.append((x1 + x2) / 2)

    if len(vertical_x) < 2:
        return None

    vertical_x.sort()
    clusters = [vertical_x[0]]
    for x in vertical_x[1:]:
        if x - clusters[-1] > 10:
            clusters.append(x)
        else:
            clusters[-1] = (clusters[-1] + x) / 2

    if len(clusters) < 2:
        return None

    col_bounds = []
    for i in range(len(clusters) - 1):
        col_bounds.append((clusters[i], clusters[i + 1]))

    col_bounds = [(a, b) for a, b in col_bounds if b - a > 20]

    return col_bounds if len(col_bounds) >= 2 else None


def _probe_best_orientation(img_bgr, ocr_engine=None):
    """Try OCR at 0°/90°/180°/270° on a downscaled image; return best angle.

    Uses a fast, low-resolution probe (~800px max dimension) to determine
    the correct document orientation.  Applies gamma correction only for
    very dark images to avoid washing out orientation signal.

    Returns:
        int: best rotation angle (0, 90, 180, or 270).
    """
    import cv2
    import numpy as np

    if ocr_engine is None:
        return 0

    h, w = img_bgr.shape[:2]
    max_probe = 800
    if max(h, w) > max_probe:
        scale = max_probe / max(h, w)
        small = cv2.resize(img_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        small = img_bgr.copy()

    # Only apply gamma for very dark images — preserve natural signal otherwise
    gray_check = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    if gray_check.mean() < 100:
        gamma = 0.5
        lut = np.array([min(255, int(((i / 255.0) ** gamma) * 255)) for i in range(256)], dtype=np.uint8)
        small = cv2.LUT(small, lut)

    best_angle = 0
    best_score = -1.0

    for angle in [0, 90, 180, 270]:
        if angle == 0:
            probe_img = small
        elif angle == 90:
            probe_img = cv2.rotate(small, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            probe_img = cv2.rotate(small, cv2.ROTATE_180)
        else:
            probe_img = cv2.rotate(small, cv2.ROTATE_90_COUNTERCLOCKWISE)

        try:
            words = ocr_engine.detect_image_words(probe_img)
        except Exception as exc:
            logger.debug(f"operation: suppressed {exc}")
            continue

        if not words:
            continue

        # conf is at index 8
        score = sum(w[8] for w in words if len(w) > 8 and w[8] >= 0.5)
        logger.debug(f"[OCR] Orientation probe {angle}°: score={score:.1f}")

        if score > best_score:
            best_score = score
            best_angle = angle

    if best_angle != 0:
        logger.info(f"[OCR] Auto-orient: best angle = {best_angle}°")

    return best_angle
