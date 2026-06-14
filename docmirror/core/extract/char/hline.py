# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Char strategy: _extract_by_hline_columns."""

from __future__ import annotations

import logging

from docmirror.core.utils.vocabulary import _is_header_row

logger = logging.getLogger(__name__)

def _extract_by_hline_columns(page_plum) -> list[list[str]] | None:
    """Horizontal-line column boundary method.

    For PDFs with horizontal dividers but no vertical lines
    (e.g. China Merchants Bank transaction statements).
    Horizontal-line x-endpoints define column boundaries;
    data rows are clustered by word y-coordinates.

    Trigger conditions: >= 3 horizontal lines, 0 vertical lines.
    """
    lines = page_plum.lines or []
    if not lines:
        return None

    # Classify lines: horizontal vs vertical
    h_lines = [l for l in lines if abs(l["top"] - l["bottom"]) < 1]
    v_lines = [l for l in lines if abs(l["x0"] - l["x1"]) < 1]

    # Trigger: enough horizontal lines, no vertical lines
    if len(h_lines) < 3 or len(v_lines) > 0:
        return None

    # ── Extract column boundaries from horizontal-line x-coordinates ──
    raw_x = sorted(set(round(v, 1) for l in h_lines for v in [l["x0"], l["x1"]]))
    # Merge nearby x values (snap with 10 pt threshold — avoid tiny gaps creating empty columns)
    x_positions = [raw_x[0]]
    for x in raw_x[1:]:
        if x - x_positions[-1] > 10:
            x_positions.append(x)

    if len(x_positions) < 3:
        return None  # Too few columns — unlikely to be a table

    # ── Determine column intervals ──
    col_count = len(x_positions) - 1
    intervals = [(x_positions[i], x_positions[i + 1]) for i in range(col_count)]

    # ── Determine header region (y-range of horizontal lines) ──
    h_y_values = sorted(set(round(l["top"], 1) for l in h_lines))
    # Header sits between the top two lines; data starts from the second line
    if len(h_y_values) < 2:
        return None
    header_top = h_y_values[0]
    data_start_y = h_y_values[1]

    # ── Extract words from the page ──
    try:
        words = page_plum.extract_words(keep_blank_chars=True)
    except Exception as exc:
        logger.debug(f"operation: suppressed {exc}")
        return None
    if not words:
        return None

    # ── Cluster words into rows by y-coordinate ──
    ROW_TOLERANCE = 5  # Words within 5 pt y-distance belong to the same row
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))

    rows_words = []  # list of (y, [words])
    current_y = -999
    current_row = []
    for w in sorted_words:
        if w["top"] - current_y > ROW_TOLERANCE:
            if current_row:
                rows_words.append((current_y, current_row))
            current_y = w["top"]
            current_row = [w]
        else:
            current_row.append(w)
    if current_row:
        rows_words.append((current_y, current_row))

    # ── Keep only header rows (between header_top and data_start_y) + data rows (below) ──
    # Validate with _is_header_row: after cropping, the header interval may
    # contain data rows (e.g. if the first h-line was cropped away)
    header_rows = []
    data_rows = []
    for y, rw in rows_words:
        if header_top - 2 <= y < data_start_y:
            # Vocabulary validation: rows with dates / amounts / long numbers → data, not header
            texts = [w["text"].strip() for w in rw if w["text"].strip()]
            if _is_header_row(texts):
                header_rows.append(rw)
            else:
                data_rows.append(rw)
        elif y >= data_start_y:
            data_rows.append(rw)

    if not data_rows:
        return None

    # ── Assign words to columns ──
    def _words_to_row(row_words):
        cells = [""] * col_count
        for w in sorted(row_words, key=lambda w: w["x0"]):
            wx = w["x0"]
            assigned = False
            for ci, (x0, x1) in enumerate(intervals):
                if x0 - 5 <= wx < x1 + 5:
                    if cells[ci]:
                        cells[ci] += " " + w["text"]
                    else:
                        cells[ci] = w["text"]
                    assigned = True
                    break
            if not assigned and col_count > 0:
                # Words beyond the right boundary → last column
                if wx >= x_positions[-1] - 5:
                    if cells[-1]:
                        cells[-1] += " " + w["text"]
                    else:
                        cells[-1] = w["text"]
        return cells

    # Build header row
    header_cells = [""] * col_count
    for rw in header_rows:
        merged = _words_to_row(rw)
        for ci in range(col_count):
            if merged[ci]:
                if header_cells[ci]:
                    header_cells[ci] += " " + merged[ci]
                else:
                    header_cells[ci] = merged[ci]

    # ── Compute header anchors (crop-immune) ──
    # From all words above data_start_y, find the nearest word centre for
    # each column interval.  Independent of whether header_rows were correctly
    # recognised — completely unaffected by engine cropping.
    pre_data_words = [w for w in words if w["top"] < data_start_y]
    header_anchors = []
    for ci in range(col_count):
        interval_mid = (intervals[ci][0] + intervals[ci][1]) / 2
        if pre_data_words:
            # Find the pre-data word whose x-centre is closest to the interval midpoint
            best_w = min(pre_data_words, key=lambda w: abs((w["x0"] + w.get("x1", w["x0"] + 10)) / 2 - interval_mid))
            anchor = (best_w["x0"] + best_w.get("x1", best_w["x0"] + 10)) / 2
            # Only accept if within half the interval width (prevent mismatch)
            interval_half = (intervals[ci][1] - intervals[ci][0]) / 2
            if abs(anchor - interval_mid) < interval_half:
                header_anchors.append(anchor)
                continue
        # Fallback: use the interval midpoint
        header_anchors.append(interval_mid)

    logger.debug(f"hline-columns: anchors={[f'{a:.1f}' for a in header_anchors]}")

    # ── Data rows: nearest-neighbour anchor assignment ──
    def _words_to_row_nn(row_words):
        cells = [""] * col_count
        for w in sorted(row_words, key=lambda w: w["x0"]):
            w_center = (w["x0"] + w.get("x1", w["x0"] + 5)) / 2
            best_ci = min(range(col_count), key=lambda ci: abs(w_center - header_anchors[ci]))
            if cells[best_ci]:
                cells[best_ci] += " " + w["text"]
            else:
                cells[best_ci] = w["text"]
        return cells

    # Build data rows using nearest-neighbour assignment
    table = [header_cells]
    for rw in data_rows:
        table.append(_words_to_row_nn(rw))

    # Validate: too few data rows or columns → not a valid table
    if len(table) < 2 or col_count < 2:
        return None

    logger.info(f"hline-columns: {len(table) - 1} data rows, {col_count} cols from {len(h_lines)} h-lines")
    return table


