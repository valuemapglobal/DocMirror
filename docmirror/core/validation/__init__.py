# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
"""
Validation Module — 验证模块
=============================

反向验证与自纠错系统的统一入口。

Usage::

    from docmirror.core.validation import validate_and_correct

    # 一步完成验证和纠错
    result = validate_and_correct(table, header)

    if result['is_valid']:
        logger.info("验证通过！")
    else:
        logger.warning(
            f"修正了 {result['correction_count']} 个错误，"
            f"剩余 {len(result['remaining_errors'])} 个错误需要人工审核"
        )
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from .correction import SelfCorrectionEngine
from .logic import LogicValidator
from .semantic import SemanticValidator, ValidationResult


def validate_and_correct(
    table: list[list[str]], header: list[str] | None = None, enable_correction: bool = True
) -> dict[str, Any]:
    """
    验证并纠正表格

    流程：
        1. 语义验证
        2. 逻辑验证
        3. 自纠错（如启用）
        4. 再次验证

    Args:
        table: 表格数据
        header: 表头
        enable_correction: 是否启用纠错

    Returns:
        {
            'is_valid': 是否最终通过验证,
            'corrected_table': 修正后的表格,
            'semantic_result': 语义验证结果,
            'logic_result': 逻辑验证结果,
            'corrections': 修正记录,
            'remaining_errors': 剩余错误,
            'correction_rate': 修正率
        }
    """
    # 1. 语义验证
    semantic_result = SemanticValidator.validate(table, header)

    # 2. 逻辑验证
    logic_result = LogicValidator.validate(table, header)

    # 合并错误
    all_errors = semantic_result.errors + logic_result.errors

    # 3. 自纠错（如启用且有错误）
    corrections = []
    remaining_errors = all_errors
    corrected_table = table

    if enable_correction and all_errors:
        correction_result = SelfCorrectionEngine.correct(table, all_errors)
        corrected_table = correction_result["corrected_table"]
        corrections = correction_result["corrections"]
        remaining_errors = correction_result["remaining_errors"]

        # 4. 再次验证修正后的表格
        re_semantic = SemanticValidator.validate(corrected_table, header)
        re_logic = LogicValidator.validate(corrected_table, header)

        semantic_result = re_semantic
        logic_result = re_logic

    # 最终是否通过
    is_valid = len(remaining_errors) == 0

    return {
        "is_valid": is_valid,
        "corrected_table": corrected_table,
        "semantic_result": semantic_result,
        "logic_result": logic_result,
        "corrections": corrections,
        "remaining_errors": remaining_errors,
        "correction_count": len(corrections),
        "correction_rate": len(corrections) / max(1, len(all_errors)),
    }


__all__ = [
    "SemanticValidator",
    "LogicValidator",
    "SelfCorrectionEngine",
    "validate_and_correct",
]
