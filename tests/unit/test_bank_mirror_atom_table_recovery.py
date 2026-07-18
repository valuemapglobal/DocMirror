# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror atom split debit/credit bank ledger recovery tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from docmirror.plugins.bank_statement.canonical import dedupe_transaction_rows
from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
from docmirror.plugins.bank_statement.mirror_atom_table_recovery import recover_mirror_atom_bank_tables

pytestmark = pytest.mark.unit


def _atom(atom_id: str, text: str, x0: float, y0: float, x1: float | None = None) -> dict:
    return {
        "id": atom_id,
        "page_id": "page:0001",
        "text": text,
        "bbox": [x0, y0, x1 if x1 is not None else x0 + 20.0, y0 + 8.0],
    }


def _result(atoms: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(_runtime_mirror_cache={"evidence": {"text_atoms": atoms}})


def test_recovers_complete_split_debit_credit_rows():
    atoms = [
        _atom("hs", "序号", 25.0, 80.0, 41.0),
        _atom("hd", "交易日期", 52.0, 80.0, 85.0),
        _atom("hr", "交易流水号", 108.0, 80.0, 149.0),
        _atom("hm", "支出（元）收入（元）账户余额（元）", 165.0, 80.0, 312.0),
        _atom("ha", "对方账号", 339.0, 80.0, 372.0),
        _atom("hp", "对方户名", 428.0, 80.0, 461.0),
        _atom("hn", "对方行号", 505.0, 80.0, 538.0),
        _atom("hbn", "对方行名", 563.0, 80.0, 596.0),
        _atom("hc", "交易渠道", 613.0, 80.0, 646.0),
        _atom("hpu", "用途", 698.0, 80.0, 715.0),
        _atom("hsu", "摘要", 782.0, 80.0, 799.0),
        _atom("s1", "1", 30.0, 110.0, 34.0),
        _atom("d1", "20260102", 49.0, 110.0, 88.0),
        _atom("r1", "REF001", 108.0, 110.0, 145.0),
        _atom("e1", "12.34", 181.0, 110.0, 205.2),
        _atom("b1", "100.00", 281.0, 110.0, 313.1),
        _atom("a1", "1234567890", 340.0, 110.0, 390.0),
        _atom("p1", "甲公司", 428.0, 110.0, 460.0),
        _atom("bn1", "BANK001", 505.0, 110.0, 535.0),
        _atom("bname1", "测试银行", 563.0, 110.0, 600.0),
        _atom("channel1", "网银", 613.0, 110.0, 635.0),
        _atom("purpose1", "货款", 698.0, 110.0, 720.0),
        _atom("summary1", "转账", 782.0, 110.0, 804.0),
        _atom("s2", "2", 30.0, 140.0, 34.0),
        _atom("d2", "20260103", 49.0, 140.0, 88.0),
        _atom("r2", "REF002", 108.0, 140.0, 145.0),
        _atom("i2", "20.00", 224.0, 140.0, 248.3),
        _atom("b2", "120.00", 281.0, 140.0, 313.1),
        _atom("s3", "3", 30.0, 170.0, 34.0),
        _atom("d3", "20260104", 49.0, 170.0, 88.0),
        _atom("r3", "REF003", 108.0, 170.0, 145.0),
        _atom("e3", "1.00", 181.0, 170.0, 205.2),
        _atom("b3", "119.00", 281.0, 170.0, 313.1),
        _atom("s4", "4", 30.0, 200.0, 34.0),
        _atom("d4", "20260105", 49.0, 200.0, 88.0),
        _atom("r4", "REF004", 108.0, 200.0, 145.0),
        _atom("i4", "1.00", 224.0, 200.0, 248.3),
        _atom("b4", "120.00", 281.0, 200.0, 313.1),
    ]

    tables = recover_mirror_atom_bank_tables(_result(atoms))

    assert len(tables) == 1
    assert tables[0][0] == [
        "序号",
        "交易日期",
        "交易流水号",
        "支出金额",
        "收入金额",
        "余额",
        "对方账号",
        "对方户名",
        "对方行号",
        "对方行名",
        "交易渠道",
        "用途",
        "摘要",
    ]
    assert tables[0][1] == [
        "1",
        "20260102",
        "REF001",
        "12.34",
        "",
        "100.00",
        "1234567890",
        "甲公司",
        "BANK001",
        "测试银行",
        "网银",
        "货款",
        "转账",
    ]
    assert tables[0][2][:6] == ["2", "20260103", "REF002", "", "20.00", "120.00"]
    assert len(tables[0]) == 5


def test_rejects_layout_without_complete_issuer_headers():
    atoms = [
        _atom("hd", "交易日期", 52.0, 80.0),
        _atom("d1", "20260102", 49.0, 110.0),
        _atom("a1", "12.34", 181.0, 110.0, 205.2),
    ]

    assert recover_mirror_atom_bank_tables(_result(atoms)) == []


def test_dedupe_uses_bank_reference_before_lossy_business_fields():
    base = {"normalized": {"date": "2026-01-02", "amount": 100.0, "balance": 200.0, "counter_party": "甲"}}
    records = [
        {**base, "raw": {"交易流水号": "REF001"}},
        {**base, "raw": {"交易流水号": "REF002"}},
        {**base, "raw": {"交易流水号": "REF002"}},
    ]

    deduped = dedupe_transaction_rows(records)

    assert len(deduped) == 2


def test_recovers_bank_header_title_and_total_row_count_from_mirror_atoms():
    atoms = [
        _atom("title", "测试银行账户交易明细表", 200.0, 10.0, 400.0),
        _atom("print", "打印日期：2026-07-18", 10.0, 30.0, 150.0),
        _atom("period", "交易时段：2026-01-01 至 2026-06-30", 10.0, 45.0, 260.0),
        _atom("holder", "户名：测试用户", 10.0, 60.0, 100.0),
        _atom("account", "账号：1234567890", 110.0, 60.0, 230.0),
        _atom("currency", "币种：人民币", 240.0, 60.0, 320.0),
        _atom("total", "总条数：38", 10.0, 220.0, 80.0),
    ]

    fields = BankStatementCommunityPlugin()._recover_identity_from_mirror(_result(atoms))

    assert fields["statement_title"]["normalized_value"] == "测试银行账户交易明细表"
    assert fields["print_date"]["normalized_value"] == "2026-07-18"
    assert fields["query_period"]["normalized_value"] == "2026-01-01 至 2026-06-30"
    assert fields["total_transactions"]["normalized_value"] == "38"
    assert fields["account_number"]["normalized_value"] == "1234567890"
