# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Extract utilities — shared char grouping and column assignment helpers.

Purpose: Adaptive row tolerance grouping, x-clustering, and char-to-text
conversion reused across char strategies.

Main components: ``_group_chars_into_rows``, ``_cluster_x_positions``,
``_assign_chars_to_columns``.

Upstream: Raw fitz char lists.

Downstream: All ``extract.char.*`` and ``extract.signal_processor``.
"""

from __future__ import annotations

import bisect
import logging

logger = logging.getLogger(__name__)


# ── Shared utility functions ──


def _adaptive_row_tolerance(chars: list[dict]) -> float:
    """F-1: Calculate adaptive y-tolerance for row grouping.

    Based on the median character height, dynamically adjusts the tolerance
    to prevent:
      - Small font-size PDFs: fixed 3 pt tolerance merging multiple lines.
      - Large font-size PDFs: 3 pt tolerance splitting same-row characters.

    Returns:
        Adaptive tolerance value (typically 1.5–5.0 pt).
    """
    if not chars or len(chars) < 5:
        return 3.0

    heights = [
        c["bottom"] - c["top"] for c in chars if c.get("bottom", 0) > c.get("top", 0) and c["bottom"] - c["top"] < 30
    ]
    if not heights:
        return 3.0

    heights.sort()
    median_h = heights[len(heights) // 2]
    # Tolerance = median character height × 0.6, clamped to [1.5, 5.0]
    tol = max(1.5, min(5.0, median_h * 0.6))
    return tol


def _refine_dense_rows(table, col_boundaries=None, raw_chars=None):
    import re as _re

    DATE = _re.compile(r"\d{4}-\d{2}-\d{2}")
    AMT = _re.compile(r"[\d,]+\.\d{2}")
    mod = False
    res = [list(r) for r in table]
    for ri in range(len(res)):
        row = res[ri]
        # Count total values across all cells in this row
        all_dates = []
        all_amts = []
        for cell in row:
            all_dates.extend(DATE.findall(cell))
            all_amts.extend(AMT.findall(cell))
        total_dates = len(all_dates)
        total_amts = len(all_amts)

        # If too many values for this row, try evenly distributing them
        if total_dates >= len(row) or total_amts >= len(row):
            # Rebuild row by evenly distributing dates and amounts
            new_row = [""] * len(row)
            # Distribute dates evenly across all columns
            if total_dates >= 1:
                dates_per_col = max(1, total_dates // len(row))
                di = 0
                for ci in range(min(len(row), total_dates)):
                    for _ in range(min(dates_per_col, total_dates - di)):
                        if di < len(all_dates):
                            new_row[ci] += all_dates[di] + " "
                            di += 1
                    new_row[ci] = new_row[ci].strip()
            # Distribute amounts evenly
            if total_amts >= 1:
                amts_per_col = max(1, total_amts // len(row))
                ai = 0
                for ci in range(min(len(row), total_amts)):
                    for _ in range(min(amts_per_col, total_amts - ai)):
                        if ai < len(all_amts):
                            if new_row[ci]:
                                new_row[ci] += f" {all_amts[ai]}"
                            else:
                                new_row[ci] = all_amts[ai]
                            ai += 1
            # Fill remaining content from original cells
            for ci in range(len(row)):
                if not new_row[ci].strip():
                    new_row[ci] = row[ci]
            # Apply if the new row has at least as many filled columns as the original
            # (the values are more evenly distributed, even if some cells become empty)
            orig_filled = sum(1 for c in row if c.strip())
            new_filled = sum(1 for c in new_row if c.strip())
            if new_filled >= orig_filled or total_dates >= len(row) * 2:
                res[ri] = new_row
                mod = True
            continue

        if not col_boundaries or not raw_chars:
            continue
        # Per-column fusion fix (original logic)
        for ci in range(len(row) - 1):
            cell = row[ci]
            if len(cell) < 12:
                continue
            dates = DATE.findall(cell)
            amts = AMT.findall(cell)
            if len(dates) <= 1 and len(amts) <= 1:
                continue
            tc = ci + 1
            sc = 0
            tmp = cell
            for dv in reversed(dates):
                t = tc + sc
                if t >= len(row):
                    break
                if not row[t].strip() and dv in tmp:
                    row[t] = dv
                    tmp = tmp.replace(dv, "", 1)
                    sc += 1
            for av in reversed(amts):
                t = tc + sc
                if t >= len(row):
                    break
                if not row[t].strip() and av in tmp:
                    row[t] = av
                    tmp = tmp.replace(av, "", 1)
                    sc += 1
            if sc > 0:
                row[ci] = tmp.strip()
                mod = True
        for ci in range(len(row)):
            row[ci] = row[ci].strip()
    return res if mod else None


def _group_chars_into_rows(chars: list[dict], y_tolerance: float = 3.0) -> list[tuple[float, list[dict]]]:
    """Group characters into rows by y-coordinate proximity.

    F-1 enhancement: when ``y_tolerance <= 0``, automatically uses
    ``_adaptive_row_tolerance``.
    """
    if not chars:
        return []

    # F-1: adaptive tolerance
    if y_tolerance <= 0:
        y_tolerance = _adaptive_row_tolerance(chars)

    sorted_chars = sorted(chars, key=lambda c: c["top"])
    rows: list[tuple[float, list[dict]]] = []
    current_row: list[dict] = [sorted_chars[0]]
    current_y = sorted_chars[0]["top"]

    for c in sorted_chars[1:]:
        if abs(c["top"] - current_y) <= y_tolerance:
            current_row.append(c)
        else:
            y_mid = sum(ch["top"] for ch in current_row) / len(current_row)
            rows.append((y_mid, sorted(current_row, key=lambda x: x["x0"])))
            current_row = [c]
            current_y = c["top"]

    if current_row:
        y_mid = sum(ch["top"] for ch in current_row) / len(current_row)
        rows.append((y_mid, sorted(current_row, key=lambda x: x["x0"])))

    return rows


def _cluster_x_positions(
    x_coords: list[float], gap_multiplier: float = 2.0, min_col_width: float = 10.0
) -> list[tuple[float, float]]:
    """X-coordinate clustering: find column boundaries.

    Optimisation 3: uses an IQR-inspired adaptive threshold (natural-break)
    instead of ``median × multiplier``, making it more robust for narrow
    inter-column gaps.  Falls back to ``median × multiplier`` when there
    are too few gap samples (< 4).
    """
    if not x_coords:
        return []

    sorted_x = sorted(set(round(x, 1) for x in x_coords))
    if len(sorted_x) < 2:
        return [(sorted_x[0], sorted_x[0] + 50)]

    gaps = [sorted_x[i + 1] - sorted_x[i] for i in range(len(sorted_x) - 1)]
    non_zero_gaps = sorted(g for g in gaps if g > 0.5)

    if not non_zero_gaps:
        return [(sorted_x[0], sorted_x[-1])]

    # ── Adaptive threshold (natural break) ──
    # Column gaps typically follow a bimodal distribution:
    #   small gaps = intra-column character spacing
    #   large gaps = inter-column spacing
    # Find the largest jump in the sorted gaps to set the threshold
    median_gap = non_zero_gaps[len(non_zero_gaps) // 2]

    if len(non_zero_gaps) >= 4:
        # Find the largest adjacent jump in sorted gaps
        max_jump = 0
        jump_idx = -1
        for j in range(len(non_zero_gaps) - 1):
            jump = non_zero_gaps[j + 1] - non_zero_gaps[j]
            if jump > max_jump:
                max_jump = jump
                jump_idx = j

        if max_jump > median_gap * 2 and jump_idx >= 0:
            # Clear bimodal distribution: threshold = midpoint of the jump
            threshold = (non_zero_gaps[jump_idx] + non_zero_gaps[jump_idx + 1]) / 2
        else:
            # Continuous distribution: fall back to median × multiplier
            threshold = median_gap * gap_multiplier
    else:
        # Too few data points: fall back to original logic
        threshold = median_gap * gap_multiplier

    col_bounds: list[tuple[float, float]] = []
    col_start = sorted_x[0]

    for i, gap in enumerate(gaps):
        if gap > threshold:
            col_end = sorted_x[i]
            if col_end - col_start >= min_col_width:
                col_bounds.append((col_start, col_end))
            col_start = sorted_x[i + 1]

    col_end = sorted_x[-1]
    if col_end - col_start >= min_col_width:
        col_bounds.append((col_start, col_end))

    return col_bounds


def _assign_chars_to_columns(row_chars: list[dict], col_bounds: list[tuple[float, float]]) -> list[str]:
    """Two-pass: assign characters to columns, then merge adjacent words within each column.

    Pass 1 (character-level): Assign each character to the closest column using
    divider midpoints.  This prevents cross-column fusion (characters from
    different columns never get grouped together).

    Pass 2 (word-merge within column): Within each column, merge adjacent
    characters that have small x-gaps (< 5pt).  This preserves multi-character
    words like "摘要" or "2016-05-30" within their correct column.
    """
    if not col_bounds:
        return []
    cells = ["" for _ in col_bounds]
    cell_char_indices: list[list[int]] = [[] for _ in col_bounds]

    # Compute divider lines
    dividers = [col_bounds[0][0] - 10]
    for i in range(len(col_bounds) - 1):
        mid = (col_bounds[i][1] + col_bounds[i + 1][0]) / 2
        dividers.append(mid)
    dividers.append(col_bounds[-1][1] + 10)

    # Pass 1: Assign each character to its closest column
    sorted_chars = sorted(row_chars, key=lambda x: x["x0"])
    char_texts = []
    for c in sorted_chars:
        text = str(c.get("text", "")).strip()
        if not text:
            continue
        char_x = (c["x0"] + c.get("x1", c["x0"])) / 2
        col_idx = bisect.bisect_right(dividers, char_x) - 1
        col_idx = max(0, min(col_idx, len(cells) - 1))
        char_texts.append((text, col_idx, c))

    # Group characters by column for word merging
    chars_by_col: dict[int, list[dict]] = {}
    for text, col_idx, c in char_texts:
        chars_by_col.setdefault(col_idx, []).append(c)

    # Pass 2: Within each column, merge adjacent words using x-gap threshold
    for col_idx, col_chars in chars_by_col.items():
        col_chars.sort(key=lambda x: x["x0"])
        words = []
        cur_word = None
        for ch in col_chars:
            text = str(ch.get("text", "")).strip()
            if not text:
                continue
            if cur_word is None:
                cur_word = text
            else:
                gap = ch["x0"] - cur_word["x1"] if "x1" in locals() else 0
                if gap is None:
                    gap = ch["x0"] - col_chars[0]["x0"]
                if gap < 5.0:
                    cur_word += text
                else:
                    words.append(cur_word)
                    cur_word = text
                cur_word_x1 = ch.get("x1", ch["x0"])
            if cur_word:
                words.append(cur_word)
        cells[col_idx] = " ".join(w.strip() for w in words if w.strip())

    return [cell.strip() for cell in cells]


def _chars_to_text(chars: list[dict]) -> str:
    """Merge a list of character dicts into a single text string."""
    if not chars:
        return ""
    sorted_c = sorted(chars, key=lambda c: c["x0"])
    parts = [sorted_c[0].get("text", "")]
    for i in range(1, len(sorted_c)):
        gap = sorted_c[i]["x0"] - sorted_c[i - 1].get("x1", sorted_c[i - 1]["x0"])
        if gap > 3:
            parts.append(" ")
        parts.append(sorted_c[i].get("text", ""))
    return "".join(parts)
