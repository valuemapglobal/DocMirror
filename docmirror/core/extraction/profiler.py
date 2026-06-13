# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Document Profiler — 文档特征分析器
==================================

基于第一性原理的文档特征分析：不是简单判断"数字/扫描"，而是从8个维度
全面刻画文档特征，为智能策略路由提供决策依据。

Design Principle (道德经):
    "道法自然" — 让文档自己"说"出它的特征，而非人为预设分类。
    "上善若水" — 策略像水一样，根据文档"容器"调整形态。

Core Philosophy:
    文档的本质不是单一类型，而是多维特征的集合。
    只有理解文档的全貌，才能选择最优的提取策略。

Usage::

    from docmirror.core.extraction.profiler import DocumentProfiler

    # 快速分析文档特征（<100ms）
    profile = DocumentProfiler.profile(fitz_doc, plum_doc)

    # 获取特征向量
    features = profile.to_feature_vector()
    # [0.85, 1.0, 0.0, 0.0, 1.0, 1.0, 0.8, 0.3]

    # 判断文档类型
    if profile.doc_type == DocType.DIGITAL:
        # 使用数字PDF策略
        ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Enumerations
# ═══════════════════════════════════════════════════════════════════════════════


class DocType(Enum):
    """文档类型"""

    DIGITAL = "digital"  # 纯数字PDF（有文本层）
    SCANNED = "scanned"  # 扫描件（无文本层）
    HYBRID = "hybrid"  # 混合文档（部分页面有文本层）


class Quality(Enum):
    """文档质量等级"""

    HIGH = "high"  # >= 80 分
    MEDIUM = "medium"  # 50-79 分
    LOW = "low"  # < 50 分


class Complexity(Enum):
    """文档复杂度"""

    SIMPLE = 0  # 单一字体，简单布局
    MODERATE = 1  # 2-3种字体，常规布局
    COMPLEX = 2  # >3种字体，复杂布局


class TableDensity(Enum):
    """表格密度"""

    SPARSE = 0  # 0-2 个表格
    MODERATE = 1  # 3-5 个表格
    DENSE = 2  # > 5 个表格


