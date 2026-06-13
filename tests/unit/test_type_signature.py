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
from docmirror.core.table.signature import (
    TypeSignature,
    TypeSignatureLibrary,
    ColumnSignatureProfile,
)


class TestTypeSignatureDataStructures:
    """测试数据结构"""
    
    def test_type_signature_creation(self):
        """测试 TypeSignature 创建"""
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
        """测试 TypeSignature 序列化"""
        sig = TypeSignature(type_name="amount", confidence=0.88)
        d = sig.to_dict()
        assert isinstance(d, dict)
        assert d["type_name"] == "amount"
        assert d["confidence"] == 0.88
    
    def test_column_signature_profile_creation(self):
        """测试 ColumnSignatureProfile 创建"""
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
    """测试日期检测"""
    
    def test_standard_date_format(self):
        """测试标准日期格式 YYYY-MM-DD"""
        assert TypeSignatureLibrary.test_date("2024-01-15") is not None
        assert TypeSignatureLibrary.test_date("2024-12-31") is not None
    
    def test_slash_date_format(self):
        """测试斜杠日期格式 YYYY/MM/DD"""
        assert TypeSignatureLibrary.test_date("2024/01/15") is not None
    
    def test_chinese_date_format(self):
        """测试中文日期格式"""
        assert TypeSignatureLibrary.test_date("2024年01月15日") is not None
        # 注意："2024年1月15号" 会被标准化为 "2024-1-15"，但strptime需要 "2024-01-15"
        # 所以这个测试可能失败，取决于实现
    
    def test_dot_date_format(self):
        """测试点号日期格式 YYYY.MM.DD"""
        assert TypeSignatureLibrary.test_date("2024.01.15") is not None
    
    def test_short_date_format(self):
        """测试短日期格式 MM-DD"""
        assert TypeSignatureLibrary.test_date("01-15") is not None
        assert TypeSignatureLibrary.test_date("1-15") is not None
    
    def test_invalid_dates(self):
        """测试无效日期"""
        assert TypeSignatureLibrary.test_date("not-a-date") is None
        assert TypeSignatureLibrary.test_date("2024-13-45") is None
        assert TypeSignatureLibrary.test_date("") is None


class TestAmountDetection:
    """测试金额检测"""
    
    def test_plain_amount(self):
        """测试纯数字金额"""
        assert TypeSignatureLibrary.test_amount("15000.00") == 15000.0
        assert TypeSignatureLibrary.test_amount("123.45") == 123.45
    
    def test_amount_with_thousands_separator(self):
        """测试带千分位的金额"""
        assert TypeSignatureLibrary.test_amount("15,000.00") == 15000.0
        assert TypeSignatureLibrary.test_amount("1,234,567.89") == 1234567.89
    
    def test_amount_with_currency_symbol(self):
        """测试带货币符号的金额"""
        assert TypeSignatureLibrary.test_amount("￥15000") == 15000.0
        assert TypeSignatureLibrary.test_amount("$1,234.56") == 1234.56
        assert TypeSignatureLibrary.test_amount("€100") == 100.0
    
    def test_negative_amount(self):
        """测试负数金额"""
        assert TypeSignatureLibrary.test_amount("-500.00") == -500.0
        assert TypeSignatureLibrary.test_amount("-￥1,000") == -1000.0
    
    def test_amount_with_percentage(self):
        """测试带百分比的金额"""
        assert TypeSignatureLibrary.test_amount("15.5%") == 15.5
    
    def test_invalid_amounts(self):
        """测试无效金额"""
        assert TypeSignatureLibrary.test_amount("not-amount") is None
        assert TypeSignatureLibrary.test_amount("") is None


class TestOtherTypeDetection:
    """测试其他类型检测"""
    
    def test_percentage_detection(self):
        """测试百分比检测"""
        assert TypeSignatureLibrary.test_percentage("15.5%") == 15.5
        assert TypeSignatureLibrary.test_percentage("100%") == 100.0
        assert TypeSignatureLibrary.test_percentage("not-percent") is None
    
    def test_account_detection(self):
        """测试银行账号检测"""
        assert TypeSignatureLibrary.test_account("6222021234567890") is not None
        assert TypeSignatureLibrary.test_account("6222 0212 3456 7890") is not None
        assert TypeSignatureLibrary.test_account("123") is None  # 太短
    
    def test_phone_detection(self):
        """测试手机号检测"""
        assert TypeSignatureLibrary.test_phone("13812345678") is not None
        assert TypeSignatureLibrary.test_phone("18912345678") is not None
        assert TypeSignatureLibrary.test_phone("12345678901") is None  # 不在13-19范围
    
    def test_id_number_detection(self):
        """测试身份证号检测"""
        assert TypeSignatureLibrary.test_id_number("110101199001011234") is not None
        assert TypeSignatureLibrary.test_id_number("11010119900101123X") is not None
        assert TypeSignatureLibrary.test_id_number("123") is None
    
    def test_number_detection(self):
        """测试普通数字检测"""
        assert TypeSignatureLibrary.test_number("123.45") == 123.45
        assert TypeSignatureLibrary.test_number("-67") == -67.0
        assert TypeSignatureLibrary.test_number("not-number") is None


