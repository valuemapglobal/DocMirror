# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Header reconstruction — repairs split and multi-row headers.

Purpose: Rejoins vertically split header cells and fixes sticky headers using
format-neutral geometry and structural heuristics.

Main components: ``reconstruct_headers_by_columns``, ``_fix_sticky_headers_heuristic``.

Upstream: Normalized table with broken header rows.

Downstream: ``table.pipeline.stage_header``, ``table.column_anchor``.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


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
    1. Vertical projection analysis (if char coordinates available)
    2. Heuristic split (fallback)
    """
    if not headers or len(headers) <= 1:
        return headers

    fixed_headers = list(headers)

    # Step 1: If char coordinates available, use vertical projection regrouping
    if page_chars:
        fixed_headers = _reconstruct_by_vertical_projection(fixed_headers, page_chars)

    # Step 2: Heuristic merging detection (fallback)
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
        if len(h) > 30:
            split_parts = _split_declared_header(h)
            if split_parts:
                logger.debug(f"[HeuristicFix] Split long header: '{h}' → {split_parts}")
                fixed.extend(split_parts)
            else:
                fixed.append(h)
        else:
            fixed.append(h)
    return fixed


def _split_declared_header(text: str) -> list[str] | None:
    """Apply sticky-header repairs declared in plugin scene resources."""
    from docmirror.configs.scene.loader import get_scene_evidence_specs

    for spec in get_scene_evidence_specs().values():
        for rule in spec.get("header_split_patterns") or []:
            if not isinstance(rule, dict):
                continue
            pattern = str(rule.get("pattern") or "")
            replacement = [str(value) for value in rule.get("replacement") or []]
            if pattern and replacement and re.search(pattern, text):
                return replacement

    return None
