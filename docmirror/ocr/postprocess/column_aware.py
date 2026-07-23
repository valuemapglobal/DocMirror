# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Column-aware OCR postprocessor — layout-constrained text correction.

Purpose: Uses ``ColumnConstraints`` and neighbor context to fix OCR errors
per column (amounts, dates, IDs) without cross-column bleed.

Main components: ``ContextAwareOCRPostProcessor``, ``ColumnConstraints``.

Upstream: OCR output + column anchor geometry.

Downstream: ``table.ocr_scoring``, normalized table cells.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Column Type Constraints
# ═══════════════════════════════════════════════════════════════════════════════


class ColumnConstraints:
    """Column type constraint definitions."""

    # Amount column constraints
    AMOUNT = {
        "allowed_chars": set("0123456789,.- "),
        "common_errors": {
            "O": "0",
            "o": "0",
            "l": "1",
            "I": "1",
            "|": "1",
            "S": "5",
            "s": "5",
            "B": "8",
            "b": "8",
            "Z": "2",
            "z": "2",
        },
        "pattern": r"^[0-9,.\- ]+$",
        "format_pattern": r"^-?[0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?$",
    }

    # Date column constraints
    DATE = {
        "allowed_chars": set("0123456789/-年月日.:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"),
        "common_errors": {
            "l": "1",
            "I": "1",
            "|": "1",
            "O": "0",
            "o": "0",
        },
        "pattern": r"^[0-9/\-年月日.]+$",
        "format_pattern": r"^\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}[日号]?( \d{1,2}:\d{2}(:\d{2})?)?$",
    }

    # ID number constraints
    ID_NUMBER = {
        "allowed_chars": set("0123456789Xx"),
        "common_errors": {
            "O": "0",
            "o": "0",
            "l": "1",
            "I": "1",
            "|": "1",
        },
        "pattern": r"^\d{17}[\dXx]$",
        "format_pattern": r"^\d{17}[\dXx]$",
    }

    # Phone number constraints
    PHONE = {
        "allowed_chars": set("0123456789- ()+#*"),
        "common_errors": {
            "O": "0",
            "o": "0",
            "l": "1",
            "I": "1",
        },
        "pattern": r"^[0-9\- ()]+$",
        "format_pattern": r"^\+?1?[3-9]\d{9}$",
    }

    # Text column (no constraints)
    TEXT = {
        "allowed_chars": None,  # no restrictions
        "common_errors": {},
        "pattern": None,
        "format_pattern": None,
    }

    # Column type mapping
    COLUMN_TYPE_MAP = {
        "amount": AMOUNT,
        "balance": AMOUNT,
        "debit": AMOUNT,
        "credit": AMOUNT,
        "date": DATE,
        "time": DATE,
        "id_number": ID_NUMBER,
        "phone": PHONE,
        "mobile": PHONE,
        "text": TEXT,
        "description": TEXT,
        "note": TEXT,
    }

    @classmethod
    def get_constraints(cls, column_type: str) -> dict[str, Any]:
        """Get column type constraints."""
        return cls.COLUMN_TYPE_MAP.get(column_type, cls.TEXT)


# ═══════════════════════════════════════════════════════════════════════════════
# Context-Aware OCR Post-Processor
# ═══════════════════════════════════════════════════════════════════════════════


