# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
"""
Enhanced OCR Module — 增强OCR模块
====================================

领域感知OCR后处理：根据列类型智能选择纠错策略。

Usage::

    from docmirror.core.enhanced_ocr import ContextAwareOCRPostProcessor

    corrected = ContextAwareOCRPostProcessor.correct(
        'O,l00.50',
        {'column_type': 'amount', 'column_name': '金额'}
    )
    # Result: '0,100.50'
"""

from .domain_aware_postprocessor import (
    ColumnConstraints,
    ContextAwareOCRPostProcessor,
)

__all__ = [
    "ContextAwareOCRPostProcessor",
    "ColumnConstraints",
]
