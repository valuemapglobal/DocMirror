# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
table_merger — Cross-page table merging
========================================

Independent module extracted from ``CoreExtractor._merge_cross_page_tables``.
Responsible for detecting content-continuous cross-page tables and merging
them into a single Block.

Merge strategy:
  1. Next page's first row is a header (matching the previous page's header)
     → skip the duplicate header and merge data rows directly.
  2. First row is not a header (continuation page) → ``_strip_preamble``
     strips summary rows / duplicate headers before merging.
  3. Completely different table (header mismatch) → treat as an independent table.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from ...models.entities.domain import Block, PageLayout
from ..utils.text_utils import headers_match
from ..utils.vocabulary import _is_header_row
from .postprocess import _strip_preamble

logger = logging.getLogger(__name__)


def _median_col_count(rows: list) -> int:
    """P3-6: Compute the median column count of a table's rows."""
    if not rows:
        return 0
    counts = sorted(len(r) for r in rows if isinstance(r, (list, tuple)))
    if not counts:
        return 0
    return counts[len(counts) // 2]


def collect_cross_page_merge_groups(pages: list[PageLayout]) -> list[dict]:
    """Plan cross-page table merges without mutating pages.

    Returns a list of merge groups, each:
        {"rows": list[list], "pages": list[int], "block": Block, "merge_log": list[dict]}
    """
    if not pages:
        return []

    all_blocks = []
    for page in pages:
        for block in page.blocks:
            all_blocks.append({"block": block, "page_number": page.page_number})

    merged_table_data: list[dict] = []

    for entry in all_blocks:
        block = entry["block"]
        if block.block_type != "table" or not isinstance(block.raw_content, list):
            continue

        curr_rows = block.raw_content
        page_no = entry["page_number"]

        if not merged_table_data:
            merged_table_data.append(
                {
                    "rows": list(curr_rows),
                    "row_pages": [page_no] * len(curr_rows),
                    "pages": [page_no],
                    "block": block,
                    "merge_log": [{"action": "start", "page": page_no, "rows": len(curr_rows)}],
                }
            )
            continue

        prev = merged_table_data[-1]
        prev_rows = prev["rows"]
        first_row = curr_rows[0] if curr_rows else []
        is_header = _is_header_row(first_row)

        prev_col_count = _median_col_count(prev_rows)
        curr_col_count = _median_col_count(curr_rows)
        col_count_mismatch = abs(prev_col_count - curr_col_count) > 1

        if col_count_mismatch:
            max_cc = max(prev_col_count, curr_col_count, 1)
            min_cc = min(prev_col_count, curr_col_count)
            ratio = min_cc / max_cc
            if ratio < 0.5:
                logger.warning(
                    "[TableMerger] quarantine col-mismatch page "
                    "%s (%s cols vs expected %s) — standalone table preserved",
                    page_no,
                    curr_col_count,
                    prev_col_count,
                )
                merged_table_data.append(
                    {
                        "rows": list(curr_rows),
                        "row_pages": [page_no] * len(curr_rows),
                        "pages": [page_no],
                        "block": block,
                        "merge_log": [
                            {
                                "action": "quarantine_col_mismatch",
                                "page": page_no,
                                "rows": len(curr_rows),
                                "prev_cols": prev_col_count,
                                "curr_cols": curr_col_count,
                            }
                        ],
                    }
                )
                continue
            merged_table_data.append(
                {
                    "rows": list(curr_rows),
                    "row_pages": [page_no] * len(curr_rows),
                    "pages": [page_no],
                    "block": block,
                    "merge_log": [{"action": "start", "page": page_no, "rows": len(curr_rows)}],
                }
            )
        elif is_header and prev_rows:
            prev_header = prev_rows[0] if prev_rows else []
            if headers_match(prev_header, first_row):
                added = curr_rows[1:]
                prev["rows"].extend(added)
                prev.setdefault("row_pages", [prev["pages"][0]] * len(prev_rows))
                prev["row_pages"].extend([page_no] * len(added))
                prev["pages"].append(page_no)
                prev["merge_log"].append(
                    {"action": "merge_header_page", "page": page_no, "rows_added": max(len(curr_rows) - 1, 0)}
                )
            else:
                merged_table_data.append(
                    {
                        "rows": list(curr_rows),
                        "row_pages": [page_no] * len(curr_rows),
                        "pages": [page_no],
                        "block": block,
                        "merge_log": [{"action": "start", "page": page_no, "rows": len(curr_rows)}],
                    }
                )
        elif not is_header and prev_rows:
            confirmed_hdr = prev_rows[0] if prev_rows else []
            stripped = _strip_preamble(list(curr_rows), confirmed_hdr)
            stripped = [r for r in stripped if any((c or "").strip() for c in r)]
            if stripped:
                prev.setdefault("row_pages", [prev["pages"][0]] * len(prev_rows))
                prev["rows"].extend(stripped)
                prev["row_pages"].extend([page_no] * len(stripped))
                prev["pages"].append(page_no)
                prev["merge_log"].append(
                    {"action": "merge_continuation", "page": page_no, "rows_added": len(stripped)}
                )
        else:
            merged_table_data.append(
                {
                    "rows": list(curr_rows),
                    "row_pages": [page_no] * len(curr_rows),
                    "pages": [page_no],
                    "block": block,
                    "merge_log": [{"action": "start", "page": page_no, "rows": len(curr_rows)}],
                }
            )

    for mdata in merged_table_data:
        if len(mdata["pages"]) > 1:
            logger.info(
                "[TableMerger] F-7 audit: merged %d pages → %d rows (table starts page %s)",
                len(mdata["pages"]),
                len(mdata["rows"]),
                mdata["pages"][0],
            )

    return merged_table_data


def merge_cross_page_tables(pages: list[PageLayout]) -> list[PageLayout]:
    """Cross-page table merging — operates at the Block level.

    .. deprecated::
        Prefer ``TableComposer.from_page_layouts()`` + dual-view mode.
        This destructive merge mutates physical pages and will be removed.

    Args:
        pages: List of PageLayout objects for all pages.

    Returns:
        PageLayout list with cross-page tables merged.
    """
    import warnings

    warnings.warn(
        "merge_cross_page_tables() is deprecated; use TableComposer dual-view instead",
        DeprecationWarning,
        stacklevel=2,
    )
    if len(pages) <= 1:
        return pages

    all_blocks = []
    for page in pages:
        for block in page.blocks:
            all_blocks.append(
                {
                    "block": block,
                    "page_number": page.page_number,
                }
            )

    merged_table_data = collect_cross_page_merge_groups(pages)
    non_table_blocks: list[dict] = [
        entry
        for entry in all_blocks
        if entry["block"].block_type != "table"
        or not isinstance(entry["block"].raw_content, list)
    ]

    new_pages = []
    for page in pages:
        page_blocks: list[Block] = []
        for entry in non_table_blocks:
            if entry["page_number"] == page.page_number:
                page_blocks.append(entry["block"])

        for mdata in merged_table_data:
            if mdata["pages"][0] == page.page_number:
                original = mdata["block"]
                merged_block = Block(
                    block_id=original.block_id,
                    block_type="table",
                    bbox=original.bbox,
                    reading_order=original.reading_order,
                    page=original.page,
                    raw_content=mdata["rows"],
                )
                page_blocks.append(merged_block)

        page_blocks.sort(key=lambda b: b.reading_order)

        new_page = PageLayout(
            page_number=page.page_number,
            width=page.width,
            height=page.height,
            blocks=tuple(page_blocks),
            semantic_zones=page.semantic_zones,
            is_scanned=page.is_scanned,
        )
        new_pages.append(new_page)

    return new_pages


def collect_quarantined_tables(pages: list[PageLayout]) -> list[dict]:
    """Collect quarantine records from cross-page merge planning (P3-2).

    Each entry describes a physical table kept standalone because column counts
    were incompatible with the preceding merge group (ratio < 0.5).
    """
    groups = collect_cross_page_merge_groups(pages)
    quarantined: list[dict] = []
    for group in groups:
        for entry in group.get("merge_log") or []:
            if entry.get("action") != "quarantine_col_mismatch":
                continue
            quarantined.append(
                {
                    "page": entry.get("page"),
                    "row_count": entry.get("rows"),
                    "reason": "col_count_mismatch",
                    "prev_cols": entry.get("prev_cols"),
                    "curr_cols": entry.get("curr_cols"),
                    "action": "standalone_physical_table",
                }
            )
    return quarantined
