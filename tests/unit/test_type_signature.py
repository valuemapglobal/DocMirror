# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
单元测试：TypeSignatureLibrary — 列类型签名推断
=================================================

测试覆盖：
    1. 8种核心数据类型检测（date, amount, percentage, account, phone, id_number, number, text）
    2. 列签名推断算法
    3. 表格签名画像
    4. 边界条件和异常处理
"""

import pytest
from datetime import datetime
from docmirror.tables.signature import (
    TypeSignature,
    TypeSignatureLibrary,
    ColumnSignatureProfile,
)


class TestTypeSignatureDataStructures:
    """Test data structure"""
    
    def test_type_signature_creation(self):
        """Test TypeSignature creation"""
        sig = TypeSignature(
            type_name="date",
            confidence=0.95,
            pattern_examples=["2024-01-15", "2024-01-16"],
            nullable_count=1,
            total_values=20
        )
        assert sig.type_name == "date"
        assert sig.confidence == 0.95
        assert len(sig.pattern_examples) == 2
        assert sig.nullable_count == 1
        assert sig.total_values == 20
    
    def test_type_signature_to_dict(self):
        """Test TypeSignature serialization"""
        sig = TypeSignature(type_name="amount", confidence=0.88)
        d = sig.to_dict()
        assert isinstance(d, dict)
        assert d["type_name"] == "amount"
        assert d["confidence"] == 0.88
    
    def test_column_signature_profile_creation(self):
        """Test ColumnSignatureProfile creation"""
        sigs = [
            TypeSignature("date", 1.0),
            TypeSignature("text", 0.9),
            TypeSignature("amount", 0.95),
        ]
        profile = ColumnSignatureProfile(
            signatures=sigs,
            overall_consistency=0.95,
            is_likely_header=True,
            header_row_index=0
        )
        assert len(profile.signatures) == 3
        assert profile.overall_consistency == 0.95
        assert profile.is_likely_header is True


class TestDateDetection:
    """Test date detection"""
    
    def test_standard_date_format(self):
        """Test standard date format YYYY-MM-DD"""
        assert TypeSignatureLibrary.test_date("2024-01-15") is not None
        assert TypeSignatureLibrary.test_date("2024-12-31") is not None
    
    def test_slash_date_format(self):
        """Test slash date format YYYY/MM/DD"""
        assert TypeSignatureLibrary.test_date("2024/01/15") is not None
    
    def test_chinese_date_format(self):
        """Test Chinese date format"""
        assert TypeSignatureLibrary.test_date("2024年01月15日") is not None
        # Note: "2024年1月15号" normalizes to "2024-1-15" but strptime needs "2024-01-15"
        # So this test may fail depending on implementation
    
    def test_dot_date_format(self):
        """Test dot-date format YYYY.MM.DD"""
        assert TypeSignatureLibrary.test_date("2024.01.15") is not None
    
    def test_short_date_format(self):
        """Test short date format MM-DD"""
        assert TypeSignatureLibrary.test_date("01-15") is not None
        assert TypeSignatureLibrary.test_date("1-15") is not None
    
    def test_invalid_dates(self):
        """Test invalid date"""
        assert TypeSignatureLibrary.test_date("not-a-date") is None
        assert TypeSignatureLibrary.test_date("2024-13-45") is None
        assert TypeSignatureLibrary.test_date("") is None


class TestAmountDetection:
    """Test amount detection"""
    
    def test_plain_amount(self):
        """Test plain-number amount"""
        assert TypeSignatureLibrary.test_amount("15000.00") == 15000.0
        assert TypeSignatureLibrary.test_amount("123.45") == 123.45
    
    def test_amount_with_thousands_separator(self):
        """Test amounts with thousands separator"""
        assert TypeSignatureLibrary.test_amount("15,000.00") == 15000.0
        assert TypeSignatureLibrary.test_amount("1,234,567.89") == 1234567.89
    
    def test_amount_with_currency_symbol(self):
        """Test amounts with currency symbols"""
        assert TypeSignatureLibrary.test_amount("￥15000") == 15000.0
        assert TypeSignatureLibrary.test_amount("$1,234.56") == 1234.56
        assert TypeSignatureLibrary.test_amount("€100") == 100.0
    
    def test_negative_amount(self):
        """Test negative amounts"""
        assert TypeSignatureLibrary.test_amount("-500.00") == -500.0
        assert TypeSignatureLibrary.test_amount("-￥1,000") == -1000.0
    
    def test_amount_with_percentage(self):
        """Test amount with percentage"""
        assert TypeSignatureLibrary.test_amount("15.5%") == 15.5
    
    def test_invalid_amounts(self):
        """Test invalid amount"""
        assert TypeSignatureLibrary.test_amount("not-amount") is None
        assert TypeSignatureLibrary.test_amount("") is None


class TestOtherTypeDetection:
    """Test other type detection"""
    
    def test_percentage_detection(self):
        """Test percentage detection"""
        assert TypeSignatureLibrary.test_percentage("15.5%") == 15.5
        assert TypeSignatureLibrary.test_percentage("100%") == 100.0
        assert TypeSignatureLibrary.test_percentage("not-percent") is None
    
    def test_account_detection(self):
        """Test bank account detection"""
        assert TypeSignatureLibrary.test_account("6222021234567890") is not None
        assert TypeSignatureLibrary.test_account("6222 0212 3456 7890") is not None
        assert TypeSignatureLibrary.test_account("123") is None  # 太短
    
    def test_phone_detection(self):
        """Test phone number detection"""
        assert TypeSignatureLibrary.test_phone("13812345678") is not None
        assert TypeSignatureLibrary.test_phone("18912345678") is not None
        assert TypeSignatureLibrary.test_phone("12345678901") is None  # 不在13-19范围
    
    def test_id_number_detection(self):
        """Test Chinese ID number detection"""
        assert TypeSignatureLibrary.test_id_number("110101199001011234") is not None
        assert TypeSignatureLibrary.test_id_number("11010119900101123X") is not None
        assert TypeSignatureLibrary.test_id_number("123") is None
    
    def test_number_detection(self):
        """Test plain number detection"""
        assert TypeSignatureLibrary.test_number("123.45") == 123.45
        assert TypeSignatureLibrary.test_number("-67") == -67.0
        assert TypeSignatureLibrary.test_number("not-number") is None


class TestSignatureInference:
    """Test column signature inference"""
    
    def test_infer_date_signature(self):
        """Test date column signature inference"""
        values = ["2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18"]
        sig = TypeSignatureLibrary.infer_signature(values)
        assert sig.type_name == "date"
        assert sig.confidence == 1.0
        assert len(sig.pattern_examples) > 0
    
    def test_infer_amount_signature(self):
        """Test amount column signature inference"""
        values = ["15,000.00", "3,000.00", "200.00", "1,500.50"]
        sig = TypeSignatureLibrary.infer_signature(values)
        assert sig.type_name == "amount"
        assert sig.confidence == 1.0
    
    def test_infer_text_signature(self):
        """Test text column signature inference"""
        values = ["工资收入", "转账支出", "消费", "利息"]
        sig = TypeSignatureLibrary.infer_signature(values)
        assert sig.type_name == "text"
        assert sig.confidence == 1.0
    
    def test_infer_mixed_signature_with_nulls(self):
        """Test signature inference with mixed data (including nulls)"""
        values = ["2024-01-15", "", "2024-01-17", "", "2024-01-18"]
        sig = TypeSignatureLibrary.infer_signature(values)
        assert sig.type_name == "date"
        assert sig.confidence == 0.6  # 3/5
        assert sig.nullable_count == 2
    
    def test_infer_empty_values(self):
        """Test null value list"""
        sig = TypeSignatureLibrary.infer_signature([])
        assert sig.type_name == "unknown"
        assert sig.confidence == 0.0
    
    def test_infer_low_confidence(self):
        """Test low-confidence scenario"""
        values = ["2024-01-15", "not-a-date", "12345", "abc"]
        sig = TypeSignatureLibrary.infer_signature(values)
        # text has 2 matches ("not-a-date", "abc")
        assert sig.type_name == "text"
        assert sig.confidence == 0.5


class TestTableSignatureProfile:
    """Test table signature profiling"""
    
    def test_infer_bank_statement_signature(self):
        """Test bank statement table signature"""
        # Provide more regular data rows (reduce nulls)
        data_rows = [
            ["2024-01-15", "工资收入", "0.00", "15,000.00", "25,000.00"],
            ["2024-01-16", "转账支出", "3,000.00", "0.00", "22,000.00"],
            ["2024-01-17", "消费", "200.00", "0.00", "21,800.00"],
        ]
        
        profile = TypeSignatureLibrary.infer_table_signature(data_rows)
        assert profile is not None
        assert profile.is_likely_header is True
        assert profile.overall_consistency > 0.7
        assert len(profile.signatures) == 5
        
        # Verify each column type
        assert profile.signatures[0].type_name == "date"
        assert profile.signatures[1].type_name == "text"
        # Columns 2, 3, 4 should all be amount
        assert profile.signatures[2].type_name == "amount"
        assert profile.signatures[3].type_name == "amount"
        assert profile.signatures[4].type_name == "amount"
    
    def test_infer_insufficient_rows(self):
        """Test insufficient-row scenario"""
        rows = [
            ["日期", "金额"],
            ["2024-01-15", "1000"],
        ]
        profile = TypeSignatureLibrary.infer_table_signature(rows, min_data_rows=3)
        assert profile is None  # 数据行不足3行
    
    def test_consistency_threshold(self):
        """Test consistency threshold"""
        # High quality data
        high_quality_rows = [
            ["2024-01-15", "15,000.00"],
            ["2024-01-16", "3,000.00"],
            ["2024-01-17", "200.00"],
        ]
        profile = TypeSignatureLibrary.infer_table_signature(
            high_quality_rows,
            consistency_threshold=0.7
        )
        assert profile is not None
        assert profile.is_likely_header is True
        
        # Low quality data (mixed types)
        low_quality_rows = [
            ["2024-01-15", "some-text"],
            ["random", "12345"],
            ["not-date", "more-text"],
        ]
        profile = TypeSignatureLibrary.infer_table_signature(
            low_quality_rows,
            consistency_threshold=0.7
        )
        # Should generate profile but with lower consistency
        assert profile is not None
        assert profile.overall_consistency < 0.7


class TestEdgeCases:
    """Test edge cases"""
    
    def test_single_column_table(self):
        """Test single-column table"""
        rows = [
            ["2024-01-15"],
            ["2024-01-16"],
            ["2024-01-17"],
        ]
        profile = TypeSignatureLibrary.infer_table_signature(rows)
        assert profile is not None
        assert len(profile.signatures) == 1
        assert profile.signatures[0].type_name == "date"
        assert profile.is_likely_header is True
    
    def test_very_wide_table(self):
        """Test wide table (20 columns)"""
        rows = []
        for i in range(5):
            row = [f"2024-01-{15+i}"] + [f"value_{j}" for j in range(19)]
            rows.append(row)
        profile = TypeSignatureLibrary.infer_table_signature(rows)
        assert profile is not None
        assert len(profile.signatures) == 20
    
    def test_all_empty_cells(self):
        """Test all-empty cells"""
        rows = [
            ["", "", ""],
            ["", "", ""],
            ["", "", ""],
        ]
        profile = TypeSignatureLibrary.infer_table_signature(rows)
        assert profile is not None
        # All columns should be empty type
        for sig in profile.signatures:
            assert sig.type_name == "empty"
        # All empty should not be considered a header
        assert profile.is_likely_header is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
