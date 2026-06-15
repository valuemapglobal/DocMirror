# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Column anchor — global header and column alignment across pages.

Purpose: Finds header rows, matches expected vocabulary headers, and builds
``column_anchors`` shared across multi-page ledger tables.

Main components: ``find_header_row_in_table``, ``build_global_column_anchors``,
``header_cells_to_column_anchors``.

Upstream: Raw table matrices, ``utils.vocabulary``.

Downstream: ``extract.extraction_hint``, ``ocr.postprocess.column_aware``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_HEADER_MARKERS = (
    "交易单号",
    "交易时间",
    "交易类型",
    "交易方式",
    "金额",
    "交易对方",
    "商户单号",
    "借方",
    "贷方",
    "余额",
    "摘要",
)


def _normalize_header(cell: str) -> str:
    return re.sub(r"\s+", "", (cell or "").strip())


def row_matches_expected_headers(row: list[str], expected: list[str], min_match: int = 3) -> bool:
    """True if row contains enough expected column header tokens."""
    if not expected:
        return False
    row_norm = [_normalize_header(c) for c in row]
    hits = 0
    for exp in expected:
        exp_n = _normalize_header(exp)
        if any(exp_n in cell or cell in exp_n for cell in row_norm if cell):
            hits += 1
    return hits >= min(min_match, len(expected))


def find_header_row_in_table(rows: list[list[str]], expected_headers: list[str] | None = None) -> int | None:
    """Return index of header row in a table matrix."""
    expected = expected_headers or list(_DEFAULT_HEADER_MARKERS)
    for i, row in enumerate(rows[:5]):
        if row_matches_expected_headers(row, expected, min_match=3):
            return i
    return None


def find_global_header_row_across_pages(
    plumber_doc,
    page_has_text: list[bool],
    expected_headers: list[str] | None = None,
    max_pages: int = 30,
    sidebar_x_ratio: float | None = None,
) -> tuple[int, list[str]] | None:
    """Scan early pages for a ledger header row.

    Returns:
        ``(page_idx, header_cells)`` or None
    """
    if plumber_doc is None:
        return None

    expected = expected_headers or list(_DEFAULT_HEADER_MARKERS)
    limit = min(len(plumber_doc.pages), max_pages)

    for pid in range(limit):
        if pid < len(page_has_text) and not page_has_text[pid]:
            continue
        try:
            page = plumber_doc.pages[pid]
            page_w = getattr(page, "width", 0) or 0
            crop_kwargs: dict[str, Any] = {}
            if sidebar_x_ratio and page_w > 0:
                crop_kwargs["crop"] = (0, 0, page_w * sidebar_x_ratio, page.height)

            tables = page.extract_tables(**crop_kwargs) if crop_kwargs else page.extract_tables()
            if not tables:
                # Try char-based line grouping
                text = page.extract_text() or ""
                if any(h in text for h in expected[:3]):
                    lines = [ln.split() for ln in text.splitlines() if ln.strip()]
                    for row in lines[:8]:
                        if row_matches_expected_headers(row, expected):
                            return pid, row
                continue

            for tbl in tables:
                if not tbl:
                    continue
                idx = find_header_row_in_table(tbl, expected)
                if idx is not None:
                    return pid, list(tbl[idx])
        except Exception as exc:
            logger.debug("[ColumnAnchor] page %d scan failed: %s", pid, exc)
    return None


def header_cells_to_column_anchors(
    page,
    header_cells: list[str],
    sidebar_x_ratio: float | None = None,
) -> list[float]:
    """Map header cell texts to x-center positions using page chars."""
    if not header_cells or page is None:
        return []

    page_w = getattr(page, "width", 0) or 0
    cutoff = page_w * sidebar_x_ratio if sidebar_x_ratio and page_w else page_w
    chars = getattr(page, "chars", []) or []
    anchors: list[float] = []

    for cell in header_cells:
        token = _normalize_header(cell)
        if not token or len(token) < 2:
            continue
        matches = [
            c
            for c in chars
            if token in _normalize_header(c.get("text", ""))
            and c.get("x0", 0) < cutoff
        ]
        if matches:
            xs = [(c.get("x0", 0) + c.get("x1", 0)) / 2 for c in matches]
            anchors.append(sum(xs) / len(xs))
    return sorted(set(round(x, 1) for x in anchors))


def build_global_column_anchors(
    plumber_doc,
    page_has_text: list[bool],
    *,
    expected_headers: list[str] | None = None,
    sidebar_x_ratio: float | None = None,
) -> list[float] | None:
    """Full pipeline: find header row → derive x anchors."""
    found = find_global_header_row_across_pages(
        plumber_doc,
        page_has_text,
        expected_headers=expected_headers,
        sidebar_x_ratio=sidebar_x_ratio,
    )
    if not found:
        return None

    page_idx, header_cells = found
    try:
        page = plumber_doc.pages[page_idx]
        anchors = header_cells_to_column_anchors(page, header_cells, sidebar_x_ratio)
        if len(anchors) >= 2:
            logger.info("[ColumnAnchor] Built %d anchors from page %d", len(anchors), page_idx + 1)
            return anchors
    except Exception as exc:
        logger.debug("[ColumnAnchor] anchor build failed: %s", exc)
    return None
