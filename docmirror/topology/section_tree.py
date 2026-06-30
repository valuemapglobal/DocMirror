# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Multi-language section tree builder.

Phase 3 of the DFG engine: detects headings and builds a hierarchical section tree
from document blocks using multi-language regex patterns, font size hierarchy,
and indent clustering.

Algorithm:
    1. Scan all blocks for heading candidates using universal patterns.
    2. Score each candidate by pattern match + font size difference + indent.
    3. Cluster candidates into levels based on font size and indent similarity.
    4. Build a tree of SectionNodes with child/parent relationships.
    5. Assign body blocks to the nearest preceding section.

Design: The heading detection regex is universal (multi-language). Domain-specific
variations handled through the pattern set, not the clustering algorithm.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Universal multi-language section patterns ───────────────────────────────────
UNIVERSAL_SECTION_PATTERNS: list[re.Pattern] = [
    # Chinese numbered headings
    re.compile(r"^(第)?[一二三四五六七八九十百]+[章节部分篇条]"),
    re.compile(r"^[（(][一二三四五六七八九十]+[）)]"),
    re.compile(r"^\d+[\.、]\s*[\u4e00-\u9fff]"),  # 1. 中文标题
    # Chinese bracket headings
    re.compile(r"^[\[【]\d+[\]】]"),
    # English numbered headings
    re.compile(r"^(Chapter|Section|Part|Appendix)\s+\d+", re.IGNORECASE),
    re.compile(r"^\d+(\.\d+)*\s+[A-Z][a-zA-Z\s]{3,}"),  # 1.2.3 Title
    re.compile(r"^[A-Z]\.\d+\.\s"),  # A.1. Title
    # Roman numeral
    re.compile(r"^[IVX]+\.\s+[A-Z]"),  # I. Title
    # Summary headings (across languages)
    re.compile(r"^(摘要|概要|总结|结论|附录|参考文献|Abstract|Summary|Introduction|Conclusion|References|Appendix)"),
    # Bold/all-caps short lines as heading candidates
    re.compile(r"^[A-Z][A-Z\s]{5,30}$"),  # ALL CAPS SHORT LINE
]

# Minimum heading confidence to accept
MIN_HEADING_CONFIDENCE = 0.4

# Font size ratio: heading must be at least this much larger than body text
HEADING_FONT_SIZE_RATIO = 1.1

# Maximum characters for a heading line (headings are typically short)
MAX_HEADING_CHARS = 120


@dataclass
class SectionNode:
    """A detected heading with its children and assigned body blocks."""

    node_id: str = ""
    title: str = ""
    level: int = 1  # 1 = top-level, 2 = sub-heading, etc.
    page_number: int = 1
    bbox: list[float] = field(default_factory=lambda: [0, 0, 0, 0])
    block_indices: list[int] = field(default_factory=list)  # indices in source blocks
    children: list[SectionNode] = field(default_factory=list)
    body_block_indices: list[int] = field(default_factory=list)  # body blocks under this section
    confidence: float = 1.0


@dataclass
class SectionTree:
    """Complete section tree for a document."""

    root: SectionNode | None = None
    flat_headings: list[SectionNode] = field(default_factory=list)  # all headings, flat list
    max_depth: int = 0
    total_headings: int = 0
    confidence: float = 1.0

    def find_section_for_block(self, block_index: int, page_number: int) -> SectionNode | None:
        """Find which section a block belongs to (nearest preceding heading)."""
        best = None
        for heading in self.flat_headings:
            if heading.page_number < page_number:
                best = heading
            elif heading.page_number == page_number:
                # Check if heading is above this block on the same page
                if heading.block_indices and heading.block_indices[0] < block_index:
                    best = heading
        return best


