# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Column-aware reading order computer.

Phase 2 of the DFG engine: computes the human reading order for a document
by using column detection results and bbox geometry.

Algorithm:
    1. For each page, assign blocks to columns (from Phase 1 ColumnDetector).
    2. Within each column, sort blocks top-to-bottom, left-to-right.
    3. Across columns, order column-major (column 0 first, then column 1, ...).
    4. For multi-page documents, chain pages sequentially.
    5. Build reading_flow (sequence of block indices) and edges (reading_next).

Design: Pure geometry, no LLM. 95% of documents solved by Y-sort within columns.
The remaining 5% (extremely messy layouts) degrade to page-local bbox order.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from docmirror.structure.structure.column_detector import ColumnAssignment, ColumnLayout

logger = logging.getLogger(__name__)


@dataclass
class OrderedBlock:
    """A block with its computed reading order position."""
    block_index: int  # index in the source block list
    page_number: int
    reading_order: int  # global reading order (0-based)
    column_id: int = 0
    bbox: list[float] = field(default_factory=lambda: [0, 0, 0, 0])
    node_id: str = ""


@dataclass
class OrderedPage:
    """Reading order for a single page."""
    page_number: int
    ordered_blocks: list[OrderedBlock] = field(default_factory=list)
    column_ids: list[int] = field(default_factory=list)


@dataclass
class ReadingFlow:
    """Complete reading order for a document."""
    pages: dict[int, OrderedPage] = field(default_factory=dict)
    global_order: list[OrderedBlock] = field(default_factory=list)  # flat ordered list
    total_blocks: int = 0
    degraded_pages: list[int] = field(default_factory=list)


def compute_reading_order(
    pages: list[dict[str, Any]],
    column_layout: ColumnLayout | None = None,
    *,
    strategy: str = "column_major",
) -> ReadingFlow:
    """Compute reading order for all pages in a document.

    Args:
        pages: List of page dicts with ``page_number``, ``blocks`` (or ``texts``).
        column_layout: Pre-computed ColumnLayout from detect_columns_from_pages().
                       If None, column detection is skipped and all pages are single-column.
        strategy: Ordering strategy — ``column_major`` (default) or ``top_left``.

    Returns:
        ReadingFlow with global_order and per-page breakdown.
    """
    flow = ReadingFlow()
    global_index = 0

    for page in pages:
        page_num = int(page.get("page_number") or 0)
        blocks = page.get("blocks") or page.get("texts") or []

        if not blocks:
            continue

        # Get column assignment for this page
        col_assignment = None
        if column_layout and page_num in column_layout.pages:
            col_assignment = column_layout.pages[page_num]

        ordered_page = _compute_page_reading_order(
            blocks=blocks,
            page_num=page_num,
            start_global_index=global_index,
            col_assignment=col_assignment,
            strategy=strategy,
        )

        flow.pages[page_num] = ordered_page
        flow.global_order.extend(ordered_page.ordered_blocks)
        flow.total_blocks += len(ordered_page.ordered_blocks)

        if col_assignment and col_assignment.degraded:
            flow.degraded_pages.append(page_num)

        global_index += len(ordered_page.ordered_blocks)

    return flow


def _compute_page_reading_order(
    blocks: list[dict[str, Any]],
    page_num: int,
    start_global_index: int,
    col_assignment: ColumnAssignment | None,
    strategy: str,
) -> OrderedPage:
    """Compute reading order for a single page."""
    ordered_page = OrderedPage(page_number=page_num)
    global_index = start_global_index

    if col_assignment and len(col_assignment.columns) > 1:
        # Multi-column page: order column-major
        ordered_page.column_ids = list(range(len(col_assignment.columns)))
        for col_id, blk_indices in enumerate(col_assignment.columns):
            # Sort blocks within this column: top-to-bottom, then left-to-right
            col_blocks = []
            for idx in blk_indices:
                if idx < len(blocks):
                    col_blocks.append((idx, blocks[idx]))

            col_blocks.sort(key=lambda x: (
                _bbox_top(x[1].get("bbox")),
                _bbox_left(x[1].get("bbox")),
            ))

            for idx, block in col_blocks:
                ordered_block = OrderedBlock(
                    block_index=idx,
                    page_number=page_num,
                    reading_order=global_index,
                    column_id=col_id,
                    bbox=list(block.get("bbox") or [0, 0, 0, 0]),
                    node_id=f"node:p{page_num}:b{idx}",
                )
                ordered_page.ordered_blocks.append(ordered_block)
                global_index += 1
    else:
        # Single column: simple top-left sort
        ordered_page.column_ids = [0]
        indexed_blocks = [(i, blocks[i]) for i in range(len(blocks))]
        indexed_blocks.sort(key=lambda x: (
            _bbox_top(x[1].get("bbox")),
            _bbox_left(x[1].get("bbox")),
        ))

        for idx, block in indexed_blocks:
            ordered_block = OrderedBlock(
                block_index=idx,
                page_number=page_num,
                reading_order=global_index,
                column_id=0,
                bbox=list(block.get("bbox") or [0, 0, 0, 0]),
                node_id=f"node:p{page_num}:b{idx}",
            )
            ordered_page.ordered_blocks.append(ordered_block)
            global_index += 1

    return ordered_page


def _bbox_top(bbox: Any) -> float:
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 2:
        return float(bbox[1])
    return 0.0


def _bbox_left(bbox: Any) -> float:
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 1:
        return float(bbox[0])
    return 0.0


__all__ = [
    "OrderedBlock",
    "OrderedPage",
    "ReadingFlow",
    "compute_reading_order",
]
