"""Tests for OCR scoring optimization (道法自然 · 第十八重境界)."""
from __future__ import annotations

import math
import pytest

from docmirror.core.table.ocr_scoring import (
    compute_decay_factor,
    detect_low_confidence_words,
    compute_ocr_enhanced_confidence,
    DECAY_CONFIG,
    LOW_CONFIDENCE_THRESHOLD,
)


class TestDecayFactor:
    """Test exponential decay factor calculation."""

    def test_no_low_confidence_words(self):
        """Test decay factor with no low confidence words."""
        decay = compute_decay_factor(10, 0)
        assert decay == 1.0

    def test_one_low_confidence_word(self):
        """Test decay factor with 1 low confidence word (10%)."""
        decay = compute_decay_factor(10, 1)
        # exp(-2.0 * 0.1^2) = exp(-0.02) ≈ 0.98
        assert 0.97 <= decay <= 0.99

    def test_three_low_confidence_words(self):
        """Test decay factor with 3 low confidence words (30%)."""
        decay = compute_decay_factor(10, 3)
        # exp(-2.0 * 0.3^2) = exp(-0.18) ≈ 0.83
        assert 0.82 <= decay <= 0.84

    def test_five_low_confidence_words(self):
        """Test decay factor with 5 low confidence words (50%)."""
        decay = compute_decay_factor(10, 5)
        # exp(-2.0 * 0.5^2) = exp(-0.5) ≈ 0.61
        assert 0.60 <= decay <= 0.62

    def test_all_low_confidence_words(self):
        """Test decay factor with all low confidence words (100%)."""
        decay = compute_decay_factor(10, 10)
        # exp(-2.0 * 1.0^2) = exp(-2.0) ≈ 0.14
        assert 0.13 <= decay <= 0.15

    def test_exponential_characteristic(self):
        """Test that decay is exponential, not linear."""
        decay_1 = compute_decay_factor(10, 1)
        decay_3 = compute_decay_factor(10, 3)
        decay_5 = compute_decay_factor(10, 5)

        # 指数衰减应该比线性衰减更快
        # 线性: 1个=0.9, 3个=0.7, 5个=0.5
        # 指数: 1个≈0.98, 3个≈0.83, 5个≈0.61
        assert decay_1 > 0.95  # 指数衰减更慢
        assert decay_3 < 0.85  # 指数衰减更快
        assert decay_5 < 0.65

    def test_custom_lambda(self):
        """Test decay factor with custom lambda."""
        decay_strong = compute_decay_factor(10, 3, decay_lambda=5.0)
        decay_weak = compute_decay_factor(10, 3, decay_lambda=0.5)

        assert decay_strong < decay_weak  # 更大的λ → 更强的衰减

    def test_min_decay_boundary(self):
        """Test minimum decay boundary."""
        decay = compute_decay_factor(1, 1)  # 100%低置信度
        assert decay >= DECAY_CONFIG["min_decay"]

    def test_max_decay_boundary(self):
        """Test maximum decay boundary."""
        decay = compute_decay_factor(10, 0)
        assert decay <= DECAY_CONFIG["max_decay"]

    def test_empty_words(self):
        """Test decay factor with empty words."""
        decay = compute_decay_factor(0, 0)
        assert decay == 1.0


class TestLowConfidenceDetection:
    """Test low confidence word detection."""

    def test_all_known_words(self):
        """Test detection with all known words."""
        cells = ["交易日期", "交易金额", "余额"]
        low_conf = detect_low_confidence_words(cells)
        assert low_conf == 0

    def test_ocr_error_similar_char(self):
        """Test detection with OCR similar character error."""
        # "交另日期" 中的 "另" 是 "易" 的形近字错误
        cells = ["交另日期", "交易金额", "余额"]
        low_conf = detect_low_confidence_words(cells)
        assert low_conf >= 1  # 至少检测到1个形近字错误

    def test_rare_characters(self):
        """Test detection with rare characters."""
        # 包含非常见字符
        cells = ["交易€期", "交易金额", "余额"]
        low_conf = detect_low_confidence_words(cells)
        assert low_conf >= 1  # 检测到非常见字符

    def test_ocr_char_confidence(self):
        """Test detection with OCR character confidence."""
        cells = ["交易日期", "交易金额", "余额"]
        # 第二个词置信度低
        ocr_conf = [0.95, 0.65, 0.92]
        low_conf = detect_low_confidence_words(cells, ocr_conf)
        assert low_conf == 1

    def test_empty_cells(self):
        """Test detection with empty cells."""
        low_conf = detect_low_confidence_words([])
        assert low_conf == 0

    def test_mixed_errors(self):
        """Test detection with mixed error types."""
        cells = [
            "交易日期",      # 正常
            "交另金额",      # 形近字错误
            "余额€",         # 非常见字符
            "未知字段",      # 词汇不匹配
        ]
        low_conf = detect_low_confidence_words(cells)
        assert low_conf >= 2  # 至少检测到2个错误


