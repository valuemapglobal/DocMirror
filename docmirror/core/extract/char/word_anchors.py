# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Char strategy: detect_columns_by_word_anchors."""

from __future__ import annotations

import logging

from docmirror.core.extract.utils import _assign_chars_to_columns, _group_chars_into_rows
from docmirror.core.utils.vocabulary import _is_header_cell
from docmirror.core.utils.watermark import is_watermark_char

logger = logging.getLogger(__name__)

def detect_columns_by_word_anchors(page_plum) -> list[list[str]] | None:
    """Word-anchor column detection.

    Uses ``extract_words()`` to locate each header word's x-position as a
    column left boundary, then bins characters into columns at char level.

    Compared to char-level clustering, word-level gaps are more pronounced
    and can handle narrow multi-column layouts (e.g. columns with only
    8\u20139 pt spacing).
    """
    try:
        # Try a tighter x_tolerance first (distinguish 2\u20133 pt column gaps)
        # then the default \u2014 keep the result with more words (= finer column splits)
        best_words = None
        for x_tol in (2, 3):
            w = page_plum.extract_words(keep_blank_chars=True, x_tolerance=x_tol)
            if w and (best_words is None or len(w) > len(best_words)):
                best_words = w
        words = best_words
    except Exception as exc:
        logger.debug(f"operation: suppressed {exc}")
        return None
    if not words or len(words) < 5:
        return None

    # ── Group words into rows by y-coordinate ──
    ROW_TOL = 5
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    word_rows: list[tuple[float, list[dict]]] = []
    cur_y = sorted_words[0]["top"]
    cur_row = [sorted_words[0]]
    for w in sorted_words[1:]:
        if abs(w["top"] - cur_y) <= ROW_TOL:
            cur_row.append(w)
        else:
            y_mid = sum(ww["top"] for ww in cur_row) / len(cur_row)
            word_rows.append((y_mid, sorted(cur_row, key=lambda x: x["x0"])))
            cur_row = [w]
            cur_y = w["top"]
    if cur_row:
        y_mid = sum(ww["top"] for ww in cur_row) / len(cur_row)
        word_rows.append((y_mid, sorted(cur_row, key=lambda x: x["x0"])))

    if len(word_rows) < 2:
        return None

    # ── Find header row: the row in the first 5 that looks most like a header ──
    header_row_idx = -1
    for i, (y_mid, rw) in enumerate(word_rows[:5]):
        texts = [w["text"].strip() for w in rw if w["text"].strip()]
        if len(texts) < 3:
            continue
        header_count = sum(1 for t in texts if _is_header_cell(t))
        if header_count / len(texts) >= 0.5:
            header_row_idx = i
            break

    if header_row_idx == -1:
        return None

    header_words = word_rows[header_row_idx][1]
    if len(header_words) < 3:
        return None

    # ── Build column boundaries from header word positions ──
    # Each word's x0, x1 become boundaries; _assign_chars_to_columns places splits in the gaps
    col_bounds: list[tuple[float, float]] = []
    for i, w in enumerate(header_words):
        x_start = w["x0"]
        x_end = w.get("x1", w["x0"] + 10)
        col_bounds.append((x_start, x_end))

    if len(col_bounds) < 3:
        return None

    # ── Extract data at character level using the column bins ──
    chars = page_plum.chars
    if not chars:
        return None
    chars = [c for c in chars if not is_watermark_char(c)]
    if not chars:
        return None

    char_rows = _group_chars_into_rows(chars)

    # Start extracting from the header row's y-position
    header_y = word_rows[header_row_idx][0]
    result: list[list[str]] = []
    for y_mid, row_chars in char_rows:
        if y_mid < header_y - 3:
            continue
        row = _assign_chars_to_columns(row_chars, col_bounds)
        result.append(row)

    if len(result) < 2:
        return None

    logger.debug(
        f"word-anchors: {len(result) - 1} data rows, {len(col_bounds)} cols from {len(header_words)} header words"
    )
    return result


