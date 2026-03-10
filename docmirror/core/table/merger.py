"""
table_merger — 跨页TableMerge
=============================

从 ``CoreExtractor._merge_cross_page_tables`` Extract的独立Module。
负责Detect内容连续的跨页Table并将它们Merge为单一 Block。

Merge策略:
  1. 下一页Table首行是Table header (且与上一页Table headerMatch) → Skip重复Table header直接MergeData
  2. 首行notTable header (续 table页) → ``_strip_preamble`` 剥离汇总行/重复Table header行后Merge
  3. 完全异 table (Table header不Match) → 当作独立Table
"""

from __future__ import annotations

import logging
from typing import Dict, List

from ...models.domain import Block, PageLayout
from .postprocess import _strip_preamble
from ..utils.text_utils import headers_match
from ..utils.vocabulary import _is_header_row

logger = logging.getLogger(__name__)


def _median_col_count(rows: list) -> int:
    """P3-6: CalculateTable行的中位列数。"""
    if not rows:
        return 0
    counts = sorted(len(r) for r in rows if isinstance(r, (list, tuple)))
    if not counts:
        return 0
    return counts[len(counts) // 2]


def merge_cross_page_tables(pages: List[PageLayout]) -> List[PageLayout]:
    """跨页TableMerge — Block 级别。

    Args:
        pages: allPage的 PageLayout List。

    Returns:
        Merge后的 PageLayout List。
    """
    if len(pages) <= 1:
        return pages

    all_blocks = []
    for page in pages:
        for block in page.blocks:
            all_blocks.append({
                "block": block,
                "page_number": page.page_number,
            })

    merged_table_data: List[Dict] = []
    non_table_blocks: List[Dict] = []

    for entry in all_blocks:
        block = entry["block"]
        if block.block_type != "table" or not isinstance(block.raw_content, list):
            non_table_blocks.append(entry)
            continue

        curr_rows = block.raw_content

        if not merged_table_data:
            merged_table_data.append({
                "rows": list(curr_rows),
                "pages": [entry["page_number"]],
                "block": block,
            })
            continue

        prev = merged_table_data[-1]
        prev_rows = prev["rows"]

        first_row = curr_rows[0] if curr_rows else []
        is_header = _is_header_row(first_row)

        # P3-6: 列数Verify — prevent不同Table误Merge
        prev_col_count = _median_col_count(prev_rows)
        curr_col_count = _median_col_count(curr_rows)
        col_count_mismatch = abs(prev_col_count - curr_col_count) > 1

        if col_count_mismatch:
            # 列数Ratio判断: ratio < 0.5 视为Extraction failed (Skip, 不打断链)
            max_cc = max(prev_col_count, curr_col_count, 1)
            min_cc = min(prev_col_count, curr_col_count)
            ratio = min_cc / max_cc
            if ratio < 0.5:
                logger.warning(
                    f"[TableMerger] skipped extraction-failed table on page "
                    f"{entry['page_number']} ({curr_col_count} cols vs "
                    f"expected {prev_col_count})"
                )
                continue  # Skip, 不打断Merge链
            # 列数相近但不同 → 视为独立Table
            merged_table_data.append({
                "rows": list(curr_rows),
                "pages": [entry["page_number"]],
                "block": block,
            })
        elif is_header and prev_rows:
            prev_header = prev_rows[0] if prev_rows else []
            if headers_match(prev_header, first_row):
                prev["rows"].extend(curr_rows[1:])
                prev["pages"].append(entry["page_number"])
            else:
                merged_table_data.append({
                    "rows": list(curr_rows),
                    "pages": [entry["page_number"]],
                    "block": block,
                })
        elif not is_header and prev_rows:
            # 续 table: 剥离本页开头的汇总行/重复Table header行, 再Merge
            confirmed_hdr = prev_rows[0] if prev_rows else []
            stripped = _strip_preamble(list(curr_rows), confirmed_hdr)
            stripped = [r for r in stripped if any((c or "").strip() for c in r)]
            if stripped:
                prev["rows"].extend(stripped)
                prev["pages"].append(entry["page_number"])
        else:
            merged_table_data.append({
                "rows": list(curr_rows),
                "pages": [entry["page_number"]],
                "block": block,
            })

    # F-7: Merge后行数审计
    for mdata in merged_table_data:
        if len(mdata["pages"]) > 1:
            merged_rows = len(mdata["rows"])
            logger.info(
                f"[TableMerger] F-7 audit: merged {len(mdata['pages'])} pages → "
                f"{merged_rows} rows (table starts page {mdata['pages'][0]})"
            )

    new_pages = []
    for page in pages:
        page_blocks: List[Block] = []
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
