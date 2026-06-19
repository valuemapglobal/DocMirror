# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CCB-style spaced split headers route through header_resolve SSOT (BS-001)."""

from __future__ import annotations

from docmirror.plugins.bank_statement.header_resolve import has_split_debit_credit_headers


def test_spaced_split_debit_credit_headers_detected():
    headers = ["序号", "记账日", "借方发 生额", "贷方发 生额", "余额"]
    assert has_split_debit_credit_headers([[headers]])


def test_compact_split_debit_credit_headers_detected():
    headers = ["交易日期", "摘要", "借方发生额", "贷方发生额", "余额"]
    assert has_split_debit_credit_headers([[headers]])


def test_normalize_split_with_spaced_headers():
    from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
    from docmirror.plugins.bank_statement.styles.grid_standard import normalize_record

    plugin = BankStatementCommunityPlugin()
    raw = {
        "记账日": "20220401",
        "借方发 生额": "100.00",
        "贷方发 生额": "",
        "余额": "500.00",
    }
    norm = normalize_record(raw, plugin)
    assert norm["direction"] == "expense"
    assert float(norm["amount"]) == 100.0


def test_single_amount_column_not_split():
    headers = ["交易日期", "摘要", "发生额", "余额"]
    assert not has_split_debit_credit_headers([[headers]])
