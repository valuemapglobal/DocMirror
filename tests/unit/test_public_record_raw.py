# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for stripping parser-internal keys from edition ``raw`` rows."""

from __future__ import annotations

from docmirror.plugins._base.base_table_parser import public_record_raw
from docmirror.plugins.bank_statement.canonical import records_from_raw_transactions


def test_public_record_raw_strips_internal_keys():
    raw_txn = {
        "交易时间": "2023030610:31:25",
        "收入金额": "20000.00",
        "_norm": {"交易日期": "2023030610:31:25", "收入金额": "20000.00"},
        "_style_id": "split_debit_credit",
    }
    public = public_record_raw(raw_txn)

    assert public == {"交易时间": "2023030610:31:25", "收入金额": "20000.00"}
    assert "_norm" not in public
    assert "_style_id" not in public


def test_records_from_raw_transactions_omits_internal_keys():
    transactions = [
        {
            "交易时间": "2023030610:31:25",
            "收入金额": "20000.00",
            "支出金额": "0",
            "_norm": {"交易日期": "2023030610:31:25"},
            "_style_id": "split_debit_credit",
        }
    ]

    def _normalize(raw_txn):
        assert "_norm" in raw_txn
        return {"amount": 20000.0, "direction": "income"}

    records = records_from_raw_transactions(
        transactions,
        normalize_fn=_normalize,
        style_id="split_debit_credit",
    )

    assert len(records) == 1
    assert records[0]["raw"] == {
        "交易时间": "2023030610:31:25",
        "收入金额": "20000.00",
        "支出金额": "0",
    }
    assert records[0]["normalized"]["amount"] == 20000.0
