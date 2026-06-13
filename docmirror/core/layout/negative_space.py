# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Negative Space Analyzer — 负空间分析器
=======================================

基于第一性原理的负空间感知：从"空白"中提取结构信息。

Design Principle (道德经):
    "知其白，守其黑" — 理解空白（白）的价值，利用它推断结构（黑）。
    "有无相生" — 空白（无）与内容（有）相互定义结构。

Core Philosophy:
    空白不是"无信息"，而是"高信息"。
    大的空白间隙 = 列边界
    规律性空白 = 表格结构
    对齐规律 = 隐式网格

Usage::

    from docmirror.core.layout.negative_space import NegativeSpaceAnalyzer

    # 分析页面负空间
    profile = NegativeSpaceAnalyzer.analyze(page_words)

    # 获取列边界（空白谷值）
    col_boundaries = profile.column_gaps
    # [150.5, 320.8, 485.2]

    # 获取密度热图
    density_map = profile.density_map
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class NegativeSpaceProfile:
    """
    负空间特征画像

    Attributes:
        column_gaps: 列间隙位置（垂直投影谷值）
        row_gaps: 行间隙位置（水平投影谷值）
        density_map: 密度热图 (2D numpy array)
        blank_regions: 空白区域列表 [(x0, y0, x1, y1), ...]
        v_projection: 垂直投影数组
        h_projection: 水平投影数组
    """

    column_gaps: list[float] = field(default_factory=list)
    row_gaps: list[float] = field(default_factory=list)
    density_map: np.ndarray | None = None
    blank_regions: list[tuple[float, float, float, float]] = field(default_factory=list)
    v_projection: np.ndarray | None = None
    h_projection: np.ndarray | None = None

    def summary(self) -> str:
        """生成人类可读的摘要"""
        return (
            f"NegativeSpaceProfile("
            f"col_gaps={len(self.column_gaps)}, "
            f"row_gaps={len(self.row_gaps)}, "
            f"blank_regions={len(self.blank_regions)}"
            f")"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Negative Space Analyzer
# ═══════════════════════════════════════════════════════════════════════════════


class NegativeSpaceAnalyzer:
    """
    负空间分析器 — 从"空白"中提取信息

    核心思想：
        - 空白不是"无"，而是"有"（有结构、有信息）
        - 大的空白间隙 = 列边界
        - 规律性空白 = 表格结构
        - 对齐规律 = 隐式网格

    分析维度：
        1. 垂直投影分析（检测列边界）
        2. 水平投影分析（检测行边界）
        3. 密度热图生成（识别内容密集区）
        4. 空白区域检测（找到无内容区域）
    """

    @classmethod
    def analyze(
        cls, page_words: list[dict], resolution: int = 2, smooth_sigma: float = 2.0, valley_threshold_ratio: float = 0.3
    ) -> NegativeSpaceProfile:
        """
        分析页面的负空间特征

        Args:
            page_words: pdfplumber提取的单词列表，包含bbox信息
                [{'x0': 10, 'y0': 20, 'x1': 50, 'y1': 30, 'text': 'hello'}, ...]
            resolution: 投影分析分辨率（像素）
            smooth_sigma: 高斯平滑sigma值
            valley_threshold_ratio: 谷值阈值（相对于峰值的比例）

        Returns:
            NegativeSpaceProfile 对象
        """
        if not page_words:
            return NegativeSpaceProfile()

        try:
            # 1. 垂直投影分析（检测列边界）
            v_projection = cls._vertical_projection(page_words, resolution)
            v_projection = cls._smooth_projection(v_projection, smooth_sigma)
            col_gaps = cls._find_projection_valleys(v_projection, valley_threshold_ratio)
            # 转换回原始坐标
            col_gaps = [gap * resolution for gap in col_gaps]

            # 2. 水平投影分析（检测行边界）
            h_projection = cls._horizontal_projection(page_words, resolution)
            h_projection = cls._smooth_projection(h_projection, smooth_sigma)
            row_gaps = cls._find_projection_valleys(h_projection, valley_threshold_ratio)
            # 转换回原始坐标
            row_gaps = [gap * resolution for gap in row_gaps]

            # 3. 密度热图生成
            density_map = cls._generate_density_heatmap(page_words, resolution)

            # 4. 空白区域检测
            blank_regions = cls._detect_blank_regions(page_words, density_map, resolution)

            profile = NegativeSpaceProfile(
                column_gaps=col_gaps,
                row_gaps=row_gaps,
                density_map=density_map,
                blank_regions=blank_regions,
                v_projection=v_projection,
                h_projection=h_projection,
            )

            logger.debug(f"[NegativeSpaceAnalyzer] {profile.summary()}")
            return profile

        except Exception as e:
            logger.warning(f"[NegativeSpaceAnalyzer] Analysis failed: {e}")
            return NegativeSpaceProfile()

    @classmethod
    def _vertical_projection(cls, words: list[dict], resolution: int) -> np.ndarray:
        """
        垂直投影分析 — 统计每个x位置的字符数

        Rationale:
            - 列内的字符 → x位置密集（峰值）
            - 列间的空白 → x位置稀疏（谷值）
            - 谷值位置 = 列边界

        Args:
            words: 单词列表
            resolution: 分辨率（像素）

        Returns:
            投影数组
        """
        if not words:
            return np.zeros(100)

        # 获取页面宽度
        page_width = max(w["x1"] for w in words)
        num_bins = int(page_width / resolution) + 1

        projection = np.zeros(num_bins)

        for word in words:
            x0_bin = int(word["x0"] / resolution)
            x1_bin = int(word["x1"] / resolution)
            # 单词覆盖的x位置+1
            projection[x0_bin : x1_bin + 1] += 1

        return projection

    @classmethod
    def _horizontal_projection(cls, words: list[dict], resolution: int) -> np.ndarray:
        """
        水平投影分析 — 统计每个y位置的字符数

        Rationale:
            - 行内的字符 → y位置密集（峰值）
            - 行间的空白 → y位置稀疏（谷值）
            - 谷值位置 = 行边界

        Args:
            words: 单词列表
            resolution: 分辨率（像素）

        Returns:
            投影数组
        """
        if not words:
            return np.zeros(100)

        # 获取页面高度
        page_height = max(w["y1"] for w in words)
        num_bins = int(page_height / resolution) + 1

        projection = np.zeros(num_bins)

        for word in words:
            y0_bin = int(word["y0"] / resolution)
            y1_bin = int(word["y1"] / resolution)
            # 单词覆盖的y位置+1
            projection[y0_bin : y1_bin + 1] += 1

        return projection

    @classmethod
    def _smooth_projection(cls, projection: np.ndarray, sigma: float) -> np.ndarray:
        """
        平滑投影（减少噪声）

        Args:
            projection: 投影数组
            sigma: 高斯平滑sigma值

        Returns:
            平滑后的投影
        """
        try:
            from scipy.ndimage import gaussian_filter1d

            return gaussian_filter1d(projection, sigma=sigma)
        except ImportError:
            # 无scipy，使用简单移动平均
            if len(projection) < 3:
                return projection

            smoothed = projection.copy()
            for i in range(1, len(projection) - 1):
                smoothed[i] = (projection[i - 1] + projection[i] + projection[i + 1]) / 3.0
            return smoothed

    @classmethod
    def _find_projection_valleys(cls, projection: np.ndarray, threshold_ratio: float = 0.3) -> list[int]:
        """
        查找投影谷值（空白间隙）

        Args:
            projection: 投影数组
            threshold_ratio: 谷值阈值（相对于峰值的比例）

        Returns:
            谷值位置列表（索引）
        """
        if len(projection) == 0:
            return []

        peak = np.max(projection)
        if peak == 0:
            return []

        threshold = peak * threshold_ratio

        valleys = []
        in_valley = False
        valley_start = 0

        for i, value in enumerate(projection):
            if value < threshold and not in_valley:
                # 进入谷值
                in_valley = True
                valley_start = i
            elif value >= threshold and in_valley:
                # 离开谷值
                in_valley = False
                valley_center = (valley_start + i) // 2
                valleys.append(valley_center)

        # 如果最后还在谷值中
        if in_valley:
            valley_center = (valley_start + len(projection) - 1) // 2
            valleys.append(valley_center)

        return valleys

    @classmethod
    def _generate_density_heatmap(cls, words: list[dict], resolution: int) -> np.ndarray:
        """
        生成密度热图

        Args:
            words: 单词列表
            resolution: 分辨率

        Returns:
            2D密度热图 (height x width)
        """
        if not words:
            return np.zeros((10, 10))

        # 获取页面尺寸
        page_width = max(w["x1"] for w in words)
        page_height = max(w["y1"] for w in words)

        width_bins = int(page_width / resolution) + 1
        height_bins = int(page_height / resolution) + 1

        heatmap = np.zeros((height_bins, width_bins))

        for word in words:
            x0_bin = int(word["x0"] / resolution)
            x1_bin = int(word["x1"] / resolution)
            y0_bin = int(word["y0"] / resolution)
            y1_bin = int(word["y1"] / resolution)

            # 单词覆盖的区域+1
            heatmap[y0_bin : y1_bin + 1, x0_bin : x1_bin + 1] += 1

        return heatmap

    @classmethod
    def _detect_blank_regions(
        cls, words: list[dict], density_map: np.ndarray, resolution: int, min_blank_size: int = 10
    ) -> list[tuple[float, float, float, float]]:
        """
        检测空白区域

        Args:
            words: 单词列表
            density_map: 密度热图
            resolution: 分辨率
            min_blank_size: 最小空白区域大小（像素）

        Returns:
            空白区域列表 [(x0, y0, x1, y1), ...]
        """
        if density_map is None or len(words) == 0:
            return []

        # 找到密度为0的区域
        blank_mask = density_map == 0

        # 简单实现：扫描连通空白区域
        blank_regions = []
        visited = set()

        height, width = blank_mask.shape

        for y in range(0, height, min_blank_size // resolution):
            for x in range(0, width, min_blank_size // resolution):
                if (y, x) not in visited and blank_mask[y, x]:
                    # 找到空白区域
                    region = cls._flood_fill_blank(blank_mask, y, x, visited, resolution)
                    if region:
                        x0, y0, x1, y1 = region
                        # 检查大小
                        if (x1 - x0) >= min_blank_size and (y1 - y0) >= min_blank_size:
                            blank_regions.append((x0, y0, x1, y1))

        return blank_regions

    @classmethod
    def _flood_fill_blank(
        cls, mask: np.ndarray, start_y: int, start_x: int, visited: set, resolution: int
    ) -> tuple[float, float, float, float] | None:
        """泛洪填充找空白区域"""
        height, width = mask.shape
        stack = [(start_y, start_x)]
        min_x, min_y = start_x, start_y
        max_x, max_y = start_x, start_y

        while stack:
            y, x = stack.pop()

            if (y, x) in visited:
                continue
            if y < 0 or y >= height or x < 0 or x >= width:
                continue
            if not mask[y, x]:
                continue

            visited.add((y, x))
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)

            # 添加邻居
            stack.extend([(y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)])

        if min_x == max_x and min_y == max_y:
            return None

        return (min_x * resolution, min_y * resolution, max_x * resolution, max_y * resolution)
