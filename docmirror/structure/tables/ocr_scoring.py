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
from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Decay coefficient configuration
DECAY_CONFIG = {
    "lambda": 2.0,  # decay coefficient lambda
    "min_decay": 0.1,  # minimum decay factor (prevents over-penalty)
    "max_decay": 1.0,  # maximum decay factor (no penalty)
}

# Low confidence threshold
LOW_CONFIDENCE_THRESHOLD = 0.7

# Visually similar character error patterns
SIMILAR_CHAR_ERRORS = [
    ("0", "O"),  # digit 0 vs letter O
    ("1", "l"),  # digit 1 vs letter l
    ("1", "I"),  # digit 1 vs letter I
    ("日", "曰"),  # visually similar CJK characters
    ("土", "士"),  # visually similar CJK characters
    ("未", "末"),  # visually similar CJK characters
]

# Uncommon character patterns (non-CJK, non-ASCII, non-digit, non-punctuation)
_RARE_CHAR_PATTERN = re.compile(
    r"[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"  # CJK
    r"a-zA-Z0-9\s"  # ASCII
    r"，。、；：！？"
    "''（）【】《》"  # CJK punctuation
    r",.!?;:()[]{}\"'"  # ASCII punctuation
    r"]"
)


def compute_decay_factor(
    total_words: int,
    low_confidence_words: int,
    decay_lambda: float | None = None,
) -> float:
    """Compute exponential decay factor.

    Args:
        total_words: Total word count
        low_confidence_words: Low-confidence word count
        decay_lambda: decay coefficient lambda (defaults to DECAY_CONFIG)

    Returns:
        decay_factor: Decay factor (0.1-1.0)

    Examples:
        >>> compute_decay_factor(10, 0)  # no low-confidence words
        1.0
        >>> compute_decay_factor(10, 1)  # 1 low-confidence word
        0.98
        >>> compute_decay_factor(10, 5)  # 5 low-confidence words
        0.61
    """
    if total_words == 0:
        return 1.0

    decay_lambda = decay_lambda or DECAY_CONFIG["lambda"]

    # Compute low confidence ratio
    ratio = low_confidence_words / total_words

    # Exponential decay: exp(-lambda * ratio^2)
    decay = math.exp(-decay_lambda * ratio * ratio)

    # Clamp to range
    decay = max(DECAY_CONFIG["min_decay"], min(DECAY_CONFIG["max_decay"], decay))

    logger.debug(f"📉 Exponential decay: {low_confidence_words}/{total_words} low-confidence words, ratio={ratio:.2f}, decay={decay:.3f}")

    return decay


def detect_low_confidence_words(
    header_cells: Sequence[str],
    ocr_char_confidences: Sequence[float] | None = None,
    vocabulary: set[str] | None = None,
) -> int:
    """Detect low-confidence word count.

    Args:
        header_cells: Header cell list
        ocr_char_confidences: OCR character-level confidence list (optional)
        vocabulary: Known vocabulary set (optional, defaults to KNOWN_HEADER_WORDS)

    Returns:
        low_confidence_count: Low-confidence word count
    """
    if not header_cells:
        return 0

    low_confidence_count = 0

    # Load vocabulary
    if vocabulary is None:
        from docmirror.structure.utils.vocabulary import KNOWN_HEADER_WORDS

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
    """Compute OCR-enhanced confidence.

    Args:
        base_confidence: Base confidence (0.0-1.0)
        header_cells: Header cell list
        ocr_char_confidences: OCR character-level confidence list (optional)
        vocabulary: Known vocabulary set (optional)
        decay_lambda: Decay coefficient lambda (optional)

    Returns:
        enhanced_confidence: OCR-enhanced confidence (0.0-1.0)

    Examples:
        >>> compute_ocr_enhanced_confidence(
        ...     base_confidence=0.85,
        ...     header_cells=["交易日期", "交易金额", "余额"],
        ...     ocr_char_confidences=[0.95, 0.65, 0.92]
        ... )
        0.705  # 17% decay
    """
    if base_confidence <= 0.0:
        return 0.0

    # Detect low confidence words
    low_conf_count = detect_low_confidence_words(header_cells, ocr_char_confidences, vocabulary)
    total_words = len(header_cells)

    # Compute decay factor
    decay_factor = compute_decay_factor(total_words, low_conf_count, decay_lambda)

    # Apply decay
    enhanced_confidence = base_confidence * decay_factor

    logger.debug(f"🔮 OCR-enhanced confidence: {base_confidence:.3f} × {decay_factor:.3f} = {enhanced_confidence:.3f}")

    return round(max(0.0, min(1.0, enhanced_confidence)), 3)


# ========== Private Methods ==========


def _is_low_confidence_word(
    cell: str,
    ocr_char_confidences: Sequence[float] | None,
    cell_index: int,
    vocabulary: set[str],
) -> bool:
    """Determine whether a single word is low-confidence.

    Criteria:
    1. OCR character-level confidence < 0.7
    2. Not in known vocabulary
    3. Contains uncommon characters
    4. Contains visually similar character errors
    """
    if not cell or not cell.strip():
        return False

    cell = cell.strip()

    # 1. Check OCR character-level confidence
    if ocr_char_confidences is not None:
        # Simplified: assume each cell maps to one confidence value
        if cell_index < len(ocr_char_confidences):
            if ocr_char_confidences[cell_index] < LOW_CONFIDENCE_THRESHOLD:
                return True

    # 2. Check vocabulary match
    from docmirror.structure.utils.vocabulary import _normalize_for_vocab

    normalized = _normalize_for_vocab(cell)
    if normalized not in vocabulary:
        # Vocabulary mismatch, directly mark as low confidence
        return True

    return False


def _has_similar_char_error(cell: str, vocabulary: set[str]) -> bool:
    """Check whether it contains visually-similar character errors."""
    for wrong, correct in SIMILAR_CHAR_ERRORS:
        if wrong in cell:
            # Check if in vocabulary after substitution
            corrected = cell.replace(wrong, correct)
            from docmirror.structure.utils.vocabulary import _normalize_for_vocab

            if _normalize_for_vocab(corrected) in vocabulary:
                return True

    return False


def _has_rare_characters(cell: str) -> bool:
    """Check whether it contains uncommon characters."""
    return bool(_RARE_CHAR_PATTERN.search(cell))
