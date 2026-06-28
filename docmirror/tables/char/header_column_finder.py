# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Header-guided column finding — column boundaries from header word positions.

Purpose: Uses pdfplumber word extraction with CJK-adaptive x_tolerance to
find multi-character column headers, then projects boundaries onto data rows.

This addresses a fundamental limitation of ``_cluster_x_positions``: for CJK
text, intra-word character gaps are indistinguishable from inter-word gaps,
making gap-based clustering unreliable.  By extracting words at font-size
granularity, multi-character column headers ("借方发生额", "交易日期") are
preserved as single units and their inter-word x-gaps become clean column
boundaries.

Main components: ``detect_columns_by_header_guided``.

Upstream: pdfplumber page, ``docmirror.structure.utils.vocabulary``.

Downstream: ``extract.char_strategy``, ``extract.engine``.
"""

from __future__ import annotations

import logging

from docmirror.structure.utils.vocabulary import _score_header_by_vocabulary
from docmirror.structure.utils.watermark import is_watermark_char
from docmirror.tables.utils import (
    _assign_chars_to_columns,
    _group_chars_into_rows,
    _refine_dense_rows,
)

logger = logging.getLogger(__name__)

# CJK font sizes typically range from 8 to 14 pt.
# Setting x_tolerance to 0.7 × font_size reliably groups CJK characters within
# multi-character words while keeping inter-word gaps intact.
_CJK_X_TOLERANCE_FACTOR = 0.7


def _estimate_font_size(chars: list[dict]) -> float:
    """Estimate the dominant font size from character height."""
    heights = [
        c.get("bottom", 0) - c.get("top", 0)
        for c in chars if c.get("bottom", 0) - c.get("top", 0) > 3
    ]
    if not heights:
        return 10.0
    heights.sort()
    return heights[len(heights) // 2]


def detect_columns_by_header_guided(page_plum) -> list[list[str]] | None:
    """Header-guided column detection with CJK-adaptive word extraction.

    1. Find the header row by vocabulary scoring (first 15 rows).
    2. Re-extract words at CJK-adaptive x_tolerance to get multi-character
       column headers as single units.
    3. Build column boundaries from header word x-positions.
    4. Project boundaries onto remaining rows at character level.
    """
    chars = page_plum.chars
    if not chars or len(chars) < 10:
        return None

    chars = [c for c in chars if not is_watermark_char(c)]
    if not chars:
        return None

    # Step 1: Group chars into rows, find header row by vocab scoring
    rows_by_y = _group_chars_into_rows(chars)
    if len(rows_by_y) < 2:
        return None

    # Step 1.5: Extract words at CJK-adaptive tolerance FIRST.
    # We need word-level text for proper vocabulary scoring — concatenated
    # CJK chars from _group_chars_into_rows have no whitespace, so split()
    # produces one giant word and vocab scoring always returns < 3.
    font_size = _estimate_font_size(chars)
    # For CJK text, x_tolerance = font_size gives the most reliable word merging:
    # consecutive characters in the same word have ~1-2pt gaps, while gaps
    # between column headers are typically 0.3-0.5× font_size or larger.
    # Using 0.7 was too conservative (split "借方发生额" into fragments).
    x_tol = max(3, font_size * 0.9)
    logger.debug("header-guided: font_size=%.1f x_tolerance=%.1f", font_size, x_tol)

    try:
        words = page_plum.extract_words(keep_blank_chars=True, x_tolerance=x_tol, y_tolerance=3)
    except Exception as exc:
        logger.debug("header-guided word extraction failed: %s", exc)
        return None

    if not words or len(words) < 5:
        return None

    # Group words by y-coordinate for header row identification.
    # Use a tolerance matching the font size to handle multi-line headers.
    ROW_TOL = max(4, font_size * 0.5)
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

    # Find header row using word-level text (each word is a proper column header)
    header_row_idx = -1
    header_words: list[dict] = []
    best_vocab_score = 0

    for i, (y_mid, rw) in enumerate(word_rows[:15]):
        word_texts = [w["text"].strip() for w in rw if w["text"].strip()]
        if len(word_texts) < 3:
            continue
        vs = _score_header_by_vocabulary(word_texts)
        if vs > best_vocab_score:
            best_vocab_score = vs
            header_row_idx = i
            header_words = rw

    if header_row_idx == -1 or best_vocab_score < 3:
        return None

    header_words.sort(key=lambda w: w["x0"])

    # Step 4: Build column boundaries from header word positions
    col_boundaries: list[tuple[float, float]] = []
    for w in header_words:
        col_boundaries.append((w["x0"], w.get("x1", w["x0"] + 10)))

    if len(col_boundaries) < 3:
        return None

    logger.debug(
        "header-guided: %d cols from %d header words (x_tol=%.1f, vocab=%d)",
        len(col_boundaries), len(header_words), x_tol, best_vocab_score,
    )

    # Step 5: Project onto all rows from header onwards.
    # Use word_rows' y-coordinates (more precise than char-level grouping)
    # to find all rows from header onwards.
    header_y_mid = word_rows[header_row_idx][0]
    result: list[list[str]] = []
    for y_mid, row_chars in rows_by_y:
        if y_mid < header_y_mid - 2:
            continue
        row = _assign_chars_to_columns(row_chars, col_boundaries)
        result.append(row)

    if len(result) < 2:
        return None

    # Step 6: Post-process dense rows where values fused into one cell.
    # Standard Chartered bank statements produce text with no useful x-gaps
    # between column values, causing _assign_chars_to_columns to merge them.
    refined = _refine_dense_rows(result, col_boundaries, chars)
    if refined is not None:
        result = refined
        logger.info("header-guided: refined %d rows affected by column fusion",
                     sum(1 for r in result if any(len(c) > 20 for c in r)))

    # Column structure verification: log first data row
    if len(result) >= 2:
        first_data = result[1]
        non_empty = sum(1 for c in first_data if c.strip())
        logger.info(
            "header-guided: %d rows, %d cols (x_tol=%.1f, vocab=%d, non_empty_cells=%d)",
            len(result), len(col_boundaries), x_tol, best_vocab_score, non_empty,
        )
        if non_empty < 3:
            logger.warning("header-guided: first data row has only %d non-empty cells — reducing threshold", non_empty)
            # Reduce to 3 column minimum to avoid rejecting sparse but correct rows
            if len(col_boundaries) >= 3:
                pass  # Keep the columns, data sparsity is expected for narrow tables
    else:
        logger.debug("header-guided: only header row found, no data rows")
    return result
