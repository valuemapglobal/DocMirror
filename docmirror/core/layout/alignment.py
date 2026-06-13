# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Alignment Inferrer — 对齐推断器
================================

基于第一性原理的对齐感知：从"对齐"中推断结构。

Design Principle (道德经):
    "道生一，一生二，二生三，三生万物" — 从简单对齐规律推导复杂结构。

Core Philosophy:
    垂直对齐的单词 → 同一列
    水平对齐的单词 → 同一行
    对齐规律 = 表格结构

Usage::

    from docmirror.core.layout.alignment import AlignmentInferrer

    # 从垂直对齐推断列
    columns = AlignmentInferrer.infer_columns(page_words)
    # [[word1, word2, ...], [word3, word4, ...], ...]

    # 从水平对齐推断行
    rows = AlignmentInferrer.infer_rows(page_words)
    # [[word1, word3, ...], [word2, word4, ...], ...]
"""

from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Alignment Inferrer
# ═══════════════════════════════════════════════════════════════════════════════


class AlignmentInferrer:
    """
    对齐推断器 — 从"对齐"中推断结构

    核心思想：
        - 垂直对齐的单词 → 同一列
        - 水平对齐的单词 → 同一行
        - 对齐规律 = 表格结构

    算法：
        1. 按坐标排序
        2. 容差内聚类（DBSCAN简化版）
        3. 输出分组
    """

    @classmethod
    def infer_columns(cls, words: list[dict], tolerance: float = 5.0, min_words_per_col: int = 2) -> list[list[dict]]:
        """
        从垂直对齐推断列

        Args:
            words: 单词列表
            tolerance: 对齐容差（像素）
            min_words_per_col: 每列最少单词数

        Returns:
            列分组列表 [[word1, word2, ...], [...], ...]
        """
        if not words or len(words) < 2:
            return [words] if words else []

        # 1. 按x0位置排序
        sorted_words = sorted(words, key=lambda w: w.get("x0", 0))

        # 2. 聚类x0位置（容差内视为同一列）
        columns = []
        current_col = [sorted_words[0]]
        current_x = sorted_words[0].get("x0", 0)

        for word in sorted_words[1:]:
            word_x = word.get("x0", 0)

            if abs(word_x - current_x) <= tolerance:
                # 属于当前列
                current_col.append(word)
                # 更新列中心（加权平均）
                current_x = np.mean([w.get("x0", 0) for w in current_col])
            else:
                # 新列
                if len(current_col) >= min_words_per_col:
                    columns.append(current_col)
                current_col = [word]
                current_x = word_x

        # 添加最后一列
        if current_col and len(current_col) >= min_words_per_col:
            columns.append(current_col)

        logger.debug(f"[AlignmentInferrer] Detected {len(columns)} columns")

        return columns

    @classmethod
    def infer_rows(cls, words: list[dict], tolerance: float = 3.0, min_words_per_row: int = 1) -> list[list[dict]]:
        """
        从水平对齐推断行

        Args:
            words: 单词列表
            tolerance: 行高容差（像素）
            min_words_per_row: 每行最少单词数

        Returns:
            行分组列表
        """
        if not words:
            return []

        # 1. 按y0位置排序
        sorted_words = sorted(words, key=lambda w: w.get("y0", 0))

        # 2. 聚类y0位置
        rows = []
        current_row = [sorted_words[0]]
        current_y = sorted_words[0].get("y0", 0)

        for word in sorted_words[1:]:
            word_y = word.get("y0", 0)

            if abs(word_y - current_y) <= tolerance:
                # 属于当前行
                current_row.append(word)
                # 更新行中心
                current_y = np.mean([w.get("y0", 0) for w in current_row])
            else:
                # 新行
                if len(current_row) >= min_words_per_row:
                    rows.append(current_row)
                current_row = [word]
                current_y = word_y

        # 添加最后一行
        if current_row and len(current_row) >= min_words_per_row:
            rows.append(current_row)

        logger.debug(f"[AlignmentInferrer] Detected {len(rows)} rows")

        return rows

    @classmethod
    def detect_alignment_patterns(
        cls, words: list[dict], col_tolerance: float = 5.0, row_tolerance: float = 3.0
    ) -> dict:
        """
        检测对齐模式

        Args:
            words: 单词列表
            col_tolerance: 列对齐容差
            row_tolerance: 行对齐容差

        Returns:
            对齐模式字典
        """
        columns = cls.infer_columns(words, col_tolerance)
        rows = cls.infer_rows(words, row_tolerance)

        # 计算对齐质量得分
        col_score = cls._calculate_alignment_score(columns, "x0")
        row_score = cls._calculate_alignment_score(rows, "y0")

        # 判断是否像表格
        is_table_like = (
            len(columns) >= 2  # 至少2列
            and len(rows) >= 2  # 至少2行
            and col_score > 0.6  # 列对齐质量好
            and row_score > 0.6  # 行对齐质量好
        )

        return {
            "columns": columns,
            "rows": rows,
            "col_count": len(columns),
            "row_count": len(rows),
            "col_alignment_score": col_score,
            "row_alignment_score": row_score,
            "is_table_like": is_table_like,
        }

    @classmethod
    def _calculate_alignment_score(cls, groups: list[list[dict]], key: str) -> float:
        """
        计算对齐质量得分

        Args:
            groups: 分组列表
            key: 坐标键 ('x0' 或 'y0')

        Returns:
            对齐得分 0.0-1.0
        """
        if not groups or len(groups) < 2:
            return 0.0

        scores = []

        for group in groups:
            if len(group) < 2:
                scores.append(0.5)  # 单个单词，中等分数
                continue

            # 计算组内方差
            values = [w.get(key, 0) for w in group]
            mean_val = np.mean(values)
            std_val = np.std(values)

            # 方差越小，对齐越好
            # 使用指数衰减函数：score = exp(-std/10)
            score = np.exp(-std_val / 10.0)
            scores.append(score)

        return np.mean(scores) if scores else 0.0

    @classmethod
    def find_column_boundaries(cls, words: list[dict], tolerance: float = 5.0) -> list[float]:
        """
        查找列边界（列之间的中点）

        Args:
            words: 单词列表
            tolerance: 对齐容差

        Returns:
            列边界位置列表
        """
        columns = cls.infer_columns(words, tolerance)

        if len(columns) < 2:
            return []

        boundaries = []

        for i in range(len(columns) - 1):
            # 当前列的最右位置
            col1_max = max(w.get("x1", 0) for w in columns[i])
            # 下一列的最左位置
            col2_min = min(w.get("x0", 0) for w in columns[i + 1])

            # 边界在中点
            boundary = (col1_max + col2_min) / 2.0
            boundaries.append(boundary)

        return boundaries

    @classmethod
    def validate_grid_structure(cls, words: list[dict], columns: list[list[dict]], rows: list[list[dict]]) -> float:
        """
        验证网格结构质量

        Args:
            words: 单词列表
            columns: 列分组
            rows: 行分组

        Returns:
            网格质量得分 0.0-1.0
        """
        if not columns or not rows:
            return 0.0

        # 1. 检查覆盖度（多少单词被分配到行列）
        words_in_grid = set()
        for col in columns:
            for word in col:
                words_in_grid.add(id(word))

        coverage = len(words_in_grid) / len(words) if words else 0.0

        # 2. 检查一致性（每行每列的单词数是否相近）
        col_sizes = [len(col) for col in columns]
        row_sizes = [len(row) for row in rows]

        col_consistency = 1.0 - (np.std(col_sizes) / (np.mean(col_sizes) + 1e-6))
        row_consistency = 1.0 - (np.std(row_sizes) / (np.mean(row_sizes) + 1e-6))

        # 3. 综合得分
        score = coverage * 0.3 + max(0, col_consistency) * 0.35 + max(0, row_consistency) * 0.35

        return min(1.0, max(0.0, score))
