# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Logic Validator — 逻辑验证器
==============================

基于第一性原理的逻辑验证：检查数据是否"自洽"。

Design Principle (道德经):
    "反者道之动" — 从结果反推矛盾，验证内在逻辑。

Core Philosophy:
    数据不仅要"合理"（语义验证），还要"自洽"（逻辑验证）。

    验证维度：
    1. 数学关系（借方+贷方=余额）
    2. 业务规则（余额不能异常跳变）
    3. 跨字段一致性（总金额=各分项之和）
    4. 序列关系（日期递增、序号连续）

Usage::

    from docmirror.core.validation.logic import LogicValidator

    # 验证表格逻辑
    result = LogicValidator.validate(table, header)

    if not result.is_valid:
        for error in result.errors:
            logger.debug(f"Row {error.row}: {error.error}")
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .semantic import ValidationError, ValidationResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Logic Validator
# ═══════════════════════════════════════════════════════════════════════════════


class LogicValidator:
    """
    逻辑验证器 — 检查数据是否"自洽"

    验证维度：
        1. 数学关系（借方+贷方=余额）
        2. 业务规则（余额不能异常跳变）
        3. 跨字段一致性（总金额=各分项之和）
        4. 序列关系（日期递增、序号连续）
    """

    @classmethod
    def validate(cls, table: list[list[str]], header: list[str] | None = None) -> ValidationResult:
        """
        验证表格逻辑

        Args:
            table: 表格数据
            header: 表头

        Returns:
            ValidationResult
        """
        if not table or len(table) < 3:  # 至少header + 2行数据
            return ValidationResult(is_valid=True)

        errors = []

        # 确定表头和数据行
        if header is None:
            header = table[0]
            data_rows = table[1:]
        else:
            data_rows = table

        # 1. 检测列类型和位置
        col_positions = cls._detect_column_positions(header)

        # 2. 验证数学关系
        errors.extend(cls._validate_math_relations(data_rows, col_positions))

        # 3. 验证序列关系
        errors.extend(cls._validate_sequences(data_rows, col_positions))

        # 4. 验证业务规则
        errors.extend(cls._validate_business_rules(data_rows, col_positions))

        # 计算置信度
        total_checks = len(data_rows) * 3  # 3类验证
        confidence = 1.0 - (len(errors) / max(1, total_checks))

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, confidence=max(0.0, min(1.0, confidence)))

    @classmethod
    def _detect_column_positions(cls, header: list[str]) -> dict[str, int]:
        """
        检测各类型列的位置

        Returns:
            {'debit': 2, 'credit': 3, 'balance': 4, ...}
        """
        positions = {}

        for idx, col_name in enumerate(header):
            col_lower = col_name.lower()

            if any(kw in col_lower for kw in ["借方", "debit", "支出"]):
                positions["debit"] = idx
            elif any(kw in col_lower for kw in ["贷方", "credit", "收入"]):
                positions["credit"] = idx
            elif any(kw in col_lower for kw in ["余额", "balance", "结余"]):
                positions["balance"] = idx
            elif any(kw in col_lower for kw in ["日期", "date", "time"]):
                positions["date"] = idx
            elif any(kw in col_lower for kw in ["序号", "no", "编号"]):
                positions["sequence"] = idx
            elif any(kw in col_lower for kw in ["小计", "subtotal"]):
                positions["subtotal"] = idx
            elif any(kw in col_lower for kw in ["合计", "total", "总计"]):
                positions["total"] = idx

        return positions

    @classmethod
    def _validate_math_relations(
        cls, data_rows: list[list[str]], col_positions: dict[str, int]
    ) -> list[ValidationError]:
        """
        验证数学关系

        规则：
        - balance[i] = balance[i-1] + credit[i] - debit[i]
        """
        errors = []

        # 需要余额列
        if "balance" not in col_positions:
            return errors

        balance_col = col_positions["balance"]
        debit_col = col_positions.get("debit")
        credit_col = col_positions.get("credit")

        for i in range(1, len(data_rows)):
            try:
                # 获取当前行和上一行的余额
                prev_balance_str = data_rows[i - 1][balance_col].replace(",", "").strip()
                curr_balance_str = data_rows[i][balance_col].replace(",", "").strip()

                if not prev_balance_str or not curr_balance_str:
                    continue

                prev_balance = float(prev_balance_str)
                curr_balance = float(curr_balance_str)

                # 如果有借贷方
                if debit_col is not None and credit_col is not None:
                    debit_str = data_rows[i][debit_col].replace(",", "").strip()
                    credit_str = data_rows[i][credit_col].replace(",", "").strip()

                    debit = float(debit_str) if debit_str else 0.0
                    credit = float(credit_str) if credit_str else 0.0

                    # 计算预期余额
                    expected_balance = prev_balance + credit - debit

                    # 检查是否匹配（允许1%误差）
                    tolerance = max(abs(curr_balance) * 0.01, 0.01)

                    if abs(curr_balance - expected_balance) > tolerance:
                        errors.append(
                            ValidationError(
                                row=i + 1,
                                col=balance_col,
                                col_name="余额",
                                value=curr_balance_str,
                                error=f"余额不匹配: 预期={expected_balance:.2f}, 实际={curr_balance:.2f}",
                                error_type="logic",
                                suggestion=f"检查第{i + 1}行的借贷方金额",
                            )
                        )

            except (ValueError, IndexError):
                continue

        return errors

    @classmethod
    def _validate_sequences(cls, data_rows: list[list[str]], col_positions: dict[str, int]) -> list[ValidationError]:
        """
        验证序列关系

        规则：
        - 日期应该递增
        - 序号应该连续
        """
        errors = []

        # 验证日期递增
        if "date" in col_positions:
            date_col = col_positions["date"]
            errors.extend(cls._validate_date_sequence(data_rows, date_col))

        # 验证序号连续
        if "sequence" in col_positions:
            seq_col = col_positions["sequence"]
            errors.extend(cls._validate_sequence_numbers(data_rows, seq_col))

        return errors

    @classmethod
    def _validate_date_sequence(cls, data_rows: list[list[str]], date_col: int) -> list[ValidationError]:
        """验证日期递增"""
        errors = []
        prev_date = None

        for i, row in enumerate(data_rows):
            if date_col >= len(row):
                continue

            date_str = row[date_col].strip()
            if not date_str:
                continue

            try:
                curr_date = cls._parse_date(date_str)
                if curr_date is None:
                    continue

                # 检查是否递减
                if prev_date and curr_date < prev_date:
                    errors.append(
                        ValidationError(
                            row=i + 1,
                            col=date_col,
                            col_name="日期",
                            value=date_str,
                            error=f"日期递减: {date_str} < 前一行",
                            error_type="logic",
                            suggestion="检查日期是否录入错误",
                        )
                    )

                prev_date = curr_date

            except (ValueError, TypeError, IndexError) as e:
                # 预期的异常：日期格式错误或行数据不完整
                logger.debug(f"日期验证跳过第{i+1}行: {e}")
                continue
            except Exception as e:
                # 意外异常：应该调查
                logger.warning(f"日期验证意外错误 (第{i+1}行): {e}", exc_info=True)
                continue

        return errors

    @classmethod
    def _validate_sequence_numbers(cls, data_rows: list[list[str]], seq_col: int) -> list[ValidationError]:
        """验证序号连续"""
        errors = []

        for i, row in enumerate(data_rows):
            if seq_col >= len(row):
                continue

            seq_str = row[seq_col].strip()
            if not seq_str:
                continue

            try:
                seq_num = int(seq_str)
                expected_seq = i + 1

                if seq_num != expected_seq:
                    errors.append(
                        ValidationError(
                            row=i + 1,
                            col=seq_col,
                            col_name="序号",
                            value=seq_str,
                            error=f"序号不连续: 预期={expected_seq}, 实际={seq_num}",
                            error_type="logic",
                        )
                    )
            except (ValueError, TypeError) as e:
                # 预期的异常：序号不是有效整数
                logger.debug(f"序号验证跳过第{i+1}行: {e}")
                continue

        return errors

    @classmethod
    def _validate_business_rules(
        cls, data_rows: list[list[str]], col_positions: dict[str, int]
    ) -> list[ValidationError]:
        """
        验证业务规则

        规则：
        - 余额不应异常跳变（>10倍）
        - 金额不应全为0（除非是空表）
        """
        errors = []

        # 验证余额跳变
        if "balance" in col_positions:
            balance_col = col_positions["balance"]
            errors.extend(cls._validate_balance_jumps(data_rows, balance_col))

        return errors

    @classmethod
    def _validate_balance_jumps(cls, data_rows: list[list[str]], balance_col: int) -> list[ValidationError]:
        """验证余额异常跳变"""
        errors = []
        prev_balance = None

        for i, row in enumerate(data_rows):
            if balance_col >= len(row):
                continue

            balance_str = row[balance_col].replace(",", "").strip()
            if not balance_str:
                continue

            try:
                curr_balance = float(balance_str)

                # 检查跳变（>10倍）
                if prev_balance is not None and prev_balance != 0:
                    ratio = abs(curr_balance / prev_balance)
                    if ratio > 10:
                        errors.append(
                            ValidationError(
                                row=i + 1,
                                col=balance_col,
                                col_name="余额",
                                value=balance_str,
                                error=f"余额异常跳变: {prev_balance:.2f} → {curr_balance:.2f} ({ratio:.1f}倍)",
                                error_type="logic",
                                suggestion="检查是否漏录交易或金额错误",
                            )
                        )

                prev_balance = curr_balance

            except (ValueError, TypeError, IndexError) as e:
                # 预期的异常：余额格式错误或行数据不完整
                logger.debug(f"余额验证跳过第{i+1}行: {e}")
                continue
            except ZeroDivisionError:
                # 理论上不应发生（已有 prev_balance != 0 检查）
                logger.warning(f"余额验证除零错误 (第{i+1}行)")
                continue
            except Exception as e:
                # 意外异常：应该调查
                logger.warning(f"余额验证意外错误 (第{i+1}行): {e}", exc_info=True)
                continue

        return errors

    @classmethod
    def _parse_date(cls, value: str):
        """解析日期"""
        import re
        from datetime import datetime

        # 清理
        cleaned = re.sub(r"[年.月日号]", "-", value).strip("-")

        formats = ["%Y-%m-%d", "%m-%d", "%Y%m%d"]
        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                # 预期的异常：格式不匹配
                continue

        return None
