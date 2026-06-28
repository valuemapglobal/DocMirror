"""Unit tests for generic community output v2.1 — type detection, standardization, identity extraction."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from docmirror.plugins._base.generic_mirror_adapter import (
    _type_detect_column,
    _standardize_value,
    _extract_identities,
    _build_normalized_record,
    _GENERIC_WARNING,
)

# ═══════════════════════════════════════════════════════════════════════════════
#  _type_detect_column
# ═══════════════════════════════════════════════════════════════════════════════


class TestTypeDetectColumn:
    def test_detect_date(self):
        col_type, conf = _type_detect_column(["2024-01-01", "2024-02-15", "2024-03-20"])
        assert col_type == "date"
        assert conf >= 0.6

    def test_detect_amount(self):
        col_type, conf = _type_detect_column(["1,000.00", "500.50", "-50.00", "¥100.00"])
        assert col_type == "amount"
        assert conf >= 0.6

    def test_detect_phone(self):
        col_type, conf = _type_detect_column(["13800138000", "13912345678", "18600001111"])
        assert col_type == "phone"
        assert conf >= 0.6

    def test_detect_id_number(self):
        col_type, conf = _type_detect_column(
            ["110101199001011234", "32010219850706321X", "440305200112123456"]
        )
        assert col_type == "id_number"
        assert conf >= 0.6

    def test_detect_email(self):
        col_type, conf = _type_detect_column(
            ["user@example.com", "test@company.cn", "admin@test.org"]
        )
        assert col_type == "email"
        assert conf >= 0.6

    def test_detect_percentage(self):
        col_type, conf = _type_detect_column(["5%", "12.5%", "99.9%", "0%"])
        assert col_type == "percentage"
        assert conf >= 0.6

    def test_text_fallback(self):
        col_type, conf = _type_detect_column(
            ["报销差旅费", "办公用品采购", "交通费", "餐费补贴"]
        )
        assert col_type == "text"

    def test_mixed_column_fallback_to_text(self):
        """Mixed types (dates + amounts) should fall back to text."""
        col_type, conf = _type_detect_column(
            ["2024-01-01", "1,000.00", "摘要说明", "张三"]
        )
        assert col_type == "text"
        assert conf < 0.6

    def test_empty_values(self):
        col_type, conf = _type_detect_column([])
        assert col_type == "text"
        assert conf == 0.0

    def test_dash_values_skipped(self):
        col_type, conf = _type_detect_column(["-", "—", "2024-01-01", "2024-02-01"])
        assert col_type == "date"
        assert conf >= 0.6

    def test_detect_account_number(self):
        col_type, conf = _type_detect_column(
            ["6222021234567890123", "6228480012345678901", "6217001234567890123"]
        )
        assert col_type == "account"
        assert conf >= 0.6


# ═══════════════════════════════════════════════════════════════════════════════
#  _standardize_value
# ═══════════════════════════════════════════════════════════════════════════════


class TestStandardizeValue:
    def test_amount_float(self):
        result = _standardize_value("1,000.00", "amount")
        assert isinstance(result, dict)
        assert result["value"] == 1000.0
        assert result["currency"] == "CNY"

    def test_amount_negative(self):
        result = _standardize_value("-500.00", "amount")
        assert isinstance(result, dict)
        assert result["value"] == -500.0

    def test_amount_with_currency_symbol(self):
        result = _standardize_value("¥100.00", "amount")
        assert isinstance(result, dict)
        assert result["value"] == 100.0
        assert result["currency"] == "CNY"

    def test_amount_usd(self):
        result = _standardize_value("$50.00", "amount")
        assert isinstance(result, dict)
        assert result["value"] == 50.0
        assert result["currency"] == "USD"

    def test_amount_non_numeric(self):
        result = _standardize_value("N/A", "amount")
        assert result == "N/A"  # raw pass-through

    def test_date_iso(self):
        result = _standardize_value("2024-01-01", "date")
        assert isinstance(result, dict)
        assert result["value"] == "2024-01-01"

    def test_date_chinese_format(self):
        result = _standardize_value("2024年01月01日", "date")
        assert isinstance(result, dict)
        assert "2024" in result["value"]

    def test_percentage(self):
        result = _standardize_value("12.5%", "percentage")
        assert isinstance(result, dict)
        assert result["value"] == 12.5
        assert result["unit"] == "%"

    def test_phone_digits(self):
        result = _standardize_value("138-0013-8000", "phone")
        assert isinstance(result, dict)
        assert result["value"] == "13800138000"

    def test_text_passthrough(self):
        result = _standardize_value("报销差旅费", "text")
        assert result == "报销差旅费"


# ═══════════════════════════════════════════════════════════════════════════════
#  _extract_identities
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractIdentities:
    def test_extract_name_by_key(self):
        fields = {"客户名称": "张三", "金额": "1,000"}
        ids = _extract_identities(fields)
        assert "name" in ids
        assert ids["name"]["key"] == "客户名称"
        assert ids["name"]["value"] == "张三"

    def test_extract_phone_by_value(self):
        fields = {"联系电话": "13800138000"}
        ids = _extract_identities(fields)
        assert "phone" in ids
        assert ids["phone"]["value"] == "13800138000"

    def test_extract_id_by_key(self):
        fields = {"身份证号": "110101199001011234"}
        ids = _extract_identities(fields)
        assert "id_number" in ids
        assert ids["id_number"]["value"] == "110101199001011234"

    def test_extract_account_by_key(self):
        fields = {"银行账号": "6222021234567890123"}
        ids = _extract_identities(fields)
        assert "account" in ids
        assert ids["account"]["key"] == "银行账号"

    def test_extract_address(self):
        fields = {"住址": "北京市朝阳区建国路88号"}
        ids = _extract_identities(fields)
        assert "address" in ids
        assert ids["address"]["value"] == "北京市朝阳区建国路88号"

    def test_english_field_names(self):
        fields = {"Name": "Alice", "Phone": "13800138000"}
        ids = _extract_identities(fields)
        assert "name" in ids
        assert ids["name"]["value"] == "Alice"

    def test_empty_fields(self):
        ids = _extract_identities({})
        assert ids == {}

    def test_value_pattern_fallback(self):
        """When key doesn't match, phone pattern should still detect."""
        fields = {"联系方式": "13912345678"}
        ids = _extract_identities(fields)
        assert "phone" in ids
        assert ids["phone"]["value"] == "13912345678"


# ═══════════════════════════════════════════════════════════════════════════════
#  _build_normalized_record
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildNormalizedRecord:
    def test_normalized_record_with_types(self):
        raw = {"日期": "2024-01-01", "金额": "1,000.00", "摘要": "报销差旅费"}
        col_types = {
            "日期": {"type": "date", "confidence": 0.95, "null_ratio": 0.0},
            "金额": {"type": "amount", "confidence": 0.90, "null_ratio": 0.0},
            "摘要": {"type": "text", "confidence": 0.80, "null_ratio": 0.0},
        }
        normalized = _build_normalized_record(raw, col_types)
        assert isinstance(normalized["日期"], dict)
        assert normalized["金额"]["value"] == 1000.0
        assert normalized["摘要"] == "报销差旅费"

    def test_normalized_unknown_column_type(self):
        raw = {"未知字段": "随便什么内容"}
        col_types = {}
        normalized = _build_normalized_record(raw, col_types)
        assert normalized["未知字段"] == "随便什么内容"

    def test_normalized_empty_raw(self):
        normalized = _build_normalized_record({}, {})
        assert normalized == {}