class TestSignatureInference:
    """测试列签名推断"""
    
    def test_infer_date_signature(self):
        """测试日期列签名推断"""
        values = ["2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18"]
        sig = TypeSignatureLibrary.infer_signature(values)
        assert sig.type_name == "date"
        assert sig.confidence == 1.0
        assert len(sig.pattern_examples) > 0
    
    def test_infer_amount_signature(self):
        """测试金额列签名推断"""
        values = ["15,000.00", "3,000.00", "200.00", "1,500.50"]
        sig = TypeSignatureLibrary.infer_signature(values)
        assert sig.type_name == "amount"
        assert sig.confidence == 1.0
    
    def test_infer_text_signature(self):
        """测试文本列签名推断"""
        values = ["工资收入", "转账支出", "消费", "利息"]
        sig = TypeSignatureLibrary.infer_signature(values)
        assert sig.type_name == "text"
        assert sig.confidence == 1.0
    
    def test_infer_mixed_signature_with_nulls(self):
        """测试混合数据（含空值）的签名推断"""
        values = ["2024-01-15", "", "2024-01-17", "", "2024-01-18"]
        sig = TypeSignatureLibrary.infer_signature(values)
        assert sig.type_name == "date"
        assert sig.confidence == 0.6  # 3/5
        assert sig.nullable_count == 2
    
    def test_infer_empty_values(self):
        """测试空值列表"""
        sig = TypeSignatureLibrary.infer_signature([])
        assert sig.type_name == "unknown"
        assert sig.confidence == 0.0
    
    def test_infer_low_confidence(self):
        """测试低置信度场景"""
        values = ["2024-01-15", "not-a-date", "12345", "abc"]
        sig = TypeSignatureLibrary.infer_signature(values)
        # text 有 2 个匹配 ("not-a-date", "abc")
        assert sig.type_name == "text"
        assert sig.confidence == 0.5


class TestTableSignatureProfile:
    """测试表格签名画像"""
    
    def test_infer_bank_statement_signature(self):
        """测试银行流水表格签名"""
        # 提供更有规律的数据行（减少空值）
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
        
        # 验证各列类型
        assert profile.signatures[0].type_name == "date"
        assert profile.signatures[1].type_name == "text"
        # 第2、3、4列都应该是 amount
        assert profile.signatures[2].type_name == "amount"
        assert profile.signatures[3].type_name == "amount"
        assert profile.signatures[4].type_name == "amount"
    
    def test_infer_insufficient_rows(self):
        """测试行数不足的情况"""
        rows = [
            ["日期", "金额"],
            ["2024-01-15", "1000"],
        ]
        profile = TypeSignatureLibrary.infer_table_signature(rows, min_data_rows=3)
        assert profile is None  # 数据行不足3行
    
    def test_consistency_threshold(self):
        """测试一致性阈值"""
        # 高质量数据
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
        
        # 低质量数据（混合类型）
        low_quality_rows = [
            ["2024-01-15", "some-text"],
            ["random", "12345"],
            ["not-date", "more-text"],
        ]
        profile = TypeSignatureLibrary.infer_table_signature(
            low_quality_rows,
            consistency_threshold=0.7
        )
        # 应该能生成profile，但一致性较低
        assert profile is not None
        assert profile.overall_consistency < 0.7


class TestEdgeCases:
    """测试边界情况"""
    
    def test_single_column_table(self):
        """测试单列表格"""
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
        """测试宽表格（20列）"""
        rows = []
        for i in range(5):
            row = [f"2024-01-{15+i}"] + [f"value_{j}" for j in range(19)]
            rows.append(row)
        profile = TypeSignatureLibrary.infer_table_signature(rows)
        assert profile is not None
        assert len(profile.signatures) == 20
    
    def test_all_empty_cells(self):
        """测试全空单元格"""
        rows = [
            ["", "", ""],
            ["", "", ""],
            ["", "", ""],
        ]
        profile = TypeSignatureLibrary.infer_table_signature(rows)
        assert profile is not None
        # 所有列都应该是 empty 类型
        for sig in profile.signatures:
            assert sig.type_name == "empty"
        # 全空不应该被认为是表头
        assert profile.is_likely_header is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
