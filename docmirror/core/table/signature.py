# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Type Signature Library — 列类型推断引擎
========================================

基于第一性原理的表头识别：不依赖词表枚举，而是通过检验"列数据的类型一致性"
来自然推断表头位置。

Design Principle (道德经):
    "道法自然" — 不预设表头应该是什么，而是让数据的内在规律自然显现。
    "知其白，守其黑" — 不仅看到有形的词汇，更理解无形的类型约束。

Core Philosophy:
    表头的本质不是特定词汇，而是为每一列定义语义类型的"命名契约"。
    如果某行下方的数据都能被该列定义的类型完全解释，那么该行就是表头。

Usage::

    from docmirror.core.table.signature import TypeSignatureLibrary

    # 推断一列数据的类型
    signature = TypeSignatureLibrary.infer_signature(["2024-01-15", "2024-01-16", "2024-01-17"])
    # Returns: TypeSignature(type_name="date", confidence=1.0, ...)

    # 推断完整表格的列签名画像
    profile = TypeSignatureLibrary.infer_table_signature(table_rows)
    # Returns: ColumnSignatureProfile(signatures=[...], overall_consistency=0.95)
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
class TypeSignature:
    """
    描述一列数据的类型特征

    Attributes:
        type_name: 类型名称 (date, amount, text, account等)
        confidence: 置信度 0-1，该列符合此类型的程度
        pattern_examples: 典型值样例（最多3个）
        nullable_count: 空值数量（某些类型允许空值）
        total_values: 总数据行数
    """

    type_name: str
    confidence: float
    pattern_examples: list[str] = field(default_factory=list)
    nullable_count: int = 0
    total_values: int = 0

    def to_dict(self) -> dict:
        """转换为字典格式（用于序列化）"""
        return {
            "type_name": self.type_name,
            "confidence": round(self.confidence, 4),
            "pattern_examples": self.pattern_examples,
            "nullable_count": self.nullable_count,
            "total_values": self.total_values,
        }


@dataclass
class ColumnSignatureProfile:
    """
    一个完整表格的列签名画像

    Attributes:
        signatures: 每列的类型签名列表
        overall_consistency: 整体一致性得分 0-1
        is_likely_header: 是否可能是表头行（基于一致性阈值）
        header_row_index: 推断的表头行索引（相对于数据起始位置）
    """

    signatures: list[TypeSignature]
    overall_consistency: float = 0.0
    is_likely_header: bool = False
    header_row_index: int = 0

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "signatures": [sig.to_dict() for sig in self.signatures],
            "overall_consistency": round(self.overall_consistency, 4),
            "is_likely_header": self.is_likely_header,
            "header_row_index": self.header_row_index,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Type Signature Library
# ═══════════════════════════════════════════════════════════════════════════════


