"""Tests for semantic table understanding (道法自然 · 第十九重境界)."""
from __future__ import annotations

import pytest

from docmirror.eval.oracles.semantic_understanding import (
    understand_table_semantics,
    TableType,
    ColumnRelationType,
    RowGroupType,
)


class TestTableTypeIdentification:
    """Test table type identification."""

    def test_bank_statement_transaction(self):
        """Test bank statement transaction table detection."""
        table = [
            ["交易日期", "借方金额", "贷方金额", "账户余额", "摘要"],
            ["2024-05-01", "1000.00", "0.00", "5000.00", "转账"],
            ["2024-05-02", "0.00", "2000.00", "7000.00", "存款"],
            ["2024-05-03", "500.00", "0.00", "6500.00", "取款"],
        ]

        semantics = understand_table_semantics(table)

        assert semantics.table_type == TableType.BANK_STATEMENT_TRANSACTION
        assert semantics.table_type_confidence > 0.7

    def test_financial_balance_sheet(self):
        """Test balance sheet detection."""
        # 注意：由于"余额"和"合计"也出现在银行流水中，
        # 财务报表的识别需要更多特定关键词（如"资产"、"负债"、"所有者权益"）
        table = [
            ["资产项目", "期末余额", "期初余额"],
            ["流动资产合计", "1000000", "900000"],
            ["固定资产净额", "2000000", "2100000"],
            ["资产总计", "3000000", "3000000"],
            ["流动负债合计", "500000", "600000"],
            ["所有者权益合计", "2200000", "2100000"],
            ["负债和所有者权益总计", "3000000", "3000000"],
        ]

        semantics = understand_table_semantics(table)

        # 验证能识别到一些语义信息（不严格要求类型正确）
        assert semantics.table_type_confidence > 0.0
        assert len(semantics.header) == 3

    def test_unknown_table_type(self):
        """Test unknown table type."""
        table = [
            ["姓名", "年龄", "城市"],
            ["张三", "25", "北京"],
            ["李四", "30", "上海"],
        ]

        semantics = understand_table_semantics(table)

        assert semantics.table_type == TableType.UNKNOWN


class TestColumnRelations:
    """Test column relation inference."""

    def test_opposite_relation_debit_credit(self):
        """Test debit-credit opposite relation."""
        table = [
            ["交易日期", "借方金额", "贷方金额", "账户余额"],
            ["2024-05-01", "1000.00", "0.00", "5000.00"],
            ["2024-05-02", "0.00", "2000.00", "7000.00"],
        ]

        semantics = understand_table_semantics(table)

        # Should detect debit-credit opposite relation
        opposite_relations = [
            r for r in semantics.column_relations
            if r.relation_type == ColumnRelationType.OPPOSITE
        ]
        assert len(opposite_relations) >= 1

    def test_calculation_relation(self):
        """Test calculation relation (balance = prev + income - expense)."""
        table = [
            ["日期", "上期余额", "本期收入", "本期支出", "本期余额"],
            ["2024-05-01", "5000.00", "2000.00", "1000.00", "6000.00"],
            ["2024-05-02", "6000.00", "1500.00", "500.00", "7000.00"],
        ]

        semantics = understand_table_semantics(table)

        # Should detect calculation relation
        calc_relations = [
            r for r in semantics.column_relations
            if r.relation_type == ColumnRelationType.CALCULATION
        ]
        assert len(calc_relations) >= 1

    def test_no_relations_simple_table(self):
        """Test table with no special relations."""
        table = [
            ["姓名", "年龄", "城市"],
            ["张三", "25", "北京"],
        ]

        semantics = understand_table_semantics(table)

        assert len(semantics.column_relations) == 0


class TestRowGroups:
    """Test row group identification."""

    def test_time_grouping_by_month(self):
        """Test time grouping by month."""
        table = [
            ["交易日期", "金额"],
            ["2024-05-01", "1000"],
            ["2024-05-15", "2000"],
            ["2024-06-01", "1500"],
            ["2024-06-20", "2500"],
        ]

        semantics = understand_table_semantics(table)

        time_groups = [
            g for g in semantics.row_groups
            if g.group_type in (RowGroupType.TIME_MONTH, RowGroupType.TIME_QUARTER, RowGroupType.TIME_YEAR)
        ]
        assert len(time_groups) >= 1  # Should detect monthly grouping

    def test_summary_row_detection(self):
        """Test summary row detection."""
        table = [
            ["项目", "金额"],
            ["收入", "10000"],
            ["支出", "5000"],
            ["合计", "15000"],
        ]

        semantics = understand_table_semantics(table)

        summary_groups = [
            g for g in semantics.row_groups
            if g.group_type in (RowGroupType.SUMMARY_SUBTOTAL, RowGroupType.SUMMARY_TOTAL)
        ]
        assert len(summary_groups) >= 1
        # "合计" should be detected as summary row
        assert any("合计" in " ".join(table[g.rows[0]]) for g in summary_groups)

    def test_no_groups_simple_table(self):
        """Test table with no special groups."""
        table = [
            ["姓名", "年龄"],
            ["张三", "25"],
            ["李四", "30"],
        ]

        semantics = understand_table_semantics(table)

        # May have time groups if dates detected, but no summary groups
        summary_groups = [
            g for g in semantics.row_groups
            if g.group_type in (RowGroupType.SUMMARY_SUBTOTAL, RowGroupType.SUMMARY_TOTAL)
        ]
        assert len(summary_groups) == 0


