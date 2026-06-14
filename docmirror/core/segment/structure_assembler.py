# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Structure Assembler — 结构组装器
=================================

基于第一性原理的结构组装：将负空间和对齐特征组装成表格。

Design Principle (道德经):
    "道生一，一生二，二生三，三生万物" — 从简单特征组装成复杂结构。

Core Philosophy:
    列边界 + 行边界 = 网格
    视觉分组 = 表格区域
    层级推断 = 表头/数据区分

Usage::

    from docmirror.core.layout.structure_assembler import StructureAssembler

    # 组装隐式表格
    tables = StructureAssembler.assemble_implicit_tables(
        words=page_words,
        neg_space=profile,
        alignment=alignment_info
    )
    # tables = [[['日期', '金额', '余额'], ['1/15', '1000', '5000'], ...]]
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from .negative_space import NegativeSpaceProfile

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Structure Assembler
# ═══════════════════════════════════════════════════════════════════════════════


class StructureAssembler:
    """
    结构组装器 — 将负空间和对齐特征组装成表格

    核心思想：
        - 列边界 + 行边界 = 网格
        - 视觉分组 = 表格区域
        - 层级推断 = 表头/数据区分

    组装流程：
        1. 构建网格（将单词分配到单元格）
        2. 识别表头行
        3. 验证表格质量
        4. 输出结构化表格
    """

    @classmethod
    def assemble_implicit_tables(
        cls,
        words: list[dict],
        neg_space: NegativeSpaceProfile,
        alignment_info: dict | None = None,
        min_rows: int = 2,
        min_cols: int = 2,
    ) -> list[list[list[str]]]:
        """
        组装隐式表格

        Args:
            words: 单词列表
            neg_space: 负空间特征
            alignment_info: 对齐信息（可选）
            min_rows: 最小行数
            min_cols: 最小列数

        Returns:
            表格列表 [[[cell, cell, ...], ...], ...]
        """
        if not words or not neg_space.column_gaps:
            return []

        try:
            # 1. 构建网格
            grid = cls._build_grid(words, neg_space.column_gaps, neg_space.row_gaps)

            if not grid or len(grid) < min_rows or len(grid[0]) < min_cols:
                return []

            # 2. 识别表头行
            header_idx = cls._identify_header_row(grid, words)

            # 3. 验证表格质量
            quality_score = cls._validate_table_quality(grid, header_idx, words)

            if quality_score < 0.5:
                logger.debug(f"[StructureAssembler] Table quality too low: {quality_score:.2f}")
                return []

            logger.debug(
                f"[StructureAssembler] Assembled table: "
                f"{len(grid)} rows x {len(grid[0])} cols, "
                f"quality={quality_score:.2f}, header={header_idx}"
            )

            return [grid]

        except Exception as e:
            logger.warning(f"[StructureAssembler] Assembly failed: {e}")
            return []

    @classmethod
    def _build_grid(
        cls, words: list[dict], col_boundaries: list[float], row_boundaries: list[float]
    ) -> list[list[str]]:
        """
        构建网格（将单词分配到单元格）

        Args:
            words: 单词列表
            col_boundaries: 列边界位置
            row_boundaries: 行边界位置

        Returns:
            网格 [[cell, cell, ...], ...]
        """
        if not col_boundaries:
            return []

        # 创建空网格
        num_rows = len(row_boundaries) + 1 if row_boundaries else 1
        num_cols = len(col_boundaries) + 1

        # 初始化为空字符串
        grid = [["" for _ in range(num_cols)] for _ in range(num_rows)]

        for word in words:
            word_text = word.get("text", "").strip()
            if not word_text:
                continue

            # 找到所属列
            col_idx = cls._find_cell_index(word.get("x0", 0), col_boundaries)
            # 找到所属行
            row_idx = cls._find_cell_index(word.get("y0", 0), row_boundaries) if row_boundaries else 0

            # 分配到单元格
            if 0 <= row_idx < num_rows and 0 <= col_idx < num_cols:
                if grid[row_idx][col_idx]:
                    grid[row_idx][col_idx] += " " + word_text
                else:
                    grid[row_idx][col_idx] = word_text

        return grid

    @classmethod
    def _find_cell_index(cls, position: float, boundaries: list[float]) -> int:
        """
        查找位置所属的单元格索引

        Args:
            position: 位置坐标
            boundaries: 边界列表（已排序）

        Returns:
            单元格索引
        """
        if not boundaries:
            return 0

        for i, boundary in enumerate(boundaries):
            if position < boundary:
                return i

        # 超过所有边界，属于最后一个单元格
        return len(boundaries)

    @classmethod
    def _identify_header_row(cls, grid: list[list[str]], words: list[dict]) -> int:
        """
        识别表头行

        策略：
        1. 第一行通常是表头
        2. 检查第一行是否有表头特征（短文本、大写、关键词）
        3. 如果第一行像数据，返回-1（无表头）

        Args:
            grid: 网格数据
            words: 原始单词列表

        Returns:
            表头行索引，-1表示无表头
        """
        if not grid or len(grid) < 2:
            return 0

        first_row = grid[0]

        # 特征1：表头通常是短文本
        avg_length = np.mean([len(cell) for cell in first_row if cell])
        if avg_length > 30:  # 太长，不像表头
            return -1

        # 特征2：表头可能包含关键词
        header_keywords = ["日期", "金额", "余额", "摘要", "name", "date", "amount", "total"]
        header_count = sum(1 for cell in first_row if any(kw in cell.lower() for kw in header_keywords))

        if header_count >= len(first_row) * 0.5:  # 50%以上包含关键词
            return 0

        # 特征3：第一行与数据行格式不同
        if len(grid) >= 3:
            second_row = grid[1]
            # 检查是否有明显差异（如第二行包含数字）
            has_numbers_in_data = any(any(c.isdigit() for c in cell) for cell in second_row)
            has_no_numbers_in_header = not any(any(c.isdigit() for c in cell) for cell in first_row)

            if has_numbers_in_data and has_no_numbers_in_header:
                return 0

        # 默认第一行为表头
        return 0

    @classmethod
    def _validate_table_quality(cls, grid: list[list[str]], header_idx: int, words: list[dict]) -> float:
        """
        验证表格质量

        评分维度：
        1. 填充度（非空单元格比例）
        2. 列一致性（每列数据格式相似）
        3. 行一致性（每行字段数相同）
        4. 表头质量

        Args:
            grid: 网格数据
            header_idx: 表头行索引
            words: 原始单词列表

        Returns:
            质量得分 0.0-1.0
        """
        if not grid:
            return 0.0

        scores = []

        # 1. 填充度
        total_cells = len(grid) * len(grid[0]) if grid else 0
        filled_cells = sum(1 for row in grid for cell in row if cell.strip())
        fill_rate = filled_cells / total_cells if total_cells > 0 else 0.0
        scores.append(fill_rate)

        # 2. 列一致性（检查每列是否有数据）
        col_scores = []
        for col_idx in range(len(grid[0])):
            col_data = [grid[row_idx][col_idx] for row_idx in range(len(grid))]
            non_empty = sum(1 for cell in col_data if cell.strip())
            col_scores.append(non_empty / len(col_data) if col_data else 0.0)
        scores.append(np.mean(col_scores) if col_scores else 0.0)

        # 3. 行一致性（检查每行是否有数据）
        row_scores = []
        for row in grid:
            non_empty = sum(1 for cell in row if cell.strip())
            row_scores.append(non_empty / len(row) if row else 0.0)
        scores.append(np.mean(row_scores) if row_scores else 0.0)

        # 4. 表头质量（如果有表头）
        if header_idx >= 0 and header_idx < len(grid):
            header = grid[header_idx]
            header_quality = sum(1 for cell in header if cell.strip() and len(cell) < 50)
            scores.append(header_quality / len(header) if header else 0.0)

        # 综合得分
        final_score = np.mean(scores) if scores else 0.0

        return min(1.0, max(0.0, final_score))

    @classmethod
    def detect_multiple_tables(
        cls, words: list[dict], neg_space: NegativeSpaceProfile, min_table_size: int = 6
    ) -> list[list[list[str]]]:
        """
        检测多个表格（基于空白区域分割）

        Args:
            words: 单词列表
            neg_space: 负空间特征
            min_table_size: 最小表格大小（单元格数）

        Returns:
            多个表格列表
        """
        if not neg_space.blank_regions:
            # 无空白区域，尝试整体组装
            return cls.assemble_implicit_tables(words, neg_space)

        # 按空白区域分割单词
        word_groups = cls._split_words_by_blank_regions(words, neg_space.blank_regions)

        all_tables = []
        for group_words in word_groups:
            if len(group_words) < min_table_size:
                continue

            # 为每个组重新分析负空间
            from .negative_space import NegativeSpaceAnalyzer

            group_neg_space = NegativeSpaceAnalyzer.analyze(group_words)

            tables = cls.assemble_implicit_tables(group_words, group_neg_space)
            all_tables.extend(tables)

        return all_tables

    @classmethod
    def _split_words_by_blank_regions(
        cls, words: list[dict], blank_regions: list[tuple[float, float, float, float]]
    ) -> list[list[dict]]:
        """
        根据空白区域分割单词

        Args:
            words: 单词列表
            blank_regions: 空白区域列表

        Returns:
            单词分组列表
        """
        # 简单实现：按垂直空白分割
        # 找到主要的垂直空白（贯穿整个页面的）
        page_height = max(w.get("y1", 0) for w in words) if words else 0

        vertical_blanks = []
        for x0, y0, x1, y1 in blank_regions:
            # 如果空白区域高度覆盖大部分页面，认为是垂直分割线
            if (y1 - y0) >= page_height * 0.8:
                vertical_blanks.append((x0 + x1) / 2.0)

        if not vertical_blanks:
            return [words]

        vertical_blanks.sort()

        # 按垂直空白分割单词
        groups = [[] for _ in range(len(vertical_blanks) + 1)]

        for word in words:
            word_x = (word.get("x0", 0) + word.get("x1", 0)) / 2.0

            # 找到所属组
            group_idx = 0
            for i, blank_x in enumerate(vertical_blanks):
                if word_x > blank_x:
                    group_idx = i + 1
                else:
                    break

            groups[group_idx].append(word)

        # 过滤空组
        return [g for g in groups if g]