class ContextAwareOCRPostProcessor:
    """
    上下文感知的OCR后处理器

    核心哲学：
        天下难事，必作于易：利用列类型简化纠错
        天下大事，必作于细：在微观层面精确纠错

    纠错策略：
        1. 列类型约束（最强）
        2. 格式验证与修复
        3. 相邻行校验
        4. 领域字典增强
    """

    @classmethod
    def correct(cls, text: str, column_context: dict[str, Any]) -> str:
        """
        上下文感知的OCR纠错

        Args:
            text: OCR识别的文本
            column_context: 列上下文信息
                {
                    'column_type': 'amount',  # 列类型
                    'column_name': '金额',     # 列名
                    'adjacent_values': [...],  # 相邻行的值
                    'domain_dict': {},         # 领域字典
                    'row_index': 5             # 行索引
                }

        Returns:
            纠错后的文本
        """
        if not text or not text.strip():
            return text

        column_type = column_context.get("column_type", "text")
        constraints = ColumnConstraints.get_constraints(column_type)

        original_text = text

        # 1. Column type constraint correction (strongest)
        if column_type != "text":
            text = cls._correct_by_column_constraints(text, constraints)

        # 2. Format validation and repair
        if constraints.get("format_pattern"):
            text = cls._correct_by_format(text, constraints["format_pattern"])

        # 3. Adjacent row validation
        adjacent_values = column_context.get("adjacent_values", [])
        if adjacent_values:
            text = cls._correct_by_adjacent_rows(text, adjacent_values, column_type)

        # 4. Domain dictionary enhancement
        domain_dict = column_context.get("domain_dict", {})
        if domain_dict:
            text = cls._correct_by_domain_dict(text, domain_dict)

        # Log corrections
        if text != original_text:
            logger.debug(f"[OCRPostProcessor] Corrected '{original_text}' → '{text}' (column_type={column_type})")

        return text

    @classmethod
    def _correct_by_column_constraints(cls, text: str, constraints: dict) -> str:
        """
        基于列类型约束纠错

        规则：
        1. 应用常见错误映射（O→0, l→1）
        2. 移除不允许的字符
        """
        common_errors = constraints.get("common_errors", {})
        allowed_chars = constraints.get("allowed_chars")

        # 1. Apply common error mappings
        for wrong_char, correct_char in common_errors.items():
            text = text.replace(wrong_char, correct_char)

        # 2. Remove disallowed characters
        if allowed_chars:
            text = "".join(char for char in text if char in allowed_chars or char.isspace())

        return text

    @classmethod
    def _correct_by_format(cls, text: str, format_pattern: str) -> str:
        """
        基于格式模式修复

        尝试：
        1. 如果匹配，直接返回
        2. 如果不匹配，尝试修复
        """
        # If already matched, return directly
        if re.match(format_pattern, text):
            return text

        # Attempt repair (simplified implementation)
        # For amounts: remove extraneous characters
        if format_pattern == r"^-?[0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?$":
            text = cls._fix_amount_format(text)

        # For dates: normalize format
        elif format_pattern == r"^\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}[日号]?$":
            text = cls._fix_date_format(text)

        return text

    @classmethod
    def _fix_amount_format(cls, text: str) -> str:
        """Fix amount format."""
        # Remove non-numeric characters (except ,. -)
        text = re.sub(r"[^0-9,.\- ]", "", text)

        # Clean up extra decimal points
        parts = text.split(".")
        if len(parts) > 2:
            text = parts[0] + "." + "".join(parts[1:])

        return text

    @classmethod
    def _fix_date_format(cls, text: str) -> str:
        """Fix date format."""
        # Normalize separators
        text = re.sub(r"[年月日]", "-", text)
        text = re.sub(r"[/\.]", "-", text)

        # Remove extra hyphens
        text = re.sub(r"-+", "-", text)
        text = text.strip("-")

        return text

    @classmethod
    def _correct_by_adjacent_rows(cls, text: str, adjacent_values: list[str], column_type: str) -> str:
        """
        基于相邻行校验纠错

        逻辑：
        1. 检查格式一致性
        2. 检查值域合理性
        """
        if not adjacent_values:
            return text

        # Check format consistency
        if column_type == "date":
            dominant_format = cls._find_dominant_date_format(adjacent_values)
            if dominant_format:
                text = cls._normalize_date_format(text, dominant_format)

        elif column_type == "amount":
            # Check thousand separator consistency
            if "," in text and not any("," in v for v in adjacent_values[:5]):
                text = text.replace(",", "")
            elif "," not in text and all("," in v for v in adjacent_values[:5]):
                # Add thousand separators
                text = cls._add_thousands_separator(text)

        return text

    @classmethod
    def _find_dominant_date_format(cls, dates: list[str]) -> str | None:
        """Find dominant date format."""
        formats = []
        for date in dates:
            if re.match(r"\d{4}-\d{2}-\d{2}", date):
                formats.append("YYYY-MM-DD")
            elif re.match(r"\d{4}/\d{2}/\d{2}", date):
                formats.append("YYYY/MM/DD")
            elif re.match(r"\d{4}年\d{1,2}月\d{1,2}日", date):
                formats.append("YYYY年MM月DD日")

        if not formats:
            return None

        return Counter(formats).most_common(1)[0][0]

    @classmethod
    def _normalize_date_format(cls, date: str, target_format: str) -> str:
        """Standardize date format."""
        # Attempt to parse
        cleaned = re.sub(r"[年/\.月日号]", "-", date).strip("-")

        formats = ["%Y-%m-%d", "%m-%d", "%Y%m%d"]
        for fmt in formats:
            try:
                dt = datetime.strptime(cleaned, fmt)

                if target_format == "YYYY-MM-DD":
                    return dt.strftime("%Y-%m-%d")
                elif target_format == "YYYY/MM/DD":
                    return dt.strftime("%Y/%m/%d")
                elif target_format == "YYYY年MM月DD日":
                    return dt.strftime("%Y年%m月%d日")
            except ValueError:
                # Expected exception: date format mismatch
                continue

        return date

    @classmethod
    def _add_thousands_separator(cls, text: str) -> str:
        """Add thousand separators."""
        try:
            # Separate integer and decimal parts
            if "." in text:
                int_part, dec_part = text.split(".")
            else:
                int_part = text
                dec_part = ""

            # Add thousand separators
            int_part = f"{int(int_part):,}"

            if dec_part:
                return f"{int_part}.{dec_part}"
            return int_part
        except (ValueError, TypeError) as e:
            # Expected exception: not a valid number
            logger.debug(f"添加千位分隔符失败 '{text}': {e}")
            return text

    @classmethod
    def _correct_by_domain_dict(cls, text: str, domain_dict: dict[str, str]) -> str:
        """
        基于领域字典纠错

        例如：
        - {"借方": "借方"}（纠正常见OCR错误）
        - {"张三": "张三"}（人名标准化）
        """
        return domain_dict.get(text, text)
