# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Bank ledger table rebuild from plugin transactions."""

from __future__ import annotations

import pytest

pytest.importorskip("docmirror_enterprise", reason="enterprise package is not available in OSS CI")

from docmirror_enterprise.plugins.bank_statement.table_rebuild import rebuild_bank_table_from_transactions

from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult


def test_rebuild_bank_table_from_transactions():
    pr = ParseResult(
        pages=[PageContent(page_number=1, tables=[])],
        entities=DocumentEntities(document_type="bank_statement"),
    )
    txns = [
        {
            "date": "2024-01-01",
            "description": "工资入账",
            "amount": 5000.0,
            "type": "credit",
            "balance": 8000.0,
        }
    ]
    assert rebuild_bank_table_from_transactions(pr, txns) is True
    assert len(pr.pages[0].tables) == 1
    assert pr.pages[0].tables[0].row_count == 1
    assert pr.pages[0].tables[0].headers[0] == "交易日期"
