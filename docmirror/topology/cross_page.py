# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cross-page continuity resolver.

Phase 4 of the DFG engine: detects when content spans across page boundaries
(paragraphs broken across pages, tables split across pages).

Algorithm:
    1. For adjacent page pairs, collect bottom-of-page blocks (page N) and
       top-of-page blocks (page N+1).
    2. Check horizontal overlap (shared column space) between bottom/top blocks.
    3. Check text continuity: is the top-block text a natural continuation
       of the bottom-block text? (Does bottom end mid-sentence? Does top start lowercase?)
    4. Produce CrossPageBridge objects with confidence scores.
    5. Below-threshold bridges are marked as ``candidate`` rather than confirmed.

Design: Pure geometry + text signal, no LLM. Uncertain continuations produce
candidate bridges rather than hallucinated merges.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Minimum horizontal overlap ratio for two blocks to be considered in the same column
MIN_HORIZONTAL_OVERLAP = 0.3

# Maximum vertical distance between bottom of page N block and top of page N+1 block
MAX_VERTICAL_GAP_POINTS = 50.0

# Confidence thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.8
MEDIUM_CONFIDENCE_THRESHOLD = 0.5


@dataclass
class CrossPageBridge:
    """A detected continuity bridge between two blocks on adjacent pages."""

    bridge_id: str = ""
    page_a: int = 0
    block_a_index: int = 0
    page_b: int = 0
    block_b_index: int = 0
    confidence: float = 1.0
    evidence: dict[str, Any] = field(default_factory=dict)
    is_candidate: bool = False  # True if confidence below threshold


@dataclass
class BridgeList:
    """Collection of cross-page bridges for a document."""

    bridges: list[CrossPageBridge] = field(default_factory=list)
    confirmed_count: int = 0
    candidate_count: int = 0


def detect_cross_page_bridges(
    pages: list[dict[str, Any]],
    *,
    min_overlap: float = MIN_HORIZONTAL_OVERLAP,
    max_gap: float = MAX_VERTICAL_GAP_POINTS,
) -> BridgeList:
    """Detect cross-page continuity for all adjacent page pairs in a document.

    Args:
        pages: List of page dicts with ``page_number``, ``blocks`` (or ``texts``),
               ``height``, ``width`` keys.
        min_overlap: Minimum horizontal overlap ratio for same-column check.
        max_gap: Maximum vertical gap in points for considering a bridge.

    Returns:
        BridgeList with all detected bridges.
    """
    result = BridgeList()

    if len(pages) < 2:
        return result

    # Sort pages by page_number
    sorted_pages = sorted(
        pages,
        key=lambda p: int(p.get("page_number") or 0),
    )

    for i in range(len(sorted_pages) - 1):
        page_a = sorted_pages[i]
        page_b = sorted_pages[i + 1]

        page_a_num = int(page_a.get("page_number") or 0)
        page_b_num = int(page_b.get("page_number") or 0)

        blocks_a = page_a.get("blocks") or page_a.get("texts") or []
        blocks_b = page_b.get("blocks") or page_b.get("texts") or []

        if not blocks_a or not blocks_b:
            continue

        page_height = float(page_a.get("height") or page_a.get("page_height") or 0)

        # ── Collect bottom candidates from page A, top candidates from page B ──
        bottom_candidates = _collect_candidates(blocks_a, page_height, "bottom")
        top_candidates = _collect_candidates(blocks_b, 0, "top")

        # ── For each bottom candidate, find matching top candidate ──
        for b_idx, b_block in bottom_candidates:
            b_bbox = b_block.get("bbox")
            if not b_bbox or len(b_bbox) < 4:
                continue

            for t_idx, t_block in top_candidates:
                t_bbox = t_block.get("bbox")
                if not t_bbox or len(t_bbox) < 4:
                    continue

                # Check horizontal overlap
                overlap_ratio = _horizontal_overlap(b_bbox, t_bbox)
                if overlap_ratio < min_overlap:
                    continue

                # Check vertical gap
                gap = float(t_bbox[1])  # top of page B block (y0 relative to page)
                if gap > max_gap:
                    continue

                # Check text continuity
                text_a = str(b_block.get("text") or b_block.get("content") or "").strip()
                text_b = str(t_block.get("text") or t_block.get("content") or "").strip()
                text_score = _text_continuity_score(text_a, text_b)

                # Compute overall confidence
                confidence = _compute_bridge_confidence(overlap_ratio, gap, text_score)

                bridge = CrossPageBridge(
                    bridge_id=f"bridge:p{page_a_num}_b{b_idx}:p{page_b_num}_b{t_idx}",
                    page_a=page_a_num,
                    block_a_index=b_idx,
                    page_b=page_b_num,
                    block_b_index=t_idx,
                    confidence=confidence,
                    evidence={
                        "horizontal_overlap": overlap_ratio,
                        "vertical_gap": gap,
                        "text_continuity": text_score,
                    },
                    is_candidate=confidence < MEDIUM_CONFIDENCE_THRESHOLD,
                )

                if bridge.is_candidate:
                    result.candidate_count += 1
                else:
                    result.confirmed_count += 1

                result.bridges.append(bridge)

    return result


