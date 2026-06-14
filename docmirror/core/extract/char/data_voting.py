# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Char strategy: detect_columns_by_data_voting."""

from __future__ import annotations

import logging
from collections import defaultdict

from docmirror.core.extract.utils import _assign_chars_to_columns, _group_chars_into_rows
from docmirror.core.utils.vocabulary import _RE_IS_AMOUNT, _RE_IS_DATE
from docmirror.core.utils.watermark import is_watermark_char

logger = logging.getLogger(__name__)

def detect_columns_by_data_voting(
    page_plum,
) -> list[list[str]] | None:
    """Data-row-driven column boundary detection.

    Uses gap positions from data rows (rows containing dates / amounts)
    to vote on column boundaries.  More robust than header-anchors:
    no dependency on header row, handles bilingual mixed headers.
    """
    try:
        words = page_plum.extract_words(keep_blank_chars=True, x_tolerance=2)
    except Exception as exc:
        logger.debug(f"operation: suppressed {exc}")
        return None
    if not words or len(words) < 10:
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

    if len(word_rows) < 5:
        return None

    # ── Filter data rows: rows containing dates or amounts ──
    data_rows: list[tuple[float, list[dict]]] = []
    for y_mid, rw in word_rows:
        texts = " ".join(w["text"] for w in rw)
        if _RE_IS_DATE.search(texts):
            data_rows.append((y_mid, rw))
        elif any(
            _RE_IS_AMOUNT.match(w["text"].strip().replace(",", "").replace("\u00a5", ""))
            for w in rw
            if w["text"].strip()
        ):
            data_rows.append((y_mid, rw))

    if len(data_rows) < 3:
        return None

    # ── Collect gap midpoint positions (3 pt resolution) ──
    gap_votes: dict[int, int] = defaultdict(int)
    page_w = page_plum.width or 600
    for _, rw in data_rows[:30]:
        for i in range(len(rw) - 1):
            gap_left = rw[i]["x1"]
            gap_right = rw[i + 1]["x0"]
            if gap_right - gap_left < 3:
                continue  # Too narrow \u2014 not a column gap
            gap_mid = (gap_left + gap_right) / 2
            bucket = round(gap_mid / 3) * 3
            gap_votes[bucket] += 1

    if not gap_votes:
        return None

    # ── Voting: gaps present in >= 40 % of data rows \u2192 column boundary ──
    n_voters = min(len(data_rows), 30)
    threshold = max(3, int(n_voters * 0.4))
    voted_gaps = sorted(x for x, count in gap_votes.items() if count >= threshold)

    if len(voted_gaps) < 2:
        return None

    # ── Merge adjacent gaps (< 8 pt \u2192 same boundary) ──
    merged_gaps: list[float] = [voted_gaps[0]]
    for g in voted_gaps[1:]:
        if g - merged_gaps[-1] < 8:
            merged_gaps[-1] = (merged_gaps[-1] + g) / 2
        else:
            merged_gaps.append(g)

    # ── Build column boundaries from gap midpoints ──
    col_bounds: list[tuple[float, float]] = []
    col_bounds.append((0, merged_gaps[0]))
    for i in range(len(merged_gaps) - 1):
        col_bounds.append((merged_gaps[i], merged_gaps[i + 1]))
    col_bounds.append((merged_gaps[-1], page_w))

    if len(col_bounds) < 3:
        return None

    # ── Extract all rows at character level using column bins ──
    chars = page_plum.chars
    if not chars:
        return None
    chars = [c for c in chars if not is_watermark_char(c)]
    if not chars:
        return None

    char_rows = _group_chars_into_rows(chars)
    result: list[list[str]] = []
    for _, row_chars in char_rows:
        row = _assign_chars_to_columns(row_chars, col_bounds)
        result.append(row)

    if len(result) < 3:
        return None

    logger.debug(
        f"data-voting: {len(result)} rows, "
        f"{len(col_bounds)} cols from "
        f"{len(data_rows)} data rows, "
        f"{len(merged_gaps)} voted gaps"
    )
    return result
