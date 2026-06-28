# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Table splitter — detects parallel side-by-side tables on one page.

Purpose: Finds column gaps and semantic boundaries to split a single wide
region into independent table blocks.

Main components: ``detect_and_split_parallel_tables``.

Upstream: Wide table zones or merged regions.

Downstream: Separate ``Block`` tables per ``page_assemble``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Configuration constants
# ═══════════════════════════════════════════════════════════════════════════

# Minimum vertical gap threshold (pt) - gaps above this are column boundaries
MIN_VERTICAL_GAP = 30.0

# Credit report right-side fixed column pattern
RIGHT_COLUMN_PATTERNS = [
    "信息来源机构",
    "更新日期",
    "信息提供机构",
]


def detect_and_split_parallel_tables(
    table_data: list[list[str]],
    page_width: float = 0.0,
    table_id: str = "",
    page_number: int = 0,
) -> list[dict]:
    """
    检测并分离并排表格

    Args:
        table_data: 表格数据 [[row1_col1, row1_col2, ...], ...]
        page_width: 页面宽度（用于计算相对位置）
        table_id: 原始表格ID
        page_number: 页码

    Returns:
        分割后的表格列表，每个元素包含:
        - table_data: 表格数据
        - table_id: 新表格ID
        - split_reason: 分割原因

    算法流程:
    1. 计算所有列的X轴分布
    2. 检测垂直空白间隙（>30pt）
    3. 验证间隙是否为语义分割点
    4. 执行分割
    """
    if not table_data or len(table_data) < 2:
        return [{"table_data": table_data, "table_id": table_id, "split_reason": None}]

    # Get column count
    col_count = max(len(row) for row in table_data)

    # Need at least 4 columns for split (2 left + 2 right)
    if col_count < 4:
        return [{"table_data": table_data, "table_id": table_id, "split_reason": None}]

    # Step 1: Estimate column X coordinates (based on index and page width)
    if page_width > 0:
        col_x_positions = _estimate_column_positions(table_data, page_width)
    else:
        # If no page width, use column index
        col_x_positions = list(range(col_count))

    # Step 2: Detect vertical gaps (based on column spacing)
    gaps = _find_column_gaps(col_x_positions, table_data)

    if not gaps:
        return [{"table_data": table_data, "table_id": table_id, "split_reason": None}]

    # Step 3: Validate if gap is a semantic split point
    valid_gaps = []
    for gap_idx in gaps:
        if _is_semantic_boundary(table_data, gap_idx):
            valid_gaps.append(gap_idx)

    if not valid_gaps:
        return [{"table_data": table_data, "table_id": table_id, "split_reason": None}]

    # Step 4: Execute split
    split_tables = []
    for gap_idx in valid_gaps:
        # Left table (0 to gap_idx-1)
        left_data = _extract_columns(table_data, 0, gap_idx)
        left_id = f"{table_id}_left" if table_id else "table_left"

        split_tables.append(
            {
                "table_data": left_data,
                "table_id": left_id,
                "split_reason": f"semantic_boundary_at_col_{gap_idx}",
            }
        )

        # Right table (gap_idx to end)
        right_data = _extract_columns(table_data, gap_idx, col_count)
        right_id = f"{table_id}_right" if table_id else "table_right"

        split_tables.append(
            {
                "table_data": right_data,
                "table_id": right_id,
                "split_reason": f"semantic_boundary_at_col_{gap_idx}",
            }
        )

        logger.info(
            f"[TableSplit] Page {page_number}: Split {table_id} into "
            f"{left_id} ({gap_idx} cols) and {right_id} ({col_count - gap_idx} cols)"
        )

    return split_tables


def _estimate_column_positions(table_data: list[list[str]], page_width: float) -> list[float]:
    """
    估算列的X坐标位置

    基于列索引和页面宽度均匀分布
    """
    col_count = max(len(row) for row in table_data)
    if col_count == 0:
        return []

    # Assume table occupies 80% of page width, with 10% margin on each side
    margin = page_width * 0.1
    table_width = page_width * 0.8
    col_width = table_width / col_count

    positions = []
    for i in range(col_count):
        positions.append(margin + i * col_width + col_width / 2)

    return positions