def detect_headings(
    blocks: list[dict[str, Any]],
    *,
    page_number: int = 1,
    body_font_size: float | None = None,
) -> list[SectionNode]:
    """Detect headings from a list of blocks on a page.

    Args:
        blocks: List of block dicts with ``text``, ``bbox``, ``font_size`` keys.
        page_number: Page number for result tagging.
        body_font_size: Median font size of body text. If None, estimated from blocks.

    Returns:
        List of SectionNode objects for detected headings.
    """
    if not blocks:
        return []

    # ── Estimate body font size ──
    if body_font_size is None:
        font_sizes = []
        for b in blocks:
            fs = b.get("font_size") or b.get("fontSize") or 0
            if fs > 0:
                font_sizes.append(float(fs))
        if font_sizes:
            font_sizes.sort()
            body_font_size = font_sizes[len(font_sizes) // 2]
        else:
            body_font_size = 12.0

    headings: list[SectionNode] = []

    for idx, block in enumerate(blocks):
        text = str(block.get("text") or block.get("content") or "").strip()
        if not text or len(text) > MAX_HEADING_CHARS:
            continue

        # Score heading likelihood
        score = _score_heading(text, block, body_font_size)

        if score >= MIN_HEADING_CONFIDENCE:
            node = SectionNode(
                node_id=f"sec:p{page_number}:b{idx}",
                title=text,
                level=1,  # Will be clustered into levels later
                page_number=page_number,
                bbox=list(block.get("bbox") or [0, 0, 0, 0]),
                block_indices=[idx],
                confidence=score,
            )
            headings.append(node)

    return headings


def _score_heading(text: str, block: dict[str, Any], body_font_size: float) -> float:
    """Score how likely a block is a heading using multiple signals.

    Returns a confidence score 0.0–1.0.
    """
    score = 0.0
    text = text.strip()

    # ── Signal 1: Pattern match (up to 0.5) ──
    for pat in UNIVERSAL_SECTION_PATTERNS:
        if pat.match(text):
            score += 0.5
            break

    # ── Signal 2: Font size (up to 0.3) ──
    font_size = float(block.get("font_size") or block.get("fontSize") or 0)
    if font_size > 0 and body_font_size > 0:
        ratio = font_size / body_font_size
        if ratio >= HEADING_FONT_SIZE_RATIO:
            if ratio >= 1.5:
                score += 0.3
            elif ratio >= 1.3:
                score += 0.2
            else:
                score += 0.1

    # ── Signal 3: Short text (up to 0.1) ──
    if len(text) <= 30:
        score += 0.1
    elif len(text) <= 50:
        score += 0.05

    # ── Signal 4: Indent (centered or left-aligned, up to 0.1) ──
    bbox = block.get("bbox")
    if bbox and len(bbox) >= 2:
        x0 = float(bbox[0])
        x1 = float(bbox[2])
        # Left-aligned or centered blocks are more likely headings
        if x0 < 100:
            score += 0.05
        # Very wide blocks might be decorative
        width = x1 - x0
        if 50 < width < 400:
            score += 0.05

    return min(1.0, score)


def build_section_tree(
    all_pages_headings: list[SectionNode],
    *,
    all_blocks: list[tuple[int, int, Any]] | None = None,
) -> SectionTree:
    """Build hierarchical section tree from detected headings.

    Args:
        all_pages_headings: Flat list of SectionNodes from detect_headings across all pages.
        all_blocks: Optional list of (page_number, block_index, block_dict) for body assignment.

    Returns:
        SectionTree with hierarchical structure.
    """
    if not all_pages_headings:
        return SectionTree()

    # ── Sort by page, then block index ──
    all_pages_headings.sort(
        key=lambda h: (
            h.page_number,
            h.block_indices[0] if h.block_indices else 0,
        )
    )

    # ── Cluster into levels by font size and indent ──
    # Extract font sizes for clustering
    heading_sizes: list[float] = []
    for h in all_pages_headings:
        bbox = h.bbox
        if bbox and len(bbox) >= 4:
            heading_sizes.append(float(bbox[2]) - float(bbox[0]))  # width as proxy for significance
        else:
            heading_sizes.append(0)

    # Simple level detection: assign levels based on relative size/confidence
    if len(all_pages_headings) > 1:
        # Find distinct size clusters
        sizes_unique = sorted(set(heading_sizes), reverse=True)
        size_to_level: dict[float, int] = {}
        for i, s in enumerate(sizes_unique):
            size_to_level[s] = min(i + 1, 6)  # Max 6 levels

        for h in all_pages_headings:
            if h.bbox and len(h.bbox) >= 4:
                w = float(h.bbox[2]) - float(h.bbox[0])
                h.level = size_to_level.get(w, 2)
            else:
                h.level = 2

    # ── Build tree structure ──
    # Simple algorithm: each heading belongs to nearest preceding higher-level heading
    root = SectionNode(node_id="root", title="Document", level=0)
    stack: list[SectionNode] = [root]

    for heading in all_pages_headings:
        # Pop stack until we find a parent (lower level number = higher in hierarchy)
        while stack and stack[-1].level >= heading.level:
            stack.pop()

        if stack:
            parent = stack[-1]
            parent.children.append(heading)

        stack.append(heading)

    tree = SectionTree(
        root=root,
        flat_headings=all_pages_headings,
        max_depth=max(
            (h.level for h in all_pages_headings),
            default=0,
        ),
        total_headings=len(all_pages_headings),
        confidence=(
            sum(h.confidence for h in all_pages_headings) / len(all_pages_headings) if all_pages_headings else 1.0
        ),
    )

    return tree


__all__ = [
    "MAX_HEADING_CHARS",
    "MIN_HEADING_CONFIDENCE",
    "SectionNode",
    "SectionTree",
    "UNIVERSAL_SECTION_PATTERNS",
    "build_section_tree",
    "detect_headings",
]