class TestOCREnhancedConfidence:
    """Test OCR-enhanced confidence calculation."""

    def test_no_decay_perfect_header(self):
        """Test no decay with perfect header."""
        enhanced = compute_ocr_enhanced_confidence(
            base_confidence=0.85,
            header_cells=["交易日期", "交易金额", "余额"],
        )
        # 无低置信度词，应该接近原始值
        assert 0.83 <= enhanced <= 0.85

    def test_decay_with_ocr_errors(self):
        """Test decay with OCR errors."""
        enhanced = compute_ocr_enhanced_confidence(
            base_confidence=0.85,
            header_cells=["交另日期", "交易金颔", "余额"],  # 2个词汇不匹配
        )
        # 应该有显著衰减 (2/3 = 67%低置信度)
        assert enhanced < 0.50  # 衰减超过40%

    def test_severe_decay_many_errors(self):
        """Test severe decay with many errors."""
        enhanced = compute_ocr_enhanced_confidence(
            base_confidence=0.90,
            header_cells=["交另€期", "交易金颔", "未知€"],  # 全部词汇不匹配
        )
        # 应该有严重衰减 (3/3 = 100%低置信度)
        assert enhanced < 0.20  # 衰减超过75%

    def test_zero_base_confidence(self):
        """Test with zero base confidence."""
        enhanced = compute_ocr_enhanced_confidence(
            base_confidence=0.0,
            header_cells=["交易日期"],
        )
        assert enhanced == 0.0

    def test_with_ocr_confidences(self):
        """Test with explicit OCR confidences."""
        enhanced = compute_ocr_enhanced_confidence(
            base_confidence=0.85,
            header_cells=["交易日期", "交易金额", "余额"],
            ocr_char_confidences=[0.95, 0.65, 0.92],  # 第二个词低置信度
        )
        assert enhanced < 0.85  # 应该有衰减

    def test_custom_decay_lambda(self):
        """Test with custom decay lambda."""
        # 使用有多个错误的表头才能看到差异
        header = ["交另日期", "交易金颔", "未知€"]
        enhanced_strong = compute_ocr_enhanced_confidence(
            base_confidence=0.85,
            header_cells=header,
            decay_lambda=5.0,  # 强衰减
        )
        enhanced_weak = compute_ocr_enhanced_confidence(
            base_confidence=0.85,
            header_cells=header,
            decay_lambda=0.5,  # 弱衰减
        )
        assert enhanced_strong < enhanced_weak

    def test_deterministic(self):
        """Test calculation is deterministic."""
        result1 = compute_ocr_enhanced_confidence(
            base_confidence=0.85,
            header_cells=["交另日期", "交易金额", "余额"],
        )
        result2 = compute_ocr_enhanced_confidence(
            base_confidence=0.85,
            header_cells=["交另日期", "交易金额", "余额"],
        )
        assert result1 == result2

    def test_bounded_output(self):
        """Test output is bounded [0, 1]."""
        enhanced = compute_ocr_enhanced_confidence(
            base_confidence=0.95,
            header_cells=["错误1", "错误2", "错误3"],  # 假设全部错误
        )
        assert 0.0 <= enhanced <= 1.0


class TestIntegration:
    """Test integration with confidence formula."""

    def test_realistic_scenario_good_ocr(self):
        """Test realistic scenario with good OCR."""
        # 高质量PDF，OCR准确
        base_conf = 0.88
        header = ["交易日期", "交易金额", "交易笔数", "余额"]
        ocr_conf = [0.98, 0.96, 0.95, 0.97]

        enhanced = compute_ocr_enhanced_confidence(base_conf, header, ocr_conf)

        # 高质量OCR，衰减很小（但“交易笔数”不在词汇表中，会有1/4=25%低置信度）
        assert enhanced >= 0.75  # 衰减不超过15%

    def test_realistic_scenario_poor_ocr(self):
        """Test realistic scenario with poor OCR."""
        # 低质量扫描，OCR错误多
        base_conf = 0.82
        header = ["交另€期", "交易金颔", "交易笔€", "余额"]
        ocr_conf = [0.65, 0.72, 0.68, 0.88]

        enhanced = compute_ocr_enhanced_confidence(base_conf, header, ocr_conf)

        # 低质量OCR，衰减明显
        assert enhanced < 0.70

    def test_decay_ratio_curve(self):
        """Test decay factor follows exponential curve."""
        ratios = []
        for low_conf_count in range(0, 11):
            decay = compute_decay_factor(10, low_conf_count)
            ratios.append(decay)

        # 验证指数衰减曲线
        assert ratios[0] == 1.0  # 0% → 1.0
        assert ratios[5] < 0.65  # 50% → <0.65
        assert ratios[10] < 0.15  # 100% → <0.15

        # 验证单调递减
        for i in range(len(ratios) - 1):
            assert ratios[i] >= ratios[i + 1]