def _find_column_gaps(col_x_positions: list[float], table_data: list[list[str]]) -> list[int]:
    """
    查找列之间的间隙

    使用更简单直接的方法：检测列索引2（第3列）前面是否有间隙
    征信报告的并排表格通常在第2列和第3列之间分割

    Returns:
        间隙位置（列索引）列表
    """
    if len(col_x_positions) < 4:
        return []

    # Credit report feature: 4-column tables typically split at the middle (2|2)
    # Check directly if there is a semantic boundary before column index 2
    gaps = []

    # Heuristic: check whether "information source institution" appears between columns 2 and 3
    if table_data:
        for row_idx, row in enumerate(table_data):
            if len(row) >= 3:
                # Check if column 3 (index 2) contains "information source institution"
                cell_content = str(row[2]).strip()
                if "信息来源机构" in cell_content:
                    gaps.append(2)  # 在索引2前面分割
                    logger.debug(f"[ColumnGap] Found '信息来源机构' at row {row_idx}, col 2")
                    break

    return gaps


def _is_semantic_boundary(table_data: list[list[str]], gap_col_idx: int) -> bool:
    """
    Verify whether a gap is a semantic split point.

    Credit report characteristics:
    - Left side has business fields (economic type, organizational type, etc.)
    - Right side is always "information source institution"
    """
    # Check if right-side columns contain "information source institution" or similar patterns
    right_headers = []
    if table_data:
        right_headers = [str(cell).strip() for cell in table_data[0][gap_col_idx:]]

    for pattern in RIGHT_COLUMN_PATTERNS:
        if any(pattern in header for header in right_headers):
            logger.debug(f"[SemanticBoundary] Found pattern '{pattern}' in right columns")
            return True

    # General rule: both sides have complete KV structure
    left_has_kv = _has_kv_structure(table_data, 0, gap_col_idx)
    right_has_kv = _has_kv_structure(table_data, gap_col_idx, None)

    if left_has_kv and right_has_kv:
        logger.debug("[SemanticBoundary] Both sides have KV structure")
        return True

    return False


def _has_kv_structure(table_data: list[list[str]], start_col: int, end_col: int | None) -> bool:
    """
    检查指定列范围是否具有KV结构

    KV结构特征:
    - 偶数索引列是标签（包含中文）
    - 奇数索引列是值
    """
    if not table_data:
        return False

    col_end = end_col if end_col is not None else max(len(row) for row in table_data)
    col_range = list(range(start_col, col_end))

    if len(col_range) < 2:
        return False

    # Check first row (header row)
    header_row = table_data[0] if table_data else []
    label_count = 0

    for col_idx in col_range[::2]:  # 检查偶数列
        if col_idx < len(header_row):
            cell = str(header_row[col_idx]).strip()
            # contains Chinese characters and medium length (2-20 chars)
            if _has_chinese(cell) and 2 <= len(cell) <= 20:
                label_count += 1

    # at least one tag found — treat as KV structure
    return label_count > 0


def _has_chinese(text: str) -> bool:
    """Check if text contains Chinese characters."""
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            return True
    return False


def _extract_columns(table_data: list[list[str]], start_col: int, end_col: int) -> list[list[str]]:
    """
    Extract data for a specified column range.

    Args:
        table_data: Raw table data
        start_col: Start column index (inclusive)
        end_col: End column index (exclusive)

    Returns:
        Extracted table data
    """
    extracted = []
    for row in table_data:
        extracted_row = row[start_col:end_col]
        # Fill empty cells to maintain consistent column count
        while len(extracted_row) < (end_col - start_col):
            extracted_row.append("")
        extracted.append(extracted_row)

    return extracted