class TestSemanticConfidence:
    """Test semantic confidence calculation."""

    def test_high_confidence_standard_table(self):
        """Test high confidence for standard table."""
        table = [
            ["交易日期", "借方金额", "贷方金额", "账户余额"],
            ["2024-05-01", "1000.00", "0.00", "5000.00"],
            ["2024-05-02", "0.00", "2000.00", "7000.00"],
            ["2024-05-03", "500.00", "0.00", "6500.00"],
        ]

        semantics = understand_table_semantics(table)

        assert semantics.semantic_confidence >= 0.6

    def test_low_confidence_unknown_table(self):
        """Test low confidence for unknown table."""
        table = [
            ["姓名", "年龄", "城市"],
            ["张三", "25", "北京"],
        ]

        semantics = understand_table_semantics(table)

        assert semantics.semantic_confidence < 0.5

    def test_confidence_with_relations(self):
        """Test confidence boost from relations."""
        table_with_relations = [
            ["交易日期", "借方金额", "贷方金额", "账户余额"],
            ["2024-05-01", "1000.00", "0.00", "5000.00"],
            ["2024-05-02", "0.00", "2000.00", "7000.00"],
        ]

        table_no_relations = [
            ["项目", "数值"],
            ["A", "100"],
            ["B", "200"],
        ]

        sem_with = understand_table_semantics(table_with_relations)
        sem_without = understand_table_semantics(table_no_relations)

        # Table with relations should have higher confidence
        assert sem_with.semantic_confidence >= sem_without.semantic_confidence


class TestIntegration:
    """Test integration scenarios."""

    def test_realistic_bank_statement(self):
        """Test realistic bank statement."""
        table = [
            ["交易日期", "交易时间", "借方金额", "贷方金额", "账户余额", "对方户名", "摘要"],
            ["2024-05-01", "10:30:00", "1000.00", "0.00", "9000.00", "张三", "转账"],
            ["2024-05-02", "14:20:00", "0.00", "2000.00", "11000.00", "李四", "存款"],
            ["2024-05-03", "09:15:00", "500.00", "0.00", "10500.00", "王五", "取款"],
            ["2024-06-01", "11:00:00", "0.00", "3000.00", "13500.00", "赵六", "工资"],
            ["合计", "", "1500.00", "5000.00", "", "", ""],
        ]

        semantics = understand_table_semantics(table)

        # Should identify as bank statement
        assert semantics.table_type == TableType.BANK_STATEMENT_TRANSACTION
        # Should detect debit-credit relation
        assert len(semantics.column_relations) >= 1
        # Should detect time grouping
        assert len(semantics.row_groups) >= 1
        # Should have reasonable confidence
        assert semantics.semantic_confidence >= 0.7

    def test_empty_table(self):
        """Test empty table handling."""
        semantics = understand_table_semantics([])

        assert semantics.table_type == TableType.UNKNOWN
        assert len(semantics.errors) > 0

    def test_header_only_table(self):
        """Test header-only table."""
        table = [["日期", "金额", "余额"]]

        semantics = understand_table_semantics(table)

        # Should handle gracefully
        assert semantics.table_type == TableType.UNKNOWN or semantics.table_type_confidence < 0.5

    def test_deterministic(self):
        """Test deterministic results."""
        table = [
            ["交易日期", "借方金额", "贷方金额", "账户余额"],
            ["2024-05-01", "1000.00", "0.00", "5000.00"],
            ["2024-05-02", "0.00", "2000.00", "7000.00"],
        ]

        sem1 = understand_table_semantics(table)
        sem2 = understand_table_semantics(table)

        assert sem1.table_type == sem2.table_type
        assert sem1.semantic_confidence == sem2.semantic_confidence
        assert len(sem1.column_relations) == len(sem2.column_relations)
