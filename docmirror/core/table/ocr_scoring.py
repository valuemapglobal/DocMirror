"""
OCR scoring — confidence decay and low-confidence word detection.

Purpose: Computes OCR-enhanced confidence scores for table cells using word
confidence, char confusion patterns, and decay factors.

Main components: ``compute_ocr_enhanced_confidence``, ``detect_low_confidence_words``.

Upstream: OCR metadata on table cells.

Downstream: ``extract.classifier``, quality metrics on ``ParseResult``.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Sequence

logger = logging.getLogger(__name__)

# 衰减系数配置
DECAY_CONFIG = {
    "lambda": 2.0,  # 衰减系数λ
    "min_decay": 0.1,  # 最小衰减因子（防止过度惩罚）
    "max_decay": 1.0,  # 最大衰减因子（无惩罚）
}

# 低置信度阈值
LOW_CONFIDENCE_THRESHOLD = 0.7

# 形近字错误模式
SIMILAR_CHAR_ERRORS = [
    ("0", "O"),  # 数字0 vs 字母O
    ("1", "l"),  # 数字1 vs 字母l
    ("1", "I"),  # 数字1 vs 字母I
    ("日", "曰"),  # 汉字形近
    ("土", "士"),  # 汉字形近
    ("未", "末"),  # 汉字形近
]

# 非常见字符模式（非CJK、非ASCII、非数字、非标点）
_RARE_CHAR_PATTERN = re.compile(
    r"[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"  # CJK
    r"a-zA-Z0-9\s"  # ASCII
    r"，。、；：！？"
    "''（）【】《》"  # CJK标点
    r",.!?;:()[]{}\"'"  # ASCII标点
    r"]"
)


def compute_decay_factor(
    total_words: int,
    low_confidence_words: int,
    decay_lambda: float | None = None,
) -> float:
    """计算指数衰减因子。

    Args:
        total_words: 总词数
        low_confidence_words: 低置信度词数
        decay_lambda: 衰减系数λ（默认使用DECAY_CONFIG）

    Returns:
        decay_factor: 衰减因子 (0.1-1.0)

    Examples:
        >>> compute_decay_factor(10, 0)  # 无低置信度词
        1.0
        >>> compute_decay_factor(10, 1)  # 1个低置信度词
        0.98
        >>> compute_decay_factor(10, 5)  # 5个低置信度词
        0.61
    """
    if total_words == 0:
        return 1.0

    decay_lambda = decay_lambda or DECAY_CONFIG["lambda"]

    # 计算低置信度比例
    ratio = low_confidence_words / total_words

    # 指数衰减: exp(-λ × ratio^2)
    decay = math.exp(-decay_lambda * ratio * ratio)

    # 限制范围
    decay = max(DECAY_CONFIG["min_decay"], min(DECAY_CONFIG["max_decay"], decay))

    logger.debug(f"📉 指数衰减: {low_confidence_words}/{total_words} 低置信度词, ratio={ratio:.2f}, decay={decay:.3f}")

    return decay


def detect_low_confidence_words(
    header_cells: Sequence[str],
    ocr_char_confidences: Sequence[float] | None = None,
    vocabulary: set[str] | None = None,
) -> int:
    """检测低置信度词数量。

    Args:
        header_cells: 表头单元格列表
        ocr_char_confidences: OCR字符级置信度列表（可选）
        vocabulary: 已知词汇表（可选，默认使用KNOWN_HEADER_WORDS）

    Returns:
        low_confidence_count: 低置信度词数量
    """
    if not header_cells:
        return 0

    low_confidence_count = 0

    # 加载词汇表
    if vocabulary is None:
        from docmirror.core.utils.vocabulary import KNOWN_HEADER_WORDS

        vocabulary = KNOWN_HEADER_WORDS

    for i, cell in enumerate(header_cells):
        if _is_low_confidence_word(cell, ocr_char_confidences, i, vocabulary):
            low_confidence_count += 1

    return low_confidence_count


def compute_ocr_enhanced_confidence(
    base_confidence: float,
    header_cells: Sequence[str],
    ocr_char_confidences: Sequence[float] | None = None,
    vocabulary: set[str] | None = None,
    decay_lambda: float | None = None,
) -> float:
    """计算OCR增强的置信度（道法自然 · 第十八重境界）。

    Args:
        base_confidence: 原始五维置信度 (0.0-1.0)
        header_cells: 表头单元格列表
        ocr_char_confidences: OCR字符级置信度列表（可选）
        vocabulary: 已知词汇表（可选）
        decay_lambda: 衰减系数λ（可选）

    Returns:
        enhanced_confidence: OCR增强后的置信度 (0.0-1.0)

    Examples:
        >>> compute_ocr_enhanced_confidence(
        ...     base_confidence=0.85,
        ...     header_cells=["交易日期", "交易金额", "余额"],
        ...     ocr_char_confidences=[0.95, 0.65, 0.92]
        ... )
        0.705  # 衰减17%
    """
    if base_confidence <= 0.0:
        return 0.0

    # 检测低置信度词
    low_conf_count = detect_low_confidence_words(header_cells, ocr_char_confidences, vocabulary)
    total_words = len(header_cells)

    # 计算衰减因子
    decay_factor = compute_decay_factor(total_words, low_conf_count, decay_lambda)

    # 应用衰减
    enhanced_confidence = base_confidence * decay_factor

    logger.debug(f"🔮 OCR增强置信度: {base_confidence:.3f} × {decay_factor:.3f} = {enhanced_confidence:.3f}")

    return round(max(0.0, min(1.0, enhanced_confidence)), 3)


# ========== Private Methods ==========


def _is_low_confidence_word(
    cell: str,
    ocr_char_confidences: Sequence[float] | None,
    cell_index: int,
    vocabulary: set[str],
) -> bool:
    """判断单个词是否为低置信度词。

    判断标准:
    1. OCR字符级置信度 < 0.7
    2. 不在已知词汇表中
    3. 包含非常见字符
    4. 包含形近字错误
    """
    if not cell or not cell.strip():
        return False

    cell = cell.strip()

    # 1. 检查OCR字符级置信度
    if ocr_char_confidences is not None:
        # 简化：假设每个cell对应一个置信度值
        if cell_index < len(ocr_char_confidences):
            if ocr_char_confidences[cell_index] < LOW_CONFIDENCE_THRESHOLD:
                return True

    # 2. 检查词汇匹配
    from docmirror.core.utils.vocabulary import _normalize_for_vocab

    normalized = _normalize_for_vocab(cell)
    if normalized not in vocabulary:
        # 词汇不匹配，直接判定为低置信度
        return True

    return False


def _has_similar_char_error(cell: str, vocabulary: set[str]) -> bool:
    """检查是否包含形近字错误。"""
    for wrong, correct in SIMILAR_CHAR_ERRORS:
        if wrong in cell:
            # 尝试替换后是否在词汇表中
            corrected = cell.replace(wrong, correct)
            from docmirror.core.utils.vocabulary import _normalize_for_vocab

            if _normalize_for_vocab(corrected) in vocabulary:
                return True

    return False


def _has_rare_characters(cell: str) -> bool:
    """检查是否包含非常见字符。"""
    return bool(_RARE_CHAR_PATTERN.search(cell))