class TypeSignatureLibrary:
    """
    类型签名库 — 定义各种数据类型的检测规则

    核心思想：通过检测数据值是否符合某种类型的模式，推断该列的语义类型。
    这不是简单的正则匹配，而是综合模式匹配、语义解析和统计推断的智能检测。

    支持的类型：
        - date: 日期（多种格式）
        - amount: 金额（含货币符号、千分位、负数）
        - percentage: 百分比
        - account: 银行账号（10-19位数字）
        - phone: 电话号码
        - id_number: 身份证号
        - text: 文本（默认类型）
        - number: 普通数字
    """

    # ── 日期模式集合 ──
    # Rationale: 覆盖中英文常见日期格式，支持多种分隔符
    DATE_PATTERNS = [
        # YYYY-MM-DD, YYYY/MM/DD, YYYY年MM月DD日
        (r"^\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?$", "%Y-%m-%d"),
        # MM-DD, MM/DD
        (r"^(0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])$", "%m-%d"),
        # YYYY.MM.DD
        (r"^\d{4}\.\d{2}\.\d{2}$", "%Y.%m.%d"),
        # DD-MMM-YYYY (英文格式)
        (r"^\d{1,2}-[A-Z]{3}-\d{4}$", "%d-%b-%Y"),
    ]

    # ── 金额模式 ──
    # Rationale: 支持货币符号、千分位逗号、小数点、负号、百分比
    AMOUNT_PATTERN = re.compile(r"^[-￥$€£¥]?\s*[\d,]+\.?\d*%?$")

    # ── 账号模式 ──
    # Rationale: 银行账号通常10-19位数字，可能有空格
    ACCOUNT_PATTERN = re.compile(r"^\d[\d\s]{9,18}$")

    # ── 手机号模式 ──
    PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")

    # ── 身份证号模式 ──
    ID_NUMBER_PATTERN = re.compile(r"^\d{17}[\dXx]$")

    # ── 百分比模式 ──
    PERCENTAGE_PATTERN = re.compile(r"^\d+\.?\d*%$")

    # ── 普通数字模式 ──
    NUMBER_PATTERN = re.compile(r"^-?\d+\.?\d*$")

    @classmethod
    def test_date(cls, value: str) -> datetime | None:
        """
        测试值是否为日期

        Args:
            value: 待测试的字符串

        Returns:
            解析后的datetime对象，或None
        """
        value = value.strip()
        if not value:
            return None

        for pattern, fmt in cls.DATE_PATTERNS:
            if re.match(pattern, value):
                try:
                    # 标准化分隔符
                    cleaned = re.sub(r"[年月日号]", "-", value)
                    cleaned = re.sub(r"[/.]", "-", cleaned)  # 也替换点号
                    # 只取前10个字符 (YYYY-MM-DD)
                    cleaned = cleaned[:10]
                    # 尝试解析
                    return datetime.strptime(cleaned, "%Y-%m-%d")
                except ValueError:
                    # 尝试其他格式
                    try:
                        return datetime.strptime(cleaned, "%m-%d")
                    except ValueError:
                        pass
        return None

    @classmethod
    def test_amount(cls, value: str) -> float | None:
        """
        测试值是否为金额

        Args:
            value: 待测试的字符串

        Returns:
            解析后的浮点数值，或None
        """
        value = value.strip()
        if not value:
            return None

        # 移除货币符号和空格
        cleaned = re.sub(r"[￥$€£¥\s]", "", value)
        # 移除千分位逗号
        cleaned = cleaned.replace(",", "")

        # 处理百分比
        if cleaned.endswith("%"):
            cleaned = cleaned[:-1]

        try:
            return float(cleaned)
        except ValueError:
            return None

    @classmethod
    def test_percentage(cls, value: str) -> float | None:
        """测试值是否为百分比"""
        value = value.strip()
        if cls.PERCENTAGE_PATTERN.match(value):
            try:
                return float(value.rstrip("%"))
            except ValueError:
                pass
        return None

    @classmethod
    def test_account(cls, value: str) -> str | None:
        """测试值是否为银行账号"""
        value = value.strip()
        if cls.ACCOUNT_PATTERN.match(value):
            return value.replace(" ", "")
        return None

    @classmethod
    def test_phone(cls, value: str) -> str | None:
        """测试值是否为手机号"""
        value = value.strip()
        if cls.PHONE_PATTERN.match(value):
            return value
        return None

    @classmethod
    def test_id_number(cls, value: str) -> str | None:
        """测试值是否为身份证号"""
        value = value.strip()
        if cls.ID_NUMBER_PATTERN.match(value):
            return value.upper()
        return None

    @classmethod
    def test_number(cls, value: str) -> float | None:
        """测试值是否为普通数字"""
        value = value.strip()
        if cls.NUMBER_PATTERN.match(value):
            try:
                return float(value)
            except ValueError:
                pass
        return None

    @classmethod
    def infer_signature(cls, values: list[str]) -> TypeSignature:
        """
        推断一列值的类型签名

        核心算法：
            1. 对每个值测试所有类型
            2. 统计每种类型的匹配数量
            3. 选择匹配度最高的类型作为签名
            4. 计算置信度 = 匹配数 / 总行数

        Args:
            values: 列值列表

        Returns:
            TypeSignature 对象
        """
        if not values:
            return TypeSignature("unknown", 0.0, [], 0, 0)

        # 统计各种类型的匹配度
        scores: dict[str, int] = {
            "date": 0,
            "amount": 0,
            "percentage": 0,
            "account": 0,
            "phone": 0,
            "id_number": 0,
            "number": 0,
            "text": 0,
            "empty": 0,
        }

        nullable_count = 0
        examples: list[str] = []

        for v in values:
            v_stripped = v.strip()
            if not v_stripped:
                scores["empty"] += 1
                nullable_count += 1
                continue

            # 按顺序测试（从特异性高到特异性低）
            if cls.test_date(v_stripped) is not None:
                scores["date"] += 1
                if len(examples) < 3:
                    examples.append(v_stripped)
                continue

            if cls.test_amount(v_stripped) is not None:
                scores["amount"] += 1
                if len(examples) < 3:
                    examples.append(v_stripped)
                continue

            if cls.test_percentage(v_stripped) is not None:
                scores["percentage"] += 1
                if len(examples) < 3:
                    examples.append(v_stripped)
                continue

            if cls.test_account(v_stripped) is not None:
                scores["account"] += 1
                if len(examples) < 3:
                    examples.append(v_stripped)
                continue

            if cls.test_phone(v_stripped) is not None:
                scores["phone"] += 1
                if len(examples) < 3:
                    examples.append(v_stripped)
                continue

            if cls.test_id_number(v_stripped) is not None:
                scores["id_number"] += 1
                if len(examples) < 3:
                    examples.append(v_stripped)
                continue

            if cls.test_number(v_stripped) is not None:
                scores["number"] += 1
                if len(examples) < 3:
                    examples.append(v_stripped)
                continue

            # 默认为文本
            scores["text"] += 1
            if len(examples) < 3:
                examples.append(v_stripped)

        # 选择最佳匹配类型
        total = len(values)
        best_type = max(scores, key=lambda t: scores[t])
        confidence = scores[best_type] / total

        return TypeSignature(
            type_name=best_type,
            confidence=confidence,
            pattern_examples=examples,
            nullable_count=nullable_count,
            total_values=total,
        )

    @classmethod
    def infer_table_signature(
        cls,
        rows: list[list[str]],
        min_data_rows: int = 3,
        consistency_threshold: float = 0.7,
    ) -> ColumnSignatureProfile | None:
        """
        推断完整表格的列签名画像

        Args:
            rows: 表格行列表（每行是单元格字符串列表）
            min_data_rows: 最小数据行数（用于推断）
            consistency_threshold: 一致性阈值（超过此值认为是有效表头）

        Returns:
            ColumnSignatureProfile 或 None（如果行数不足）
        """
        if len(rows) < min_data_rows:
            return None  # 行数太少，无法推断

        # 推断每列的类型签名
        num_cols = max(len(row) for row in rows)
        signatures: list[TypeSignature] = []

        for col_idx in range(num_cols):
            # 提取该列的值
            col_values = []
            for row in rows:
                if col_idx < len(row):
                    col_values.append(row[col_idx])
                else:
                    col_values.append("")

            # 推断类型签名
            signature = cls.infer_signature(col_values)
            signatures.append(signature)

        # 计算整体一致性得分
        # 公式：平均置信度 × 非空列比例 × 类型多样性奖励
        avg_confidence = sum(sig.confidence for sig in signatures) / len(signatures)
        non_empty_ratio = sum(1 for sig in signatures if sig.confidence > 0.3 and sig.type_name != "empty") / len(
            signatures
        )

        # 类型多样性奖励：不同的列类型越多，越可能是表头
        unique_types = len(
            set(sig.type_name for sig in signatures if sig.confidence > 0.3 and sig.type_name != "empty")
        )
        diversity_bonus = min(1.0, unique_types / 3.0)  # 最多奖励3种不同列类型

        overall_consistency = avg_confidence * non_empty_ratio * (0.7 + 0.3 * diversity_bonus)

        # 如果所有列都是 empty，不应该被认为是表头
        is_likely_header = (
            overall_consistency >= consistency_threshold and non_empty_ratio > 0.3
        )  # 至少30%的列有实际内容

        return ColumnSignatureProfile(
            signatures=signatures,
            overall_consistency=overall_consistency,
            is_likely_header=is_likely_header,
            header_row_index=0,
        )
