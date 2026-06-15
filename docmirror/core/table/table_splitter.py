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
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════════════════════════════

# 最小垂直间隙阈值（pt）- 超过此值认为是列边界
MIN_VERTICAL_GAP = 30.0

# 征信报告右侧固定列模式
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

    # 获取列数
    col_count = max(len(row) for row in table_data)

    # 至少需要4列才考虑分割（左右各2列）
    if col_count < 4:
        return [{"table_data": table_data, "table_id": table_id, "split_reason": None}]

    # Step 1: 估算列的X坐标（基于列索引和页面宽度）
    if page_width > 0:
        col_x_positions = _estimate_column_positions(table_data, page_width)
    else:
        # 如果没有页面宽度，使用列索引
        col_x_positions = list(range(col_count))

    # Step 2: 检测垂直间隙（基于列间距）
    gaps = _find_column_gaps(col_x_positions, table_data)

    if not gaps:
        return [{"table_data": table_data, "table_id": table_id, "split_reason": None}]

    # Step 3: 验证间隙是否为语义分割点
    valid_gaps = []
    for gap_idx in gaps:
        if _is_semantic_boundary(table_data, gap_idx):
            valid_gaps.append(gap_idx)

    if not valid_gaps:
        return [{"table_data": table_data, "table_id": table_id, "split_reason": None}]

    # Step 4: 执行分割
    split_tables = []
    for gap_idx in valid_gaps:
        # 左侧表格（0 到 gap_idx-1）
        left_data = _extract_columns(table_data, 0, gap_idx)
        left_id = f"{table_id}_left" if table_id else "table_left"

        split_tables.append({
            "table_data": left_data,
            "table_id": left_id,
            "split_reason": f"semantic_boundary_at_col_{gap_idx}",
        })

        # 右侧表格（gap_idx 到末尾）
        right_data = _extract_columns(table_data, gap_idx, col_count)
        right_id = f"{table_id}_right" if table_id else "table_right"

        split_tables.append({
            "table_data": right_data,
            "table_id": right_id,
            "split_reason": f"semantic_boundary_at_col_{gap_idx}",
        })

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

    # 假设表格占页面宽度的80%，左右各留10%边距
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

    # 征信报告特征：4列表格通常在中间分割（2|2）
    # 直接检查列索引2前面是否有语义边界
    gaps = []

    # 启发式规则：检查第2列和第3列之间是否有"信息来源机构"
    if table_data:
        for row_idx, row in enumerate(table_data):
            if len(row) >= 3:
                # 检查第3列（索引2）是否包含"信息来源机构"
                cell_content = str(row[2]).strip()
                if "信息来源机构" in cell_content:
                    gaps.append(2)  # 在索引2前面分割
                    logger.debug(f"[ColumnGap] Found '信息来源机构' at row {row_idx}, col 2")
                    break

    return gaps


def _is_semantic_boundary(table_data: list[list[str]], gap_col_idx: int) -> bool:
    """
    验证间隙是否为语义分割点
    
    征信报告特征:
    - 左侧是业务字段（经济类型、组织机构类型等）
    - 右侧固定是"信息来源机构"
    """
    # 检查右侧列是否包含"信息来源机构"等模式
    right_headers = []
    if table_data:
        right_headers = [str(cell).strip() for cell in table_data[0][gap_col_idx:]]

    for pattern in RIGHT_COLUMN_PATTERNS:
        if any(pattern in header for header in right_headers):
            logger.debug(f"[SemanticBoundary] Found pattern '{pattern}' in right columns")
            return True

    # 通用规则：两侧都有完整的KV结构
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

    # 检查第一行（header行）
    header_row = table_data[0] if table_data else []
    label_count = 0

    for col_idx in col_range[::2]:  # 检查偶数列
        if col_idx < len(header_row):
            cell = str(header_row[col_idx]).strip()
            # 包含中文且长度适中（2-20字符）
            if _has_chinese(cell) and 2 <= len(cell) <= 20:
                label_count += 1

    # 如果至少有一个标签，认为有KV结构
    return label_count > 0


def _has_chinese(text: str) -> bool:
    """检查文本是否包含中文"""
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False


def _extract_columns(table_data: list[list[str]], start_col: int, end_col: int) -> list[list[str]]:
    """
    提取指定列范围的数据
    
    Args:
        table_data: 原始表格数据
        start_col: 起始列索引（包含）
        end_col: 结束列索引（不包含）
    
    Returns:
        提取后的表格数据
    """
    extracted = []
    for row in table_data:
        extracted_row = row[start_col:end_col]
        # 填充空单元格以保持列数一致
        while len(extracted_row) < (end_col - start_col):
            extracted_row.append("")
        extracted.append(extracted_row)

    return extracted
