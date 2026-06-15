# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for compact bank ledger parsing (银座银行 layout)."""

from __future__ import annotations

from docmirror.plugins._base.bank_compact_parser import (
    extract_compact_ledger_transactions,
    normalize_compact_transaction,
    parse_compact_ledger_cell,
    parse_counterparty_cell,
    resolve_amount_fields,
)


def test_parse_compact_ledger_cell_three_amounts():
    parsed = parse_compact_ledger_cell("2025-10-273765000.003765306.09")
    resolved = resolve_amount_fields(parsed, summary="电汇/服务费")
    assert resolved["date"] == "2025-10-27"
    assert resolved["expense"] == 3765000.00
    assert resolved["amount"] == 3765000.00
    assert resolved["direction"] == "expense"
    assert resolved["balance"] == 3765306.09


def test_parse_compact_ledger_cell_interest_two_amounts():
    parsed = parse_compact_ledger_cell("2025-09-210.04306.09")
    resolved = resolve_amount_fields(parsed, summary="结息")
    assert resolved["date"] == "2025-09-21"
    assert resolved["amount"] == 0.04
    assert resolved["direction"] == "income"
    assert resolved["balance"] == 306.09


def test_parse_counterparty_cell():
    account, name = parse_counterparty_cell("01041560012000235重庆正大能科科")
    assert account == "01041560012000235"
    assert name == "重庆正大能科科"


def test_extract_and_normalize_with_continuation_rows():
    table = [
        ["银座银行交易明细", "", ""],
        ["账号:651204680300015", "第1 / 1页", ""],
        ["日期支出收入余额", "对方账户对方户名", "摘要/附言"],
        ["2025-09-210.04306.09", "", "结息"],
        ["00:07:46", "", ""],
        ["2025-10-273765000.003765306.09", "01041560012000235重庆正大能科科", "电汇/服务费"],
        ["16:36:24", "技有限公司", ""],
    ]
    raws = extract_compact_ledger_transactions(table)
    assert len(raws) == 2

    first = normalize_compact_transaction(raws[0])
    assert first["date"] == "2025-09-21"
    assert first["timestamp"] == "2025-09-21 00:07:46"
    assert first["amount"] == 0.04
    assert first["summary"] == "结息"

    second = normalize_compact_transaction(raws[1])
    assert second["date"] == "2025-10-27"
    assert second["timestamp"] == "2025-10-27 16:36:24"
    assert second["amount"] == 3765000.00
    assert second["counter_account"] == "01041560012000235"
    assert "重庆正大能科" in second["counter_party"]
    assert "技有限公司" in second["counter_party"]
