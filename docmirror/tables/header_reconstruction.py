# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Header reconstruction — repairs split and multi-row headers.

Purpose: Rejoins vertically split header cells, fixes sticky headers, and
splits compound semantic header units (e.g. credit report layouts).

Main components: ``reconstruct_headers_by_columns``, ``_fix_sticky_headers_heuristic``.

Upstream: Normalized table with broken header rows.

Downstream: ``table.pipeline.stage_header``, ``table.column_anchor``.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Credit report header correction dictionary
# ═══════════════════════════════════════════════════════════════════════════

CREDIT_REPORT_HEADER_FIXES = {
    "当前交有易未的结清构信数贷": "当前有未结清信贷交易的机构数",
    "当前交有易未的结机清构信数贷": "当前有未结清信贷交易的机构数",
    "首次责有任相的关年还份款": "首次有相关还款责任的年份",
}


def reconstruct_headers_by_columns(headers: list[str], page_chars: list | None = None) -> list[str]:
    """Column-aware header reconstruction algorithm (v11 optimized)

    Column boundary detection and text reconstruction based on character physical position.
    Simulates human column boundary recognition when reading tables.

    Args:
        headers: Original headers list (may contain merged/sticky text)
        page_chars: Page character-level coordinate info (optional, for advanced reconstruction)

    Returns:
        Reconstructed headers list

    Algorithm:
    1. Domain dictionary fast correction (priority)
    2. Vertical projection analysis (if char coordinates available)
    3. Heuristic split (fallback)
    """
    if not headers or len(headers) <= 1:
        return headers

    # Step 1: Domain dictionary correction (most reliable)
    fixed_headers = []
    for h in headers:
        if h in CREDIT_REPORT_HEADER_FIXES:
            corrected = CREDIT_REPORT_HEADER_FIXES[h]
            logger.debug(f"[HeaderFix] Corrected: '{h}' → '{corrected}'")
            fixed_headers.append(corrected)
        else:
            fixed_headers.append(h)

    # Step 2: If char coordinates available, use vertical projection regrouping
    if page_chars:
        fixed_headers = _reconstruct_by_vertical_projection(fixed_headers, page_chars)

    # Step 3: Heuristic merging detection (fallback)
    fixed_headers = _fix_sticky_headers_heuristic(fixed_headers)

    return fixed_headers


def _reconstruct_by_vertical_projection(headers: list[str], page_chars: list) -> list[str]:
    """Header reconstruction via vertical projection histogram

    Detect column boundaries using character x-coordinate vertical projection density.

    Args:
        headers: Current headers
        page_chars: Character-level coordinate list [{x0, y0, x1, y1, text}, ...]

    Returns:
        Reconstructed headers
    """
    if not page_chars:
        return headers

    # Extract all character x coordinates
    x_positions = []
    for char_info in page_chars:
        x_positions.append(char_info.get("x0", 0))

    if not x_positions:
        return headers

    # Detect vertical blank gaps (column boundaries)
    x_positions.sort()
    gaps = _detect_vertical_gaps(x_positions, threshold=15.0)

    if not gaps:
        return headers

    # Regroup characters based on gaps
    if len(gaps) >= 1 and page_chars:
        grouped = _group_chars_by_column_gaps(page_chars, gaps)
        if grouped and len(grouped) >= len(headers):
            logger.debug(
                "[VerticalProjection] regrouped %d header columns from %d gaps",
                len(grouped),
                len(gaps),
            )
            return grouped[: max(len(headers), len(grouped))]

    return headers


def _group_chars_by_column_gaps(
    page_chars: list[dict],
    gap_centers: list[float],
) -> list[str]:
    """Assign page chars to columns separated by vertical gaps; return cell texts."""
    if not page_chars or not gap_centers:
        return []

    bounds = [float("-inf"), *sorted(gap_centers), float("inf")]
    buckets: list[list[dict]] = [[] for _ in range(len(bounds) - 1)]
    for char_info in page_chars:
        x = float(char_info.get("x0", 0))
        for idx in range(len(bounds) - 1):
            if bounds[idx] <= x < bounds[idx + 1]:
                buckets[idx].append(char_info)
                break

    columns: list[str] = []
    for bucket in buckets:
        if not bucket:
            continue
        text = "".join(c["text"] for c in sorted(bucket, key=lambda c: c.get("x0", 0)))
        cleaned = text.strip()
        if cleaned:
            columns.append(cleaned)
    return columns


def _detect_vertical_gaps(x_positions: list[float], threshold: float = 15.0) -> list[float]:
    """Detect gaps in vertical projection

    Args:
        x_positions: Sorted x-coordinate list
        threshold: Gap threshold (pt)

    Returns:
        Gap position list
    """
    gaps = []
    for i in range(1, len(x_positions)):
        gap = x_positions[i] - x_positions[i - 1]
        if gap > threshold:
            gaps.append((x_positions[i - 1] + x_positions[i]) / 2)
    return gaps


def _fix_sticky_headers_heuristic(headers: list[str]) -> list[str]:
    """Heuristic sticky header repair

    Detect and split abnormally long header text.

    Args:
        headers: Current headers

    Returns:
        Repaired headers
    """
    fixed = []
    for h in headers:
        # Detect unusually long headers (>30 chars with multiple semantic units)
        if len(h) > 30 and _has_multiple_semantic_units(h):
            # Attempt to split (based on credit report domain knowledge)
            split_parts = _split_credit_report_header(h)
            if split_parts:
                logger.debug(f"[HeuristicFix] Split long header: '{h}' → {split_parts}")
                fixed.extend(split_parts)
            else:
                fixed.append(h)
        else:
            fixed.append(h)
    return fixed


def _has_multiple_semantic_units(text: str) -> bool:
    """Check whether text contains multiple semantic units"""
    # Contains multiple keywords: "的", "transaction", "institution", "year", "responsible", etc.
    keywords = ["的", "交易", "机构", "年份", "责任"]
    count = sum(1 for kw in keywords if kw in text)
    return count >= 3


def _split_credit_report_header(text: str) -> list[str] | None:
    """Credit-report specific header split (number of institutions, repayment responsibility year, etc.)."""
    patterns = [
        (r"当前.*信贷交易.*机构数", ["当前有未结清信贷交易的机构数"]),
        (r"首次.*还款.*责任.*年份", ["首次有相关还款责任的年份"]),
    ]

    for pattern, replacement in patterns:
        if re.search(pattern, text):
            return replacement

    return None
