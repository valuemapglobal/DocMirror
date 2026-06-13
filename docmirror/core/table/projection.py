# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Projection Histogram Table Detection - T-11
=============================================

基于 X 轴投影直方图的列检测算法,作为 Column Consensus 的增强替代方案。

优势:
- 不受单元格空白影响
- 对噪声更鲁棒
- 适用于复杂无边框表格

Algorithm:
  1. 按 y 分组字符 (行检测)
  2. 对每行计算 X 轴投影直方图
  3. 检测直方图谷值 (列边界)
  4. 验证列一致性 (多行共享相同列边界)
  5. 返回表格结构和列位置

Design principles:
    - Pure functions, no state, no side effects.
    - Works as fallback when gap-based clustering fails.
    - Compatible with existing Column Consensus interface.
"""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. X 轴投影直方图计算
# ═══════════════════════════════════════════════════════════════════════════════

def compute_x_projection(
    chars: list[dict],
    page_w: float,
    bin_size: float = 2.0
) -> list[int]:
    """T-11: 计算 X 轴投影直方图。
    
    Args:
        chars: 字符列表
        page_w: 页面宽度
        bin_size: 直方图 bin 大小 (px),默认 2px
    
    Returns:
        投影直方图数组,每个元素表示该 x 位置的字符数
    """
    if not chars or page_w <= 0:
        logger.debug("[projection] compute_x_projection: empty input or invalid page_w")
        return []

    # 初始化直方图
    num_bins = int(page_w / bin_size) + 1
    histogram = [0] * num_bins

    # 填充直方图
    for c in chars:
        x0 = c.get("x0", 0)
        x1 = c.get("x1", x0)

        # 字符覆盖的 bin 范围
        bin_start = int(x0 / bin_size)
        bin_end = int(x1 / bin_size)

        # 在范围内 +1
        for bin_idx in range(bin_start, min(bin_end + 1, num_bins)):
            histogram[bin_idx] += 1

    return histogram


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 列边界检测
# ═══════════════════════════════════════════════════════════════════════════════

def detect_column_boundaries(
    projection: list[int],
    min_valley_depth: float = 0.3,
    min_column_width: float = 20.0,
    bin_size: float = 2.0
) -> list[int]:
    """T-11: 从投影直方图检测列边界。
    
    Args:
        projection: X 轴投影直方图
        min_valley_depth: 最小谷值深度 (相对峰值的比率)
        min_column_width: 最小列宽度 (px)
        bin_size: 直方图 bin 大小 (px)
    
    Returns:
        列边界位置列表 (px 坐标)
    """
    if not projection or len(projection) < 10:
        logger.debug(f"[projection] detect_column_boundaries: projection too short ({len(projection) if projection else 0} bins)")
        return []

    # Step 1: 平滑直方图 (移动平均,窗口大小=5)
    smoothed = _smooth_projection(projection, window_size=5)

    # Step 2: 找到全局最大值
    max_val = max(smoothed)
    if max_val == 0:
        logger.debug("[projection] detect_column_boundaries: max value is 0 (empty projection)")
        return []

    # Step 3: 检测局部最小值 (valleys)
    valleys = []
    for i in range(1, len(smoothed) - 1):
        if smoothed[i] < smoothed[i - 1] and smoothed[i] < smoothed[i + 1]:
            # 检查谷值深度
            depth = 1.0 - (smoothed[i] / max_val)
            if depth >= min_valley_depth:
                valleys.append(i)

    # Step 4: 过滤: 列宽度 < min_column_width
    min_bin_width = int(min_column_width / bin_size)
    filtered_valleys = [valleys[0]] if valleys else []

    for i in range(1, len(valleys)):
        if valleys[i] - filtered_valleys[-1] >= min_bin_width:
            filtered_valleys.append(valleys[i])

    # Step 5: 转换为 px 坐标
    boundaries = [v * bin_size for v in filtered_valleys]

    logger.debug(
        f"[Projection] Detected {len(boundaries)} column boundaries "
        f"(valley depth threshold={min_valley_depth})"
    )

    return boundaries


def _smooth_projection(projection: list[int], window_size: int = 5) -> list[float]:
    """平滑投影直方图 (移动平均)。"""
    if not projection:
        return []

    smoothed = []
    half_w = window_size // 2

    for i in range(len(projection)):
        # 窗口范围
        start = max(0, i - half_w)
        end = min(len(projection), i + half_w + 1)

        # 计算平均值
        window = projection[start:end]
        avg = sum(window) / len(window)
        smoothed.append(avg)

    return smoothed


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 字符分配到列
# ═══════════════════════════════════════════════════════════════════════════════

def assign_chars_to_columns(
    chars: list[dict],
    column_boundaries: list[float],
    page_w: float
) -> dict[int, list[dict]]:
    """T-11: 将字符分配到对应的列。
    
    Args:
        chars: 字符列表
        column_boundaries: 列边界位置列表 (px)
        page_w: 页面宽度
    
    Returns:
        {col_index: [chars]}
    """
    if not chars or not column_boundaries:
        return {}

    # 添加起始和结束边界
    boundaries = [0.0] + sorted(column_boundaries) + [page_w]

    # 分配字符
    columns: dict[int, list[dict]] = defaultdict(list)

    for c in chars:
        x_mid = (c.get("x0", 0) + c.get("x1", 0)) / 2

        # 找到 x_mid 所在的列区间
        for col_idx in range(len(boundaries) - 1):
            if boundaries[col_idx] <= x_mid < boundaries[col_idx + 1]:
                columns[col_idx].append(c)
                break

    logger.debug(f"[Projection] Assigned chars to {len(columns)} columns")
    return dict(columns)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 统一入口: 表格检测
# ═══════════════════════════════════════════════════════════════════════════════

def detect_table_by_projection(
    chars: list[dict],
    page_w: float,
    page_h: float,
    min_rows: int = 3,
    min_cols: int = 2
) -> tuple | None:
    """T-11: 使用投影直方图检测表格结构。
    
    Algorithm:
      1. 按 y 分组字符 (行检测)
      2. 对每组计算 X 投影
      3. 检测列边界
      4. 验证: 行数 >= min_rows, 列数 >= min_cols
      5. 返回表格边界和列位置
    
    Args:
        chars: 字符列表
        page_w: 页面宽度
        page_h: 页面高度
        min_rows: 最小行数
        min_cols: 最小列数
    
    Returns:
        (y_top, y_bottom, [col_x_positions]) 或 None
    """
    if not chars or page_w <= 0 or page_h <= 0:
        return None

    # Step 1: 按 y 分组字符
    y_bin = 3.0
    y_groups: dict[int, list] = defaultdict(list)

    for c in chars:
        y_mid = (c.get("top", 0) + c.get("bottom", 0)) / 2
        y_key = round(y_mid / y_bin) * y_bin
        y_groups[y_key].append(c)

    if len(y_groups) < min_rows:
        return None

    # Step 2: 对所有字符计算 X 投影
    all_x_projection = compute_x_projection(chars, page_w, bin_size=2.0)

    if not all_x_projection:
        return None

    # Step 3: 检测列边界
    column_boundaries = detect_column_boundaries(
        all_x_projection,
        min_valley_depth=0.3,
        min_column_width=20.0,
        bin_size=2.0
    )

    if len(column_boundaries) < min_cols - 1:  # n 列需要 n-1 个边界
        return None

    # Step 4: 计算列中心位置
    boundaries = [0.0] + sorted(column_boundaries) + [page_w]
    col_positions = []

    for i in range(len(boundaries) - 1):
        col_center = (boundaries[i] + boundaries[i + 1]) / 2
        col_positions.append(col_center)

    if len(col_positions) < min_cols:
        return None

    # Step 5: 验证行一致性 (检查多行是否都有相同数量的列)
    row_cell_counts = []

    for y_key in sorted(y_groups.keys()):
        row_chars = y_groups[y_key]
        if len(row_chars) < 2:
            continue

        # 分配字符到列
        row_columns = assign_chars_to_columns(row_chars, column_boundaries, page_w)

        # 计算有字符的列数
        non_empty_cols = sum(1 for cols in row_columns.values() if cols)
        if non_empty_cols >= min_cols:
            row_cell_counts.append(non_empty_cols)

    # 检查是否有足够的行具有一致的列数
    if len(row_cell_counts) < min_rows:
        return None

    # 验证列数一致性 (允许 ±1 的误差)
    if max(row_cell_counts) - min(row_cell_counts) > 1:
        logger.debug(
            f"[Projection] Column count inconsistent: {row_cell_counts}"
        )
        return None

    # Step 6: 计算表格边界
    y_top = min(y_groups.keys())
    y_bottom = max(y_groups.keys())

    logger.info(
        f"[Projection] Table detected: {len(row_cell_counts)} rows × "
        f"{len(col_positions)} cols (y={y_top:.0f}-{y_bottom:.0f})"
    )

    return (y_top, y_bottom, col_positions)


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数: 与 Column Consensus 集成
# ═══════════════════════════════════════════════════════════════════════════════

def projection_fallback(
    chars: list[dict],
    page_w: float,
    page_h: float,
    min_rows: int = 3,
    min_cols: int = 2
) -> tuple | None:
    """T-11: 投影直方图备选方案入口。
    
    当 gap-based clustering 失败时调用此函数。
    
    Returns:
        (y_top, y_bottom, [col_x_positions]) 或 None
    """
    try:
        return detect_table_by_projection(chars, page_w, page_h, min_rows, min_cols)
    except Exception as e:
        logger.warning(f"[Projection] Fallback failed: {e}")
        return None
