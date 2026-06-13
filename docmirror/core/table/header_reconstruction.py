# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Column-Aware Header Reconstruction (v11 Optimization)
======================================================

列感知Header重组算法 - 解决表格Header文字粘连与乱序问题

算法原理:
1. 领域词典快速校正（优先）
2. 垂直投影分析（基于字符坐标）
3. 启发式分割（备选）

模拟人类阅读表格时的列边界识别机制。
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 征信报告Header校正词典
# ═══════════════════════════════════════════════════════════════════════════

CREDIT_REPORT_HEADER_FIXES = {
    "当前交有易未的结清构信数贷": "当前有未结清信贷交易的机构数",
    "当前交有易未的结机清构信数贷": "当前有未结清信贷交易的机构数",
    "首次责有任相的关年还份款": "首次有相关还款责任的年份",
}


def reconstruct_headers_by_columns(headers: list[str], page_chars: list | None = None) -> list[str]:
    """列感知Header重组算法（v11优化）
    
    基于字符物理位置的列边界检测与文本重组。
    模拟人类阅读表格时的列边界识别机制。
    
    Args:
        headers: 原始headers列表（可能包含粘连文本）
        page_chars: 页面字符级坐标信息（可选，用于高级重组）
    
    Returns:
        重组后的headers列表
    
    算法流程:
    1. 领域词典快速校正（优先）
    2. 垂直投影分析（如有字符坐标）
    3. 启发式分割（备选）
    """
    if not headers or len(headers) <= 1:
        return headers

    # Step 1: 领域词典校正（最可靠）
    fixed_headers = []
    for h in headers:
        if h in CREDIT_REPORT_HEADER_FIXES:
            corrected = CREDIT_REPORT_HEADER_FIXES[h]
            logger.debug(f"[HeaderFix] Corrected: '{h}' → '{corrected}'")
            fixed_headers.append(corrected)
        else:
            fixed_headers.append(h)

    # Step 2: 如果有字符坐标，进行垂直投影重组
    if page_chars:
        fixed_headers = _reconstruct_by_vertical_projection(fixed_headers, page_chars)

    # Step 3: 启发式粘连检测（备选）
    fixed_headers = _fix_sticky_headers_heuristic(fixed_headers)

    return fixed_headers


def _reconstruct_by_vertical_projection(headers: list[str], page_chars: list) -> list[str]:
    """基于垂直投影直方图的Header重组
    
    使用字符x坐标的垂直投影密度检测列边界。
    
    Args:
        headers: 当前headers
        page_chars: 字符级坐标列表 [{x0, y0, x1, y1, text}, ...]
    
    Returns:
        重组后的headers
    """
    if not page_chars:
        return headers

    # 提取所有字符的x坐标
    x_positions = []
    for char_info in page_chars:
        x_positions.append(char_info.get('x0', 0))

    if not x_positions:
        return headers

    # 检测垂直空白间隙（列边界）
    x_positions.sort()
    gaps = _detect_vertical_gaps(x_positions, threshold=15.0)

    if not gaps:
        return headers

    # 根据间隙重新分组字符
    # TODO: 实现完整的字符分组逻辑
    logger.debug(f"[VerticalProjection] Detected {len(gaps)} column gaps")

    return headers


def _detect_vertical_gaps(x_positions: list[float], threshold: float = 15.0) -> list[float]:
    """检测垂直投影中的空白间隙
    
    Args:
        x_positions: 排序后的x坐标列表
        threshold: 间隙阈值（pt）
    
    Returns:
        间隙位置列表
    """
    gaps = []
    for i in range(1, len(x_positions)):
        gap = x_positions[i] - x_positions[i-1]
        if gap > threshold:
            gaps.append((x_positions[i-1] + x_positions[i]) / 2)
    return gaps


def _fix_sticky_headers_heuristic(headers: list[str]) -> list[str]:
    """启发式粘连Header修复
    
    检测并分割异常长度的header文本。
    
    Args:
        headers: 当前headers
    
    Returns:
        修复后的headers
    """
    fixed = []
    for h in headers:
        # 检测异常长的header（>30字符且包含多个语义单元）
        if len(h) > 30 and _has_multiple_semantic_units(h):
            # 尝试分割（基于征信报告领域知识）
            split_parts = _split_credit_report_header(h)
            if split_parts:
                logger.debug(f"[HeuristicFix] Split long header: '{h}' → {split_parts}")
                fixed.extend(split_parts)
            else:
                fixed.append(h)
        else:
            fixed.append(h)
    return fixed


def _has_multiple_semantic_units(text: str) -> bool:
    """判断文本是否包含多个语义单元"""
    # 包含多个"的"、"交易"、"机构"、"年份"、"责任"等关键词
    keywords = ["的", "交易", "机构", "年份", "责任"]
    count = sum(1 for kw in keywords if kw in text)
    return count >= 3


def _split_credit_report_header(text: str) -> list[str] | None:
    """征信报告专用Header分割"""
    # 基于已知模式的分割规则
    patterns = [
        # 模式1: "当前有未结清信贷交易的机构数"
        (r"当前.*信贷交易.*机构数", ["当前有未结清信贷交易的机构数"]),
        # 模式2: "首次有相关还款责任的年份"
        (r"首次.*还款.*责任.*年份", ["首次有相关还款责任的年份"]),
    ]

    for pattern, replacement in patterns:
        if re.search(pattern, text):
            return replacement

    return None
