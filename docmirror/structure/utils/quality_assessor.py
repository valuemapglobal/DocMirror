# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Document quality assessor — digital vs scanned and quality scoring.

Purpose: Produces ``QualityReport`` with document type guess, blur/noise
metrics, and recommendations for router decisions.

Main components: ``DocumentQualityAssessor``, ``QualityReport``, ``DocumentQuality``.

Upstream: Sample page renders and text layer stats.

Downstream: ``analyze.quality_router``, ``analyze.pre_analyzer``.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class DocumentQuality(Enum):
    """Document quality level."""

    EXCELLENT = "excellent"  # excellent (>0.8)
    GOOD = "good"  # good (0.6-0.8)
    FAIR = "fair"  # fair (0.4-0.6)
    POOR = "poor"  # poor (0.2-0.4)
    VERY_POOR = "very_poor"  # very poor (<0.2)


class DocumentType(Enum):
    """Document type."""

    DIGITAL_PDF = "digital_pdf"  # digital PDF
    SCANNED_PDF = "scanned_pdf"  # scanned PDF
    IMAGE = "image"  # image
    MIXED = "mixed"  # mixed


@dataclass
class QualityReport:
    """Quality report."""

    # Quality score
    overall_score: float  # 综合评分 0-1
    contrast_score: float  # 对比度
    sharpness_score: float  # 清晰度
    noise_score: float  # 噪点水平

    # Document characteristics
    document_type: DocumentType  # 文档类型
    quality_level: DocumentQuality  # 质量等级
    is_scanned: bool  # 是否扫描件

    # Processing recommendations
    recommended_strategy: str  # 推荐策略
    estimated_ocr_quality: float  # 预估OCR质量
    needs_preprocessing: bool  # 是否需要预处理

    # Details
    details: dict[str, Any]  # 详细指标


