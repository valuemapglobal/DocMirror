# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Semantic Level Classifier (v11 Optimization)
=============================================

细粒度文本语义级别分类器 - 解决Level分类粗糙问题

分类体系:
- h1: 一级标题（如"身份标识"、"信息概要"）
- h2: 二级标题（如"基本概况信息"）
- label: 字段标签（如"企业名称"）
- value: 字段值（如"佛山市石头普润斯科技有限公司"）
- body: 普通正文
- footer: 页脚/页码

基于多模态特征融合：字体、位置、模式、上下文
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PageContext:
    """页面上下文信息，用于Level分类"""
    page_number: int
    page_height: float
    page_width: float
    previous_block: TextBlockInfo | None = None
    next_block: TextBlockInfo | None = None


@dataclass
class TextBlockInfo:
    """文本块信息"""
    content: str
    font_size: float = 12.0
    font_weight: str = "normal"  # normal, bold
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    classified_level: str = "body"


# ═══════════════════════════════════════════════════════════════════════════
# 征信报告领域词典
# ═══════════════════════════════════════════════════════════════════════════

# 一级标题（h1）
H1_TITLES = {
    "身份标识",
    "信息概要",
    "基本信息",
    "信贷交易信息",
    "公共记录明细",
    "声明信息",
    "报告说明",
}

# 二级标题（h2）
H2_TITLES = {
    "基本概况信息",
    "高管人员信息",
    "资本构成信息",
    "主要组成人员信息",
    "实际控制人",
    "获得许可记录",
    "环保处罚信息",
    "信贷交易概要",
    "借贷交易概要",
    "担保交易概要",
    "非信贷交易概要",
}

# 字段标签词典（label）
FIELD_LABELS = {
    "企业名称",
    "中征码",
    "统一社会信用代码",
    "组织机构代码",
    "纳税人识别号（国税）",
    "纳税人识别号（地税）",
    "经济类型",
    "组织机构类型",
    "企业规模",
    "所属行业",
    "成立年份",
    "登记证书有效截止日期",
    "登记地址",
    "办公/经营地址",
    "注册资本",
    "法定代表人",
    "经营范围",
    "信息来源机构",
    "更新日期",
    "职位",
    "姓名",
    "证件类型",
    "证件号码",
    "许可部门",
    "许可类型",
    "许可日期",
    "截止日期",
    "许可内容",
}


class SemanticLevelClassifier:
    """细粒度文本语义级别分类器"""

    def classify(self, text_block: TextBlockInfo, page_context: PageContext) -> str:
        """
        基于多特征融合的Level分类
        
        Args:
            text_block: 文本块信息
            page_context: 页面上下文
        
        Returns:
            分类级别: h1, h2, label, value, body, footer
        """
        content = text_block.content.strip()

        if not content:
            return "body"

        # 规则1: 页码识别（最高优先级）
        if self._is_footer(content, text_block, page_context):
            return "footer"

        # 规则2: 一级标题识别
        if self._is_h1_title(content):
            return "h1"

        # 规则3: 二级标题识别
        if self._is_h2_title(content):
            return "h2"

        # 规则4: 字段标签识别
        if self._is_field_label(content):
            return "label"

        # 规则5: 字段值识别（基于上下文）
        if self._is_field_value(text_block, page_context):
            return "value"

        # 规则6: 字体大小启发式
        if self._is_title_by_font(text_block):
            if text_block.font_size > 16:
                return "h1"
            elif text_block.font_size > 14 and text_block.font_weight == "bold":
                return "h2"

        # 默认：body
        return "body"

    def _is_footer(self, content: str, text_block: TextBlockInfo, page_context: PageContext) -> bool:
        """判断是否为页脚/页码"""
        # 页码模式白名单
        page_number_patterns = [
            r'第\s*\d+\s*页/共\d+\s*页',  # 第 3 页/共4 页
            r'Page\s*\d+\s*of\s*\d+',      # Page 3 of 4
            r'\d+\s*/\s*\d+',              # 3 / 4
        ]

        for pattern in page_number_patterns:
            if re.search(pattern, content):
                return True

        # 位置判断（页面底部5%区域）
        if page_context.page_height > 0:
            if text_block.y0 > page_context.page_height * 0.95:
                return True

        return False

    def _is_h1_title(self, content: str) -> bool:
        """判断是否为一级标题"""
        # 精确匹配
        if content in H1_TITLES:
            return True

        # 前缀匹配（去除可能的后缀）
        for title in H1_TITLES:
            if content.startswith(title) and len(content) <= len(title) + 5:
                return True

        return False

    def _is_h2_title(self, content: str) -> bool:
        """判断是否为二级标题"""
        if content in H2_TITLES:
            return True

        for title in H2_TITLES:
            if content.startswith(title) and len(content) <= len(title) + 5:
                return True

        return False

    def _is_field_label(self, content: str) -> bool:
        """判断是否为字段标签"""
        # 精确匹配
        if content in FIELD_LABELS:
            return True

        # 前缀匹配（如"企业名称 "后面可能有空格）
        for label in FIELD_LABELS:
            if content == label or content.startswith(label + " "):
                return True

        # 模式匹配：以"："或":"结尾
        if content.endswith("：") or content.endswith(":"):
            clean_content = content.rstrip("：:").strip()
            if clean_content in FIELD_LABELS:
                return True

        return False

    def _is_field_value(self, text_block: TextBlockInfo, page_context: PageContext) -> bool:
        """判断是否为字段值"""
        # 如果前一个block是label，且当前block在同一行或下一行
        if page_context.previous_block:
            if page_context.previous_block.classified_level == 'label':
                # 检查空间相邻性（同一行或下一行，x坐标接近）
                if self._spatially_adjacent(page_context.previous_block, text_block):
                    return True

        return False

    def _spatially_adjacent(self, label_block: TextBlockInfo, value_block: TextBlockInfo) -> bool:
        """判断两个文本块是否空间相邻"""
        # Y坐标接近（同一行或下一行）
        y_diff = abs(value_block.y0 - label_block.y0)
        if y_diff > 20:  # 超过20pt认为不是同一行
            return False

        # X坐标：value应该在label右侧
        if value_block.x0 < label_block.x1 - 5:  # 允许5pt误差
            return False

        return True

    def _is_title_by_font(self, text_block: TextBlockInfo) -> bool:
        """基于字体特征判断是否为标题"""
        # 粗体且字号较大
        if text_block.font_weight == "bold" and text_block.font_size >= 14:
            return True

        # 字号显著大于正文
        if text_block.font_size >= 16:
            return True

        return False


# ═══════════════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════════════

# 全局分类器实例（单例）
_classifier = SemanticLevelClassifier()


def classify_text_level(content: str, page_context: PageContext,
                       font_size: float = 12.0,
                       font_weight: str = "normal",
                       bbox: tuple = (0, 0, 0, 0)) -> str:
    """
    便捷函数：分类文本级别
    
    Args:
        content: 文本内容
        page_context: 页面上下文
        font_size: 字体大小
        font_weight: 字体粗细
        bbox: 边界框 (x0, y0, x1, y1)
    
    Returns:
        分类级别
    """
    text_block = TextBlockInfo(
        content=content,
        font_size=font_size,
        font_weight=font_weight,
        x0=bbox[0],
        y0=bbox[1],
        x1=bbox[2],
        y1=bbox[3],
    )

    return _classifier.classify(text_block, page_context)
