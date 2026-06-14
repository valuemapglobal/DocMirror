# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Char strategy: detect_columns_by_whitespace_projection."""

from __future__ import annotations

import logging

from docmirror.core.extract.char.vocab_boundary import _adjust_boundaries_by_vocab
from docmirror.core.extract.utils import _adaptive_row_tolerance
from docmirror.core.utils.vocabulary import _score_header_by_vocabulary

logger = logging.getLogger(__name__)

def detect_columns_by_whitespace_projection(
    page_plum,
) -> list[list[str]] | None:
    """Vertical whitespace projection — project all rows onto the x-axis
    and detect column boundaries from whitespace bands.

    Algorithm:
        1. Collect all non-space characters, group into rows by y.
        2. For each x-position (1 pt resolution), count how many rows
           have text at that position.
        3. Positions with projection value <= 10 % of row count are "whitespace".
        4. Continuous whitespace bands >= 3 pt wide \u2192 column boundary (midpoint).
        5. Split each row's characters into cells using column boundaries.

    Suited for: borderless tables where columns are aligned by spacing.
    """
    chars = page_plum.chars
    if not chars or len(chars) < 20:
        return None

    # F-1: adaptive row-grouping tolerance
    from .utils import _adaptive_row_tolerance

    row_tol = _adaptive_row_tolerance(chars)

    # Collect non-space chars, group into rows by y (using adaptive tolerance)
    text_chars = [c for c in chars if c["text"].strip()]
    if not text_chars:
        return None
    sorted_chars = sorted(text_chars, key=lambda c: c["top"])
    y_rows: dict[int, list] = {}
    current_yk = round(sorted_chars[0]["top"] / row_tol) * row_tol
    y_rows[current_yk] = [sorted_chars[0]]
    for c in sorted_chars[1:]:
        ck = round(c["top"] / row_tol) * row_tol
        if abs(c["top"] - current_yk) <= row_tol:
            y_rows.setdefault(current_yk, []).append(c)
        else:
            current_yk = ck
            y_rows.setdefault(current_yk, []).append(c)

    if len(y_rows) < 3:
        return None

    # x-coordinate range
    all_text_chars = [c for row in y_rows.values() for c in row]
    x_min = min(c["x0"] for c in all_text_chars)
    x_max = max(c["x1"] for c in all_text_chars)
    width = int(x_max - x_min) + 2
    if width < 20:
        return None

    # Build x-axis projection histogram
    row_count = len(y_rows)
    projection = [0] * width

    for row_chars in y_rows.values():
        marked = set()
        for c in row_chars:
            c_x0 = max(0, int(c["x0"] - x_min))
            c_x1 = min(width - 1, int(c["x1"] - x_min))
            for x in range(c_x0, c_x1 + 1):
                marked.add(x)
        for x in marked:
            projection[x] += 1

    # F-3: dynamic column-gap threshold (based on average character width)
    avg_char_w = sum(c["x1"] - c["x0"] for c in all_text_chars) / len(all_text_chars)
    min_gap_width = max(2.0, avg_char_w * 0.5)  # Minimum 2 pt or half a character width

    # Find whitespace bands: contiguous x-ranges with projection <= 10 % of row count
    threshold = row_count * 0.10
    gaps: list[tuple[float, float, int]] = []
    in_gap = False
    gap_start = 0

    for x in range(width):
        if projection[x] <= threshold:
            if not in_gap:
                gap_start = x
                in_gap = True
        else:
            if in_gap:
                gap_width = x - gap_start
                if gap_width >= min_gap_width:  # F-3: dynamic threshold
                    gaps.append((gap_start + x_min, x - 1 + x_min, gap_width))
                in_gap = False
    # Handle trailing gap
    if in_gap:
        gap_width = width - gap_start
        if gap_width >= 3:
            gaps.append((gap_start + x_min, width - 1 + x_min, gap_width))

    if len(gaps) < 2:
        return None  # Need at least 2 gaps to define 3+ columns

    # Column boundaries = [x_min, gap1_mid, gap2_mid, ..., x_max]
    col_boundaries = [x_min]
    for g_start, g_end, _ in gaps:
        col_boundaries.append((g_start + g_end) / 2)
    col_boundaries.append(x_max + 1)

    n_cols = len(col_boundaries) - 1
    if n_cols < 3 or n_cols > 20:
        return None

    # Vocabulary-guided boundary correction: avoid splitting known header words
    first_yk = sorted(y_rows.keys())[0]
    header_chars = sorted(y_rows[first_yk], key=lambda c: c["x0"])
    col_boundaries = _adjust_boundaries_by_vocab(col_boundaries, header_chars)
    n_cols = len(col_boundaries) - 1  # Count may stay the same, positions shift

    # Split each row by column boundaries
    result: list[list[str]] = []
    for yk in sorted(y_rows.keys()):
        row_chars = sorted(y_rows[yk], key=lambda c: c["x0"])

        # 1. Merge adjacent characters into words (prevent words from being split mid-span)
        words = []
        curr_word = None
        for c in row_chars:
            if not str(c.get("text", "")).strip():
                continue
            if not curr_word:
                curr_word = {"x0": c["x0"], "x1": c.get("x1", c["x0"]), "text": c["text"]}
            else:
                gap = c["x0"] - curr_word["x1"]
                if gap < 2.5:
                    curr_word["x1"] = max(curr_word["x1"], c.get("x1", c["x0"]))
                    curr_word["text"] += c["text"]
                else:
                    words.append(curr_word)
                    curr_word = {"x0": c["x0"], "x1": c.get("x1", c["x0"]), "text": c["text"]}
        if curr_word:
            words.append(curr_word)

        cells: list[str] = []
        for i in range(n_cols):
            left = col_boundaries[i]
            right = col_boundaries[i + 1]
            # Assign to columns based on word centre point
            cell_words = [
                w for w in words if (w["x0"] + w["x1"]) / 2 >= left - 1 and (w["x0"] + w["x1"]) / 2 < right + 1
            ]
            cell_text = " ".join(w["text"] for w in cell_words).strip()
            cells.append(cell_text)
        result.append(cells)

    logger.debug(f"whitespace_projection: {len(result)} rows, {n_cols} cols from {len(gaps)} gaps")

    if len(result) < 2:
        return None

    # ── Vocab scan: find the true header row, skip KV metadata rows ──
    # Some PDFs have KV metadata rows (e.g. "Account name: xxx") inside
    # the table zone before the actual header — these must be skipped
    best_header_idx = 0
    best_header_vs = 0
    scan_limit = min(15, len(result))
    for ri in range(scan_limit):
        vs = _score_header_by_vocabulary(result[ri])
        if vs > best_header_vs:
            best_header_vs = vs
            best_header_idx = ri

    if best_header_vs >= 3 and best_header_idx > 0:
        logger.info(
            f"whitespace_projection: header found at row {best_header_idx} "
            f"(vocab={best_header_vs}), skipping {best_header_idx} preamble rows"
        )
        result = result[best_header_idx:]

    return result if len(result) >= 2 else None