# ═══════════════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class DocumentProfile:
    """
    文档特征画像 — 8维特征向量

    Attributes:
        quality_score: 质量评分 0-100
        doc_type: 文档类型
        complexity: 复杂度
        table_density: 表格密度
        has_text_layer: 是否有文本层
        has_explicit_borders: 是否有显式边框
        avg_chars_per_line: 平均每行字符数
        table_count_estimate: 预估表格数
    """

    quality_score: float
    doc_type: DocType
    complexity: Complexity
    table_density: TableDensity
    has_text_layer: bool
    has_explicit_borders: bool
    avg_chars_per_line: float
    table_count_estimate: int

    def to_feature_vector(self) -> list[float]:
        """
        转换为特征向量（用于策略路由）

        Returns:
            9维特征向量 [0-1] 归一化
        """
        return [
            self.quality_score / 100.0,  # 0: 质量
            1.0 if self.doc_type == DocType.DIGITAL else 0.0,  # 1: 是否数字
            0.0 if self.doc_type == DocType.SCANNED else 0.5,  # 2: 扫描程度
            self.complexity.value / 2.0,  # 3: 复杂度
            self.table_density.value / 2.0,  # 4: 表格密度
            1.0 if self.has_text_layer else 0.0,  # 5: 文本层
            1.0 if self.has_explicit_borders else 0.0,  # 6: 边框
            min(1.0, self.avg_chars_per_line / 100.0),  # 7: 字符密度
            min(1.0, self.table_count_estimate / 10.0),  # 8: 表格数
        ]

    def summary(self) -> str:
        """生成人类可读的摘要"""
        return (
            f"DocumentProfile("
            f"type={self.doc_type.value}, "
            f"quality={self.quality_score:.0f}, "
            f"complexity={self.complexity.name}, "
            f"tables={self.table_count_estimate}, "
            f"text_layer={self.has_text_layer}, "
            f"borders={self.has_explicit_borders}"
            f")"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Document Profiler
# ═══════════════════════════════════════════════════════════════════════════════


class DocumentProfiler:
    """
    文档特征分析器 — 快速分析（<100ms）

    分析维度：
        1. 文本层检测（PyMuPDF快速扫描前3页）
        2. 质量评估（Laplacian方差，采样渲染）
        3. 边框检测（pdfplumber lines统计）
        4. 表格密度估算（布局分析）
        5. 复杂度评估（字体种类、列数变化）

    设计原则：
        - 快速：只采样前3页，避免全量扫描
        - 准确：多维度交叉验证
        - 鲁棒：异常时降级到默认值
    """

    @classmethod
    def profile(cls, fitz_doc, plum_doc, max_sample_pages: int = 3) -> DocumentProfile:
        """
        快速分析文档特征

        Args:
            fitz_doc: PyMuPDF document对象
            plum_doc: pdfplumber document对象
            max_sample_pages: 最大采样页数（默认3）

        Returns:
            DocumentProfile 对象
        """
        try:
            # 1. 文本层检测
            has_text_layer = cls._detect_text_layer(fitz_doc, max_sample_pages)

            # 2. 质量评估（采样第1页）
            quality_score = cls._assess_quality(fitz_doc[0])

            # 3. 边框检测
            has_explicit_borders = cls._detect_borders(plum_doc, max_sample_pages)

            # 4. 文档类型判断
            doc_type = cls._classify_doc_type(has_text_layer, quality_score, fitz_doc, max_sample_pages)

            # 5. 复杂度评估
            complexity = cls._assess_complexity(fitz_doc, max_sample_pages)

            # 6. 表格密度估算
            table_density = cls._estimate_table_density(plum_doc, max_sample_pages)
            table_count = cls._estimate_table_count(plum_doc)

            # 7. 字符密度
            avg_chars = cls._calculate_char_density(fitz_doc, max_sample_pages)

            profile = DocumentProfile(
                quality_score=quality_score,
                doc_type=doc_type,
                complexity=complexity,
                table_density=table_density,
                has_text_layer=has_text_layer,
                has_explicit_borders=has_explicit_borders,
                avg_chars_per_line=avg_chars,
                table_count_estimate=table_count,
            )

            logger.debug(f"[DocumentProfiler] {profile.summary()}")
            return profile

        except Exception as e:
            logger.warning(f"[DocumentProfiler] Profiling failed: {e}, using defaults")
            # 降级到默认配置
            return cls._default_profile()

    @classmethod
    def _detect_text_layer(cls, fitz_doc, max_pages: int) -> bool:
        """
        检测是否有文本层

        Rationale: 如果前N页平均每页>50字符，认为有文本层
        """
        sample_pages = min(len(fitz_doc), max_pages)
        total_chars = sum(len(fitz_doc[i].get_text()) for i in range(sample_pages))
        avg_chars = total_chars / max(1, sample_pages)
        return avg_chars > 50

    @classmethod
    def _assess_quality(cls, fitz_page) -> float:
        """
        评估页面质量（0-100分）

        Rationale: 使用Laplacian方差作为清晰度指标
        - var >= 200 → 100分（高质量）
        - var 50-200 → 60-100分（中等）
        - var < 50 → 0-60分（低质量）
        """
        try:
            import cv2
            import numpy as np

            # 渲染页面为图像
            pix = fitz_page.get_pixmap(dpi=150)
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)

            # 转灰度
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

            # Laplacian方差
            lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()

            # 转换为0-100分
            if lap_var >= 200:
                return 100.0
            elif lap_var >= 50:
                return 60 + (lap_var - 50) / 150 * 40
            else:
                return lap_var / 50 * 60

        except ImportError:
            # 无OpenCV，使用简单启发式
            text_len = len(fitz_page.get_text())
            return min(100.0, text_len / 10)  # 粗略估计
        except Exception as e:
            logger.debug(f"[DocumentProfiler] Quality assessment failed: {e}")
            return 50.0  # 默认中等质量

    @classmethod
    def _detect_borders(cls, plum_doc, max_pages: int) -> bool:
        """
        检测是否有显式边框

        Rationale: 如果前N页平均每页>20条线，认为有显式边框
        """
        sample_pages = min(len(plum_doc), max_pages)
        total_lines = sum(len(plum_doc[i].lines or []) for i in range(sample_pages))
        avg_lines = total_lines / max(1, sample_pages)
        return avg_lines > 20

    @classmethod
    def _classify_doc_type(cls, has_text_layer: bool, quality_score: float, fitz_doc, max_pages: int) -> DocType:
        """
        分类文档类型

        规则：
        - 有文本层 + 高质量 → DIGITAL
        - 无文本层 → SCANNED
        - 部分页面有文本层 → HYBRID
        """
        if not has_text_layer:
            return DocType.SCANNED

        # 检查是否所有页面都有文本层
        sample_pages = min(len(fitz_doc), max_pages)
        pages_with_text = sum(1 for i in range(sample_pages) if len(fitz_doc[i].get_text()) > 50)

        if pages_with_text == sample_pages:
            return DocType.DIGITAL
        elif pages_with_text > 0:
            return DocType.HYBRID
        else:
            return DocType.SCANNED

    @classmethod
    def _assess_complexity(cls, fitz_doc, max_pages: int) -> Complexity:
        """
        评估文档复杂度

        Rationale: 基于字体种类数量
        - < 3种字体 → SIMPLE
        - 3-6种字体 → MODERATE
        - > 6种字体 → COMPLEX
        """
        try:
            font_names = set()
            sample_pages = min(len(fitz_doc), max_pages)

            for i in range(sample_pages):
                text_dict = fitz_doc[i].get_text("dict")
                for block in text_dict.get("blocks", []):
                    if "lines" not in block:
                        continue
                    for line in block["lines"]:
                        for span in line.get("spans", []):
                            font_names.add(span.get("font", ""))

            font_count = len(font_names)

            if font_count < 3:
                return Complexity.SIMPLE
            elif font_count < 6:
                return Complexity.MODERATE
            else:
                return Complexity.COMPLEX

        except Exception as e:
            logger.debug(f"[DocumentProfiler] Complexity assessment failed: {e}")
            return Complexity.MODERATE  # 默认中等复杂度

    @classmethod
    def _estimate_table_density(cls, plum_doc, max_pages: int) -> TableDensity:
        """估算表格密度"""
        table_count = cls._estimate_table_count(plum_doc, max_pages)

        if table_count <= 2:
            return TableDensity.SPARSE
        elif table_count <= 5:
            return TableDensity.MODERATE
        else:
            return TableDensity.DENSE

    @classmethod
    def _estimate_table_count(cls, plum_doc, max_pages: int = None) -> int:
        """
        估算表格数量

        Rationale: 使用pdfplumber的find_tables()快速估算
        """
        try:
            sample_pages = min(len(plum_doc), max_pages or len(plum_doc))
            total_tables = 0

            for i in range(sample_pages):
                page = plum_doc[i]
                tables = page.find_tables()
                total_tables += len(tables)

            # 如果只采样了部分页面，估算总数
            if max_pages and max_pages < len(plum_doc):
                ratio = len(plum_doc) / max_pages
                total_tables = int(total_tables * ratio)

            return total_tables

        except Exception as e:
            logger.debug(f"[DocumentProfiler] Table count estimation failed: {e}")
            return 0

    @classmethod
    def _calculate_char_density(cls, fitz_doc, max_pages: int) -> float:
        """计算平均每行字符数"""
        try:
            sample_pages = min(len(fitz_doc), max_pages)
            total_chars = 0
            total_lines = 0

            for i in range(sample_pages):
                text = fitz_doc[i].get_text()
                lines = text.split("\n")
                total_chars += len(text)
                total_lines += len([l for l in lines if l.strip()])

            return total_chars / max(1, total_lines)

        except Exception as e:
            logger.debug(f"[DocumentProfiler] Char density calculation failed: {e}")
            return 50.0  # 默认值

    @classmethod
    def _default_profile(cls) -> DocumentProfile:
        """默认配置（分析失败时使用）"""
        return DocumentProfile(
            quality_score=50.0,
            doc_type=DocType.HYBRID,
            complexity=Complexity.MODERATE,
            table_density=TableDensity.MODERATE,
            has_text_layer=True,
            has_explicit_borders=False,
            avg_chars_per_line=50.0,
            table_count_estimate=2,
        )