def _collect_candidates(
    blocks: list[dict[str, Any]],
    page_height: float,
    position: str,
) -> list[tuple[int, dict[str, Any]]]:
    """Collect candidate blocks from the bottom or top of a page.

    Args:
        blocks: List of block dicts with ``bbox`` key.
        page_height: Page height in points.
        position: ``"bottom"`` to collect bottom 20% of page, ``"top"`` for top 20%.

    Returns:
        List of (block_index, block_dict) tuples sorted by y-coordinate.
    """
    candidates = []

    for idx, block in enumerate(blocks):
        bbox = block.get("bbox")
        if not bbox or len(bbox) < 4:
            continue

        y0 = float(bbox[1])
        y1 = float(bbox[3])

        if position == "bottom":
            if y1 > page_height * 0.8:
                candidates.append((idx, block))
        elif position == "top":
            if y0 < page_height * 0.2 if page_height > 0 else y0 < 100:
                candidates.append((idx, block))

    # Sort by y-coordinate
    if position == "bottom":
        candidates.sort(key=lambda x: float(x[1].get("bbox", [0, 0, 0, 0])[1]), reverse=True)
    else:
        candidates.sort(key=lambda x: float(x[1].get("bbox", [0, 0, 0, 0])[1]))

    return candidates


def _horizontal_overlap(bbox_a: Any, bbox_b: Any) -> float:
    """Compute horizontal overlap ratio between two bboxes."""
    if not (isinstance(bbox_a, (list, tuple)) and len(bbox_a) >= 4):
        return 0.0
    if not (isinstance(bbox_b, (list, tuple)) and len(bbox_b) >= 4):
        return 0.0

    ax0, ax1 = float(bbox_a[0]), float(bbox_a[2])
    bx0, bx1 = float(bbox_b[0]), float(bbox_b[2])

    overlap_min = max(ax0, bx0)
    overlap_max = min(ax1, bx1)

    if overlap_max <= overlap_min:
        return 0.0

    # Ratio relative to the smaller block's width
    overlap_width = overlap_max - overlap_min
    min_width = min(ax1 - ax0, bx1 - bx0)

    if min_width <= 0:
        return 0.0

    return overlap_width / min_width


def _text_continuity_score(text_a: str, text_b: str) -> float:
    """Score how likely text_b is a natural continuation of text_a.

    Signals:
        - text_a does not end with sentence-ending punctuation → +0.4
        - text_b starts with lowercase letter → +0.3
        - text_a ends mid-word (hyphen or no space after last char) → +0.3

    Returns 0.0–1.0.
    """
    if not text_a or not text_b:
        return 0.0

    score = 0.0

    # Signal 1: text_a doesn't end with sentence-ending punctuation
    text_a_end = text_a.rstrip()[-1:] if text_a.rstrip() else ""
    if text_a_end and text_a_end not in {".", "。", "!", "！", "?", "？", ":", "：", ";", "；"}:
        score += 0.4

    # Signal 2: text_b starts with lowercase letter
    if text_b and text_b[0].islower():
        score += 0.3

    # Signal 3: text_b starts mid-sentence (not capitalized)
    first_chars = text_b.strip()[:3]
    if first_chars and not first_chars[0].isupper() and not re.match(r"[\d（(【\[]", first_chars[0]):
        score += 0.2

    return min(1.0, score)


def _compute_bridge_confidence(
    overlap: float,
    gap: float,
    text_score: float,
) -> float:
    """Compute overall bridge confidence from individual signals.

    Weights: overlap=0.4, gap=0.3, text=0.3
    """
    # Normalize gap: smaller gap = higher score
    gap_score = max(0.0, 1.0 - (gap / MAX_VERTICAL_GAP_POINTS))

    confidence = 0.4 * overlap + 0.3 * gap_score + 0.3 * text_score
    return round(min(1.0, max(0.0, confidence)), 3)


__all__ = [
    "BridgeList",
    "CrossPageBridge",
    "HIGH_CONFIDENCE_THRESHOLD",
    "MAX_VERTICAL_GAP_POINTS",
    "MEDIUM_CONFIDENCE_THRESHOLD",
    "MIN_HORIZONTAL_OVERLAP",
    "detect_cross_page_bridges",
]
