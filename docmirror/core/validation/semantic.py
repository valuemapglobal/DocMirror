# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Semantic Validator — 语义验证器
================================

基于第一性原理的语义验证：检查数据是否"合理"。

Design Principle (道德经):
    "反者道之动" — 从结果反推问题，反向验证。
    "知人者智，自知者明" — 系统能自我检查、自我认知。

Core Philosophy:
    提取完成 ≠ 任务结束
    验证通过 = 任务结束

    验证维度：
    1. 日期合理性（2024-13-45 不合理）
    2. 数字范围（年龄200岁不合理）
    3. 格式匹配（手机号11位）
    4. 类型一致性（应该是数字的字段出现文字）

Usage::

    from docmirror.core.validation.semantic import SemanticValidator

    # 验证表格语义
    result = SemanticValidator.validate(table, header)

    if not result.is_valid:
        logger.warning(f"发现 {len(result.errors)} 个语义错误")
        for error in result.errors:
            logger.debug(f"Row {error['row']}, Col {error['col']}: {error['error']}")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ValidationError:
    """验证错误"""

    row: int
    col: int
    col_name: str
    value: str
    error: str
    error_type: str  # 'semantic', 'logic', 'structure'
    suggestion: str | None = None


@dataclass
class ValidationResult:
    """验证结果"""

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    confidence: float = 1.0
    warnings: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def summary(self) -> str:
        return (
            f"ValidationResult("
            f"valid={self.is_valid}, "
            f"errors={self.error_count}, "
            f"warnings={self.warning_count}, "
            f"confidence={self.confidence:.2f}"
            f")"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Semantic Validator
# ═══════════════════════════════════════════════════════════════════════════════


class SemanticValidator:
    """
    语义验证器 — 检查数据是否"合理"

    验证维度：
        1. 日期合理性（2024-13-45 不合理）
        2. 数字范围（年龄200岁不合理）
        3. 格式匹配（手机号11位）
        4. 类型一致性（应该是数字的字段出现文字）
    """

    # 列类型关键词映射
    COLUMN_TYPE_KEYWORDS = {
        "date": ["日期", "date", "time", "时间", "年月"],
        "amount": ["金额", "amount", "money", "元", "元整"],
        "balance": ["余额", "balance", "结余"],
        "phone": ["电话", "phone", "手机", "tel", "联系方式"],
        "id_number": ["身份证", "id", "证件号", "编号"],
        "age": ["年龄", "age"],
        "percentage": ["比例", "percentage", "%", "比率"],
        "account": ["账号", "account", "卡号", "账户"],
    }

    @classmethod
    def validate(cls, table: list[list[str]], header: list[str] | None = None) -> ValidationResult:
        """
        验证表格语义

        Args:
            table: 表格数据 [[cell, cell, ...], ...]
            header: 表头（可选，如未提供则从table[0]推断）

        Returns:
            ValidationResult
        """
        if not table:
            return ValidationResult(is_valid=True)

        errors = []
        warnings = []

        # 确定表头
        if header is None:
            header = table[0] if table else []
            data_rows = table[1:]
        else:
            data_rows = table

        # 推断每列的类型
        col_types = cls._infer_column_types(table, header)

        # 验证每个单元格
        for row_idx, row in enumerate(data_rows):
            actual_row_idx = row_idx + (0 if header is table[0] else 1)

            for col_idx, cell in enumerate(row):
                if col_idx >= len(header):
                    continue

                col_name = header[col_idx] if col_idx < len(header) else f"col_{col_idx}"
                col_type = col_types.get(col_idx, "text")

                # 验证单元格
                error = cls._validate_cell(cell, col_type, col_name)
                if error:
                    errors.append(
                        ValidationError(
                            row=actual_row_idx,
                            col=col_idx,
                            col_name=col_name,
                            value=cell,
                            error=error,
                            error_type="semantic",
                        )
                    )

        # 计算置信度
        total_cells = len(data_rows) * len(header) if header else 0
        confidence = 1.0 - (len(errors) / max(1, total_cells))

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, confidence=max(0.0, min(1.0, confidence)), warnings=warnings
        )

    @classmethod
    def _infer_column_types(cls, table: list[list[str]], header: list[str]) -> dict[int, str]:
        """
        推断每列的数据类型

        Args:
            table: 表格数据
            header: 表头

        Returns:
            {col_idx: type}
        """
        col_types = {}

        for col_idx, col_name in enumerate(header):
            col_type = cls._detect_type_from_header(col_name)

            # 如果从表头无法判断，从数据推断
            if col_type == "text":
                col_data = [row[col_idx] for row in table[1:] if col_idx < len(row) and row[col_idx].strip()]
                col_type = cls._detect_type_from_data(col_data)

            col_types[col_idx] = col_type

        return col_types

    @classmethod
    def _detect_type_from_header(cls, header: str) -> str:
        """从表头推断类型"""
        header_lower = header.lower()

        for col_type, keywords in cls.COLUMN_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in header_lower:
                    return col_type

        return "text"

    @classmethod
    def _detect_type_from_data(cls, data: list[str]) -> str:
        """从数据推断类型"""
        if not data:
            return "text"

        # 统计各类特征
        date_count = sum(1 for v in data if cls._looks_like_date(v))
        number_count = sum(1 for v in data if cls._looks_like_number(v))
        phone_count = sum(1 for v in data if cls._looks_like_phone(v))

        total = len(data)

        if date_count > total * 0.6:
            return "date"
        elif phone_count > total * 0.6:
            return "phone"
        elif number_count > total * 0.6:
            return "amount"

        return "text"

    @classmethod
    def _validate_cell(cls, value: str, col_type: str, col_name: str) -> str | None:
        """
        验证单个单元格

        Returns:
            错误消息，无错误返回None
        """
        if not value or not value.strip():
            return None  # 空值不验证

        value = value.strip()

        if col_type == "date":
            return cls._validate_date(value, col_name)
        elif col_type in ("amount", "balance"):
            return cls._validate_number(value, col_name)
        elif col_type == "phone":
            return cls._validate_phone(value, col_name)
        elif col_type == "age":
            return cls._validate_age(value, col_name)
        elif col_type == "percentage":
            return cls._validate_percentage(value, col_name)
        elif col_type == "id_number":
            return cls._validate_id_number(value, col_name)

        return None

    @classmethod
    def _validate_date(cls, value: str, col_name: str) -> str | None:
        """验证日期合理性"""
        # 尝试匹配各种日期格式
        patterns = [
            (r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?", "date_format"),
            (r"\d{4}\.\d{2}\.\d{2}", "date_format"),
            (r"\d{8}", "date_format_compact"),
        ]

        is_date_like = False
        for pattern, fmt_type in patterns:
            if re.match(pattern, value):
                is_date_like = True
                break

        if not is_date_like:
            return None  # 不像日期，不验证

        # 尝试解析
        try:
            dt = cls._parse_date(value)
            if dt is None:
                return f"日期格式无效: {value}"

            # 检查年份范围（1900-2100）
            if dt.year < 1900 or dt.year > 2100:
                return f"年份超出范围: {dt.year} (应在1900-2100)"

            # 检查是否在未来（除非是计划日期）
            if dt > datetime.now():
                return f"日期在未来: {value}"

            return None

        except Exception:
            return f"日期解析失败: {value}"

    @classmethod
    def _parse_date(cls, value: str) -> datetime | None:
        """解析日期"""
        # 清理分隔符
        cleaned = re.sub(r"[年.月日号]", "-", value)
        cleaned = cleaned.strip("-")

        # 尝试多种格式
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%d",
            "%m-%d",
            "%Y%m%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                # 预期的异常：格式不匹配
                continue

        return None

    @classmethod
    def _validate_number(cls, value: str, col_name: str) -> str | None:
        """验证数字合理性"""
        try:
            # 清理千位分隔符
            cleaned = value.replace(",", "").replace("，", "")
            num = float(cleaned)

            # 检查NaN和Inf
            if num != num:  # NaN
                return f"无效数字: {value}"

            # 检查范围（通用范围）
            if abs(num) > 1e15:
                return f"数值过大: {num}"

            # 业务特定规则
            col_name_lower = col_name.lower()

            if "余额" in col_name_lower or "balance" in col_name_lower:
                # 余额可以为负（透支）
                if abs(num) > 1e12:
                    return f"余额异常: {num}"

            if "金额" in col_name_lower or "amount" in col_name_lower:
                # 金额通常为正
                if num < -1e9:
                    return f"金额异常负数: {num}"

            return None

        except ValueError:
            return f"非数字格式: {value}"

    @classmethod
    def _validate_phone(cls, value: str, col_name: str) -> str | None:
        """验证手机号"""
        # 清理
        cleaned = re.sub(r"[-\s()]", "", value)

        # 中国手机号：11位，1开头
        if re.match(r"^1[3-9]\d{9}$", cleaned):
            return None

        # 座机号：区号+号码
        if re.match(r"^0\d{2,3}-?\d{7,8}$", cleaned):
            return None

        # 如果不像电话号码
        if len(cleaned) >= 7:
            return f"电话号码格式可能错误: {value}"

        return None

    @classmethod
    def _validate_age(cls, value: str, col_name: str) -> str | None:
        """验证年龄"""
        try:
            age = int(float(value.replace(",", "")))
            if age < 0 or age > 150:
                return f"年龄不合理: {age} (应在0-150)"
            return None
        except (ValueError, TypeError) as e:
            logger.debug(f"年龄验证失败 '{value}': {e}")
            return f"年龄格式错误: {value}"

    @classmethod
    def _validate_percentage(cls, value: str, col_name: str) -> str | None:
        """验证百分比"""
        try:
            cleaned = value.replace("%", "").strip()
            pct = float(cleaned)
            if pct < 0 or pct > 100:
                return f"百分比超出范围: {pct}% (应在0-100)"
            return None
        except (ValueError, TypeError) as e:
            logger.debug(f"百分比验证失败 '{value}': {e}")
            return f"百分比格式错误: {value}"

    @classmethod
    def _validate_id_number(cls, value: str, col_name: str) -> str | None:
        """验证身份证号"""
        # 中国身份证：18位或15位
        cleaned = value.strip()

        if len(cleaned) == 18:
            if not re.match(r"^\d{17}[\dXx]$", cleaned):
                return f"身份证号格式错误: {value}"
        elif len(cleaned) == 15:
            if not re.match(r"^\d{15}$", cleaned):
                return f"身份证号格式错误: {value}"
        elif len(cleaned) > 0:
            return f"身份证号长度错误: {len(cleaned)}位 (应为15或18位)"

        return None

    @classmethod
    def _looks_like_date(cls, value: str) -> bool:
        """判断是否像日期"""
        return bool(re.match(r"\d{4}[-/年.]\d{1,2}", value))

    @classmethod
    def _looks_like_number(cls, value: str) -> bool:
        """判断是否像数字"""
        try:
            float(value.replace(",", "").replace("，", ""))
            return True
        except (ValueError, TypeError):
            return False

    @classmethod
    def _looks_like_phone(cls, value: str) -> bool:
        """判断是否像电话"""
        cleaned = re.sub(r"[-\s()]", "", value)
        return bool(re.match(r"^1[3-9]\d{9}$", cleaned))
