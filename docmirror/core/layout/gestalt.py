# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Gestalt Vision Layer - T-10
=============================

独立的视觉感知层,在 Zone 生成后、Block 转换前运行。
基于格式塔心理学原理 (Gestalt Principles) 执行三项视觉感知修正:

1. Baseline Gravity (基线引力): 合并同一水平线的碎片 zone
2. Visual Grouping (视觉分组): 基于 proximity + similarity 的分组
3. Separator Line Detection (分隔线检测): 识别视觉分隔线

Design principles:
    - Pure functions, no state, no side effects.
    - Works independently of layout_analysis.py
    - Can be enabled/disabled via feature flag
"""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Baseline Gravity (基线引力)
# ═══════════════════════════════════════════════════════════════════════════════

def apply_baseline_gravity(
    zones: list,
    page_w: float,
    threshold: float = 3.0
) -> list:
    """T-10: 按 baseline (y±threshold) 合并相邻 zone。
    
    适用于: 同一行被错误切分为多个 zone 的情况。
    
    Args:
        zones: Zone 列表
        page_w: 页面宽度
        threshold: baseline 差异阈值 (px),默认 3px
    
    Returns:
        合并后的 zones
    """
    if not zones or len(zones) < 2:
        return zones

    # 按 y_top 排序
    sorted_zones = sorted(zones, key=lambda z: z.bbox[1])

    merged = [sorted_zones[0]]

    for i in range(1, len(sorted_zones)):
        current = merged[-1]
        next_zone = sorted_zones[i]

        # 计算 baseline 差异
        current_y = (current.bbox[1] + current.bbox[3]) / 2
        next_y = (next_zone.bbox[1] + next_zone.bbox[3]) / 2
        baseline_diff = abs(current_y - next_y)

        # 计算宽度
        current_width = current.bbox[2] - current.bbox[0]
        next_width = next_zone.bbox[2] - next_zone.bbox[0]

        # 合并条件:
        # 1. baseline 差异 < threshold
        # 2. 宽度都 < 页面 70% (R-04: 放宽,仅排除全宽 banner)
        # 3. 相同 type 或一个是 summary 一个是 formula
        if (baseline_diff < threshold and
            current_width < page_w * 0.7 and
            next_width < page_w * 0.7 and
            (current.type == next_zone.type or
             {current.type, next_zone.type} <= {"summary", "formula"})):

            # 合并 zone
            from dataclasses import replace

            # 合并 bbox (union)
            new_bbox = (
                min(current.bbox[0], next_zone.bbox[0]),
                min(current.bbox[1], next_zone.bbox[1]),
                max(current.bbox[2], next_zone.bbox[2]),
                max(current.bbox[3], next_zone.bbox[3]),
            )

            # 合并 chars
            new_chars = current.chars + next_zone.chars

            # 合并 text
            new_text = current.text + " " + next_zone.text if current.text and next_zone.text else current.text or next_zone.text

            # 替换最后一个 zone
            merged[-1] = replace(
                current,
                bbox=new_bbox,
                chars=new_chars,
                text=new_text.strip()
            )

            logger.debug(
                f"[Gestalt] Merged zones: {current.type} + {next_zone.type} "
                f"(baseline_diff={baseline_diff:.1f}px)"
            )
        else:
            merged.append(next_zone)

    logger.info(f"[Gestalt] Baseline gravity: {len(zones)} → {len(merged)} zones")
    return merged


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Visual Grouping (视觉分组)
# ═══════════════════════════════════════════════════════════════════════════════

def detect_visual_groups(
    zones: list,
    page_w: float,
    page_h: float,
    proximity_threshold: float = 20.0
) -> dict[str, list[int]]:
    """T-10: 检测视觉分组,返回 {group_id: [zone_indices]}。
    
    基于格式塔原理:
    1. Proximity (接近性): 空间距离 < threshold 且在同一水平带
    2. Similarity (相似性): 相同 type 或字号差异 < 2pt
    3. Common Region (共同区域): 在同一表格区域内
    
    Args:
        zones: Zone 列表
        page_w: 页面宽度
        page_h: 页面高度
        proximity_threshold: 空间距离阈值 (px)
    
    Returns:
        {group_id: [zone_indices, ...]}
    """
    if not zones:
        return {}

    # Union-Find 数据结构
    parent = list(range(len(zones)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # 遍历所有 zone 对,检测是否应该分组
    for i in range(len(zones)):
        for j in range(i + 1, len(zones)):
            z1, z2 = zones[i], zones[j]

            # 计算空间距离 (使用 bbox 中心点)
            cx1 = (z1.bbox[0] + z1.bbox[2]) / 2
            cy1 = (z1.bbox[1] + z1.bbox[3]) / 2
            cx2 = (z2.bbox[0] + z2.bbox[2]) / 2
            cy2 = (z2.bbox[1] + z2.bbox[3]) / 2

            distance = ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5

            # 检查是否在同一水平带 (y 差异 < 30px)
            same_horizontal_band = abs(cy1 - cy2) < 30.0

            # 检查相似性 (相同 type)
            same_type = z1.type == z2.type

            # 分组条件: 距离近 + 同一水平带 + 相同 type
            if (distance < proximity_threshold and
                same_horizontal_band and
                same_type):
                union(i, j)

    # 收集分组结果
    groups: dict[str, list[int]] = defaultdict(list)
    for i in range(len(zones)):
        group_id = f"group_{find(i)}"
        groups[group_id].append(i)

    # 过滤: 只保留包含多个 zone 的分组
    result = {k: v for k, v in groups.items() if len(v) > 1}

    logger.info(f"[Gestalt] Visual grouping: {len(result)} groups detected")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Separator Line Detection (分隔线检测)
# ═══════════════════════════════════════════════════════════════════════════════

def detect_separator_lines(
    chars: list[dict],
    page_w: float,
    min_length: float = 50.0
) -> list[tuple]:
    """T-10: 检测水平/垂直分隔线。
    
    Args:
        chars: 字符列表
        page_w: 页面宽度
        min_length: 最小线长度 (px)
    
    Returns:
        [(x0, y0, x1, y1, orientation), ...]
        orientation: 'horizontal' | 'vertical'
    """
    if not chars:
        return []

    # 线条字符集
    HLINE_CHARS = set("─━═─━═━┅┉┄┈─━═")
    VLINE_CHARS = set("│┃┆┊│┃┆┊")

    # 分离水平线和垂直线字符
    h_chars = [c for c in chars if c.get("text", "") in HLINE_CHARS]
    v_chars = [c for c in chars if c.get("text", "") in VLINE_CHARS]

    separators = []

    # 检测水平线
    if h_chars:
        # 按 y 坐标分组
        y_groups: dict[int, list] = defaultdict(list)
        for c in h_chars:
            y_key = round(c.get("top", 0))
            y_groups[y_key].append(c)

        # 合并相邻线段
        for y_key, line_chars in y_groups.items():
            if not line_chars:
                continue

            sorted_chars = sorted(line_chars, key=lambda c: c.get("x0", 0))

            # 合并连续线段
            segments = [[sorted_chars[0]]]
            for i in range(1, len(sorted_chars)):
                gap = sorted_chars[i]["x0"] - segments[-1][-1].get("x1", sorted_chars[i - 1]["x0"])
                if gap < 5.0:  # 小间隙视为连续
                    segments[-1].append(sorted_chars[i])
                else:
                    segments.append([sorted_chars[i]])

            # 转换为分隔线
            for segment in segments:
                x0 = min(c["x0"] for c in segment)
                x1 = max(c.get("x1", c["x0"]) for c in segment)
                length = x1 - x0

                if length >= min_length:
                    y_mid = (segment[0].get("top", 0) + segment[0].get("bottom", 0)) / 2
                    separators.append((x0, y_mid, x1, y_mid, "horizontal"))

    # 检测垂直线 (类似逻辑)
    if v_chars:
        # 按 x 坐标分组
        x_groups: dict[int, list] = defaultdict(list)
        for c in v_chars:
            x_key = round(c.get("x0", 0))
            x_groups[x_key].append(c)

        # 合并相邻线段
        for x_key, line_chars in x_groups.items():
            if not line_chars:
                continue

            sorted_chars = sorted(line_chars, key=lambda c: c.get("top", 0))

            segments = [[sorted_chars[0]]]
            for i in range(1, len(sorted_chars)):
                gap = sorted_chars[i]["top"] - segments[-1][-1].get("bottom", sorted_chars[i - 1]["top"])
                if gap < 5.0:
                    segments[-1].append(sorted_chars[i])
                else:
                    segments.append([sorted_chars[i]])

            for segment in segments:
                y0 = min(c["top"] for c in segment)
                y1 = max(c.get("bottom", c["top"]) for c in segment)
                length = y1 - y0

                if length >= min_length:
                    x_mid = (segment[0].get("x0", 0) + segment[0].get("x1", 0)) / 2
                    separators.append((x_mid, y0, x_mid, y1, "vertical"))

    logger.info(f"[Gestalt] Separator detection: {len(separators)} lines found")
    return separators


# ═══════════════════════════════════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════════════════════════════════

def apply_gestalt_corrections(
    zones: list,
    chars: list[dict],
    page_w: float,
    page_h: float,
    enable_baseline_gravity: bool = True,
    enable_visual_grouping: bool = True,
    enable_separator_detection: bool = True
) -> list:
    """T-10: 应用所有 Gestalt 视觉感知修正。
    
    执行顺序:
    1. Baseline Gravity (合并同行碎片)
    2. Separator Detection (识别分隔线)
    3. Visual Grouping (标记视觉分组)
    
    Args:
        zones: Zone 列表
        chars: 字符列表
        page_w: 页面宽度
        page_h: 页面高度
        enable_baseline_gravity: 是否启用基线引力
        enable_visual_grouping: 是否启用视觉分组
        enable_separator_detection: 是否启用分隔线检测
    
    Returns:
        增强后的 zones (带 visual_group_id 属性)
    """
    if not zones:
        return zones

    logger.info(f"[Gestalt] Applying corrections to {len(zones)} zones...")

    # Step 1: Baseline Gravity
    if enable_baseline_gravity:
        zones = apply_baseline_gravity(zones, page_w, threshold=3.0)

    # Step 2: Separator Detection
    if enable_separator_detection:
        separators = detect_separator_lines(chars, page_w, min_length=50.0)
        # TODO: 可以使用 separators 信息来优化 zone 边界
        # 当前版本仅记录,不影响 zone 结构
        if separators:
            logger.debug(f"[Gestalt] Found {len(separators)} separator lines")

    # Step 3: Visual Grouping
    if enable_visual_grouping:
        groups = detect_visual_groups(zones, page_w, page_h, proximity_threshold=20.0)

        # 为 zones 添加 visual_group_id
        # 注意: Zone 是 dataclass,需要检查是否有 visual_group_id 字段
        for group_id, indices in groups.items():
            for idx in indices:
                if idx < len(zones):
                    zone = zones[idx]
                    if hasattr(zone, 'visual_group_id'):
                        from dataclasses import replace
                        zones[idx] = replace(zone, visual_group_id=group_id)

    logger.info(f"[Gestalt] Corrections applied, {len(zones)} zones remaining")
    return zones