class DocumentQualityAssessor:
    """
    文档质量评估器

    评估文档质量，推荐最优处理策略。
    """

    def __init__(self):
        self.stats = {
            "total_assessments": 0,
            "excellent": 0,
            "good": 0,
            "fair": 0,
            "poor": 0,
            "very_poor": 0,
        }

    def assess_image(self, image: np.ndarray) -> QualityReport:
        """
        评估图像质量

        Args:
            image: 图像（numpy数组）

        Returns:
            QualityReport
        """
        self.stats["total_assessments"] += 1

        # 1. Base metrics
        contrast_score = self._assess_contrast(image)
        sharpness_score = self._assess_sharpness(image)
        noise_score = self._assess_noise(image)

        # 2. Composite score
        overall_score = contrast_score * 0.3 + sharpness_score * 0.4 + noise_score * 0.3

        # 3. Document type classification
        document_type = self._detect_document_type(image)
        is_scanned = self._is_scanned_document(image, overall_score)

        # 4. Quality grade
        quality_level = self._classify_quality(overall_score)

        # 5. Estimated OCR quality
        estimated_ocr_quality = self._predict_ocr_quality(overall_score, contrast_score, sharpness_score)

        # 6. Recommended strategy
        recommended_strategy = self._recommend_strategy(quality_level, estimated_ocr_quality, is_scanned)

        # 7. Whether preprocessing is needed
        needs_preprocessing = overall_score < 0.7

        # Update statistics
        self._update_stats(quality_level)

        # Generate report
        report = QualityReport(
            overall_score=overall_score,
            contrast_score=contrast_score,
            sharpness_score=sharpness_score,
            noise_score=noise_score,
            document_type=document_type,
            quality_level=quality_level,
            is_scanned=is_scanned,
            recommended_strategy=recommended_strategy,
            estimated_ocr_quality=estimated_ocr_quality,
            needs_preprocessing=needs_preprocessing,
            details={
                "contrast": contrast_score,
                "sharpness": sharpness_score,
                "noise": noise_score,
                "document_type": document_type.value,
                "is_scanned": is_scanned,
            },
        )

        logger.debug(
            f"[QualityAssessor] Overall: {overall_score:.3f} | "
            f"Contrast: {contrast_score:.3f} | "
            f"Sharpness: {sharpness_score:.3f} | "
            f"Noise: {noise_score:.3f} | "
            f"Strategy: {recommended_strategy}"
        )

        return report

    def _assess_contrast(self, image: np.ndarray) -> float:
        """
        评估对比度

        使用标准差归一化到0-1。
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Standard deviation
        std = np.std(gray)

        # Normalized (typical document contrast ~128)
        score = min(std / 128.0, 1.0)

        return score

    def _assess_sharpness(self, image: np.ndarray) -> float:
        """
        评估清晰度

        使用拉普拉斯方差。
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Laplacian variance
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        # Normalized (typical sharp document 500+)
        score = min(laplacian_var / 500.0, 1.0)

        return score

    def _assess_noise(self, image: np.ndarray) -> float:
        """
        评估噪点水平

        通过与模糊图像的差值计算。
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Gaussian blur
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        # Difference (noise)
        noise = cv2.absdiff(gray, blur)
        noise_level = np.mean(noise)

        # Normalize and invert (lower noise = higher score)
        score = max(0, 1.0 - noise_level / 128.0)

        return score

    def _detect_document_type(self, image: np.ndarray) -> DocumentType:
        """
        检测文档类型

        基于图像特征判断。
        """
        # Simplified: based on color distribution
        if len(image.shape) == 3:
            # Check if grayscale image (scanned document characteristic)
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            color_std = np.std(image, axis=(0, 1)).mean()

            if color_std < 10:
                return DocumentType.SCANNED_PDF
            else:
                return DocumentType.IMAGE
        else:
            return DocumentType.SCANNED_PDF

    def _is_scanned_document(self, image: np.ndarray, quality: float) -> bool:
        """
        判断是否为扫描文档

        特征：
        1. 质量较低
        2. 有噪点
        3. 可能有倾斜
        """
        # Simplified: quality < 0.7 with noise
        if quality < 0.7:
            noise_score = self._assess_noise(image)
            if noise_score < 0.7:
                return True

        return False

    def _classify_quality(self, score: float) -> DocumentQuality:
        """Classify quality grade."""
        if score > 0.8:
            return DocumentQuality.EXCELLENT
        elif score > 0.6:
            return DocumentQuality.GOOD
        elif score > 0.4:
            return DocumentQuality.FAIR
        elif score > 0.2:
            return DocumentQuality.POOR
        else:
            return DocumentQuality.VERY_POOR

    def _predict_ocr_quality(self, overall: float, contrast: float, sharpness: float) -> float:
        """
        预估OCR质量

        基于图像质量指标预测OCR识别率。
        """
        # Empirical formula
        predicted = overall * 0.5 + contrast * 0.2 + sharpness * 0.3

        # Clamp to reasonable range
        predicted = min(max(predicted, 0.1), 0.95)

        return predicted

    def _recommend_strategy(self, quality: DocumentQuality, ocr_quality: float, is_scanned: bool) -> str:
        """
        推荐处理策略

        Returns:
            策略名称
        """
        if quality == DocumentQuality.EXCELLENT:
            return "digital_direct"
        elif quality == DocumentQuality.GOOD:
            return "standard_ocr"
        elif quality == DocumentQuality.FAIR:
            return "enhanced_ocr"
        elif is_scanned or ocr_quality < 0.5:
            return "aggressive_preprocess_ocr"
        else:
            return "standard_ocr"

    def _update_stats(self, quality: DocumentQuality):
        """Update statistics."""
        if quality == DocumentQuality.EXCELLENT:
            self.stats["excellent"] += 1
        elif quality == DocumentQuality.GOOD:
            self.stats["good"] += 1
        elif quality == DocumentQuality.FAIR:
            self.stats["fair"] += 1
        elif quality == DocumentQuality.POOR:
            self.stats["poor"] += 1
        else:
            self.stats["very_poor"] += 1

    def get_stats(self) -> dict[str, Any]:
        """Get evaluation statistics"""
        return self.stats.copy()
