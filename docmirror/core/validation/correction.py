# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Self-Correction Engine — 自纠错引擎
====================================

基于第一性原理的自纠错：发现错误并自动修正。

Design Principle (道德经):
    "胜人者有力，自胜者强" — 能纠正自己的错误才是真正强大。
    "学不学，复众人之所过" — 从错误中学习，避免重复犯错。

Core Philosophy:
    纠错策略：
    1. OCR错误修正（0↔O, 1↔I, 5↔S）
    2. 格式修正（2024.1.5 → 2024-01-05）
    3. 类型转换（"1,000" → 1000.0）
    4. 逻辑修正（根据上下文推断正确值）

Usage::

    from docmirror.core.validation.correction import SelfCorrectionEngine

    # 纠正错误
    result = SelfCorrectionEngine.correct(table, validation_errors)

    logger.info(f"修正了 {result['correction_count']} 个错误，修正率: {result['correction_rate']:.2%}")

    # 使用修正后的表格
    corrected_table = result['corrected_table']
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .semantic import ValidationError

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Self-Correction Engine
# ═══════════════════════════════════════════════════════════════════════════════


class SelfCorrectionEngine:
    """
    自纠错引擎 — 发现错误并自动修正

    纠错策略：
        1. OCR错误修正（0↔O, 1↔I, 5↔S）
        2. 格式修正（2024.1.5 → 2024-01-05）
        3. 类型转换（"1,000" → 1000.0）
        4. 逻辑修正（根据上下文推断正确值）
    """

    # OCR常见错误映射
    OCR_ERROR_MAP = {
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "S": "5",
        "s": "5",
        "B": "8",
        "b": "8",
        "Z": "2",
        "z": "2",
    }

    @classmethod
    def correct(
        cls, table: list[list[str]], errors: list[ValidationError], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        纠正验证发现的错误

        Args:
            table: 原始表格
            errors: 验证错误列表
            context: 上下文信息（可选）

        Returns:
            {
                'corrected_table': 修正后的表格,
                'corrections': 修正记录列表,
                'remaining_errors': 未修正的错误,
                'correction_count': 修正数量,
                'correction_rate': 修正率
            }
        """
        if not errors:
            return {
                "corrected_table": table,
                "corrections": [],
                "remaining_errors": [],
                "correction_count": 0,
                "correction_rate": 1.0,
            }

        # 深拷贝表格
        corrected_table = [row[:] for row in table]
        corrections = []
        remaining_errors = []

        for error in errors:
            row_idx = error.row
            col_idx = error.col
            original_value = table[row_idx][col_idx]
            error_type = error.error_type
            error_msg = error.error

            # 尝试修正
            corrected_value, method = cls._try_correct(original_value, error_msg, error.col_name)

            if corrected_value is not None and corrected_value != original_value:
                # 应用修正
                corrected_table[row_idx][col_idx] = corrected_value
                corrections.append(
                    {
                        "row": row_idx,
                        "col": col_idx,
                        "col_name": error.col_name,
                        "original": original_value,
                        "corrected": corrected_value,
                        "method": method,
                        "error": error_msg,
                    }
                )
            else:
                # 无法修正
                remaining_errors.append(error)

        correction_rate = len(corrections) / max(1, len(errors))

        logger.info(f"[SelfCorrection] Corrected {len(corrections)}/{len(errors)} errors (rate={correction_rate:.2%})")

        return {
            "corrected_table": corrected_table,
            "corrections": corrections,
            "remaining_errors": remaining_errors,
            "correction_count": len(corrections),
            "correction_rate": correction_rate,
        }

    @classmethod
    def _try_correct(cls, value: str, error_msg: str, col_name: str) -> tuple[str | None, str]:
        """
        尝试纠正错误

        Returns:
            (corrected_value, method) 或 (None, '')
        """
        # 1. OCR错误修正
        if "格式" in error_msg or "无效" in error_msg:
            corrected = cls._correct_ocr_errors(value)
            if corrected:
                return corrected, "ocr_correction"

        # 2. 日期格式修正
        if "日期" in error_msg or "date" in error_msg.lower():
            corrected = cls._correct_date_format(value)
            if corrected:
                return corrected, "date_format_correction"

        # 3. 数字格式修正
        if "数字" in error_msg or "数值" in error_msg or "number" in error_msg.lower():
            corrected = cls._correct_number_format(value)
            if corrected:
                return corrected, "number_format_correction"

        # 4. 逻辑修正（根据上下文）
        if "不匹配" in error_msg or "余额" in col_name:
            corrected = cls._correct_logic_error(value, error_msg, col_name)
            if corrected:
                return corrected, "logic_correction"

        return None, ""

    @classmethod
    def _correct_ocr_errors(cls, value: str) -> str | None:
        """
        纠正OCR常见错误

        规则：
        - O/o → 0
        - I/l/| → 1
        - S/s → 5
        """
        if not value:
            return None

        corrected = value
        for wrong_char, right_char in cls.OCR_ERROR_MAP.items():
            corrected = corrected.replace(wrong_char, right_char)

        return corrected if corrected != value else None

    @classmethod
    def _correct_date_format(cls, value: str) -> str | None:
        """
        纠正日期格式

        规则：
        - 2024.1.5 → 2024-01-05
        - 20240115 → 2024-01-15
        - 2024年1月5日 → 2024-01-05
        """
        if not value:
            return None

        # 清理
        cleaned = value

        # 2024.1.5 或 2024/1/5
        match = re.match(r"(\d{4})[./](\d{1,2})[./](\d{1,2})", cleaned)
        if match:
            year, month, day = match.groups()
            try:
                dt = datetime(int(year), int(month), int(day))
                return dt.strftime("%Y-%m-%d")
            except ValueError as e:
                # 预期的异常：无效日期（如月=13）
                logger.debug(f"日期格式纠正失败 '{value}': {e}")
                pass  # 尝试下一个格式

        # 20240115
        match = re.match(r"(\d{4})(\d{2})(\d{2})", cleaned)
        if match:
            year, month, day = match.groups()
            try:
                dt = datetime(int(year), int(month), int(day))
                return dt.strftime("%Y-%m-%d")
            except ValueError as e:
                # 预期的异常：无效日期（如月=13）
                logger.debug(f"日期格式纠正失败 '{value}': {e}")
                pass  # 尝试下一个格式

        # 2024年1月5日
        match = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", cleaned)
        if match:
            year, month, day = match.groups()
            try:
                dt = datetime(int(year), int(month), int(day))
                return dt.strftime("%Y-%m-%d")
            except ValueError as e:
                # 预期的异常：无效日期（如月=13）
                logger.debug(f"日期格式纠正失败 '{value}': {e}")
                pass  # 尝试下一个格式

        return None

    @classmethod
    def _correct_number_format(cls, value: str) -> str | None:
        """
        纠正数字格式

        规则：
        - 1,000.50 → 1000.50
        - （1000） → -1000（会计格式）
        """
        if not value:
            return None

        cleaned = value.strip()

        # 会计格式（括号表示负数）
        match = re.match(r"\((.+)\)", cleaned)
        if match:
            inner = match.group(1).replace(",", "")
            try:
                num = float(inner)
                return f"-{num:.2f}"
            except (ValueError, TypeError) as e:
                # 预期的异常：不是有效数字
                logger.debug(f"会计格式纠正失败 '{value}': {e}")
                pass

        # 清理千位分隔符
        cleaned = cleaned.replace(",", "").replace("，", "")

        try:
            num = float(cleaned)
            # 如果是整数，返回整数格式
            if num == int(num):
                return str(int(num))
            return str(num)
        except (ValueError, TypeError) as e:
            # 预期的异常：不是有效数字
            logger.debug(f"数字格式纠正失败 '{value}': {e}")
            pass

        return None

    @classmethod
    def _correct_logic_error(cls, value: str, error_msg: str, col_name: str) -> str | None:
        """
        尝试逻辑修正

        注：这需要更多上下文信息，这里是简化实现
        """
        # 如果是余额不匹配，可以尝试从上下文推断
        # 但这需要知道前一行余额和当前行借贷方
        # 这里返回None，表示需要人工审核
        return None
